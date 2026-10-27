#!/usr/bin/env python3
"""
Console Web do Operador — Motor SunTzu (Chess Challenge III ICEV 2026)

Servidor HTTP local (somente 127.0.0.1, apenas biblioteca padrão) que expõe a GameSession e o
WatchdogEngine para a página tools/operator_console/web/index.html:
- GET  /            -> página do console (HTML/CSS/JS autocontido, 100% offline)
- GET  /api/state   -> snapshot JSON completo do estado
- GET  /events      -> Server-Sent Events: snapshot a cada mudança (e batimento periódico)
- GET  /api/pgn     -> download de partidas/ultima.pgn
- POST /api/parse | /api/move | /api/undo | /api/clock | /api/settings | /api/new | /api/move-now

O motor joga automaticamente em uma thread dedicada sempre que for a nossa vez.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from tools.operator_console.console import (  # noqa: E402
    GameSession,
    WatchdogEngine,
    apply_time_profile,
    build_engine_and_session,
    check_rule_alerts,
    describe_move_pt,
    format_clock_ms,
    origin_tag_for_move,
    parse_clock_str,
    parse_user_move,
)

import chess  # noqa: E402  (disponível após console.py configurar o .venv no sys.path)

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")

# SAN inglês -> português (N=C, R=T, Q=D, K=R; B permanece B)
EN_TO_PT_PIECE = {"N": "C", "B": "B", "R": "T", "Q": "D", "K": "R"}


def san_to_pt(san: str) -> str:
    return re.sub(r"[NBRQK]", lambda m: EN_TO_PT_PIECE[m.group(0)], san)


def _color_name(color: chess.Color) -> str:
    return "white" if color == chess.WHITE else "black"


class ConsoleController:
    """
    Coordena GameSession + WatchdogEngine para o console web.
    O WatchdogEngine não é thread-safe: toda ação que toca o motor ou o tabuleiro roda sob self.lock
    e é recusada enquanto o motor estiver calculando (exceto 'Jogar agora', que só envia 'stop').
    """

    def __init__(
        self,
        engine: WatchdogEngine,
        session: GameSession,
        args: argparse.Namespace,
        movetime_override_ms: Optional[int] = None,
        initial_message: str = "",
    ):
        self.engine = engine
        self.session = session
        self.args = args
        self.movetime_override_ms = movetime_override_ms
        self.lock = threading.RLock()
        self.changed = threading.Condition()
        self.version = 0
        self.thinking = False
        self.search_started_at: Optional[float] = None
        self.turn_started_at = time.time()
        self.last_our_move: Optional[dict[str, object]] = None
        self.pv_fen: str = session.board.fen()
        self.status = {"text": initial_message or "Console pronto.", "level": "success" if initial_message else "info"}
        self._board_cache: dict[str, object] = {}
        self._closed = False
        self._wake = threading.Event()
        self._refresh_board_cache()
        self.worker = threading.Thread(target=self._engine_worker, name="suntzu-engine-worker", daemon=True)

    # ------------------------------------------------------------------ estado

    def start(self):
        self.worker.start()
        self._wake.set()

    def _bump(self):
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    def _set_status(self, text: str, level: str = "info"):
        self.status = {"text": text, "level": level}

    def _refresh_board_cache(self):
        """Recalcula a parte do snapshot derivada do tabuleiro (chamado sob lock, fora de buscas)."""
        board = self.session.board
        legal = []
        for mv in board.legal_moves:
            legal.append(
                {
                    "uci": mv.uci(),
                    "from": chess.square_name(mv.from_square),
                    "to": chess.square_name(mv.to_square),
                    "promo": chess.piece_symbol(mv.promotion) if mv.promotion else None,
                }
            )
            if board.is_castling(mv):
                # Permite arrastar o rei sobre a própria torre (como no chess.com / lichess)
                rook_sq = chess.square(7 if board.is_kingside_castling(mv) else 0, chess.square_rank(mv.from_square))
                legal.append({"uci": mv.uci(), "from": chess.square_name(mv.from_square), "to": chess.square_name(rook_sq), "promo": None})

        history = []
        replay = chess.Board(self.session.start_fen)
        for m_uci in self.session.moves_uci:
            mv = chess.Move.from_uci(m_uci)
            history.append(
                {
                    "uci": m_uci,
                    "san": san_to_pt(replay.san(mv)),
                    "ours": replay.turn == self.session.our_color,
                }
            )
            replay.push(mv)

        pieces = {chess.square_name(sq): p.symbol() for sq, p in board.piece_map().items()}
        check_sq = None
        if board.is_check():
            king_sq = board.king(board.turn)
            check_sq = chess.square_name(king_sq) if king_sq is not None else None

        last_move = None
        if self.session.moves_uci:
            lm = chess.Move.from_uci(self.session.moves_uci[-1])
            last_move = {"from": chess.square_name(lm.from_square), "to": chess.square_name(lm.to_square)}

        game_over = board.is_game_over(claim_draw=True)
        result_reason = None
        if game_over:
            outcome = board.outcome(claim_draw=True)
            reasons = {
                chess.Termination.CHECKMATE: "Xeque-mate",
                chess.Termination.STALEMATE: "Afogamento",
                chess.Termination.INSUFFICIENT_MATERIAL: "Material insuficiente",
                chess.Termination.SEVENTYFIVE_MOVES: "Regra dos 75 lances",
                chess.Termination.FIVEFOLD_REPETITION: "Repetição quíntupla",
                chess.Termination.FIFTY_MOVES: "Regra dos 50 lances",
                chess.Termination.THREEFOLD_REPETITION: "Repetição tripla",
            }
            result_reason = reasons.get(outcome.termination, outcome.termination.name) if outcome else None

        start_board = chess.Board(self.session.start_fen)
        self._board_cache = {
            "fen": board.fen(),
            "start_turn": _color_name(start_board.turn),
            "start_fullmove": start_board.fullmove_number,
            "turn": _color_name(board.turn),
            "our_color": _color_name(self.session.our_color),
            "is_our_turn": board.turn == self.session.our_color,
            "fullmove": board.fullmove_number,
            "halfmove_clock": board.halfmove_clock,
            "pieces": pieces,
            "legal": legal,
            "history": history,
            "last_move": last_move,
            "check_square": check_sq,
            "game_over": game_over,
            "result": board.result(claim_draw=True) if game_over else None,
            "result_reason": result_reason,
        }

    def _pv_pt(self, pv_uci: list[str], max_moves: int = 8) -> list[str]:
        out = []
        try:
            b = chess.Board(self.pv_fen)
            for u in pv_uci[:max_moves]:
                mv = chess.Move.from_uci(u)
                if mv not in b.legal_moves:
                    break
                out.append(san_to_pt(b.san(mv)))
                b.push(mv)
        except Exception:
            pass
        return out

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            telem = self.engine.get_telemetry_snapshot()
            telem["pv_pt"] = self._pv_pt(list(telem.get("pv") or []))
            ponder_san = None
            if telem.get("pondering") and telem.get("ponder_move_uci"):
                try:
                    mv = chess.Move.from_uci(str(telem["ponder_move_uci"]))
                    if mv in self.session.board.legal_moves:
                        ponder_san = san_to_pt(self.session.board.san(mv))
                except Exception:
                    pass
            telem["ponder_san"] = ponder_san
            is_our_turn = self.session.board.turn == self.session.our_color
            snap = dict(self._board_cache)
            snap.update(
                {
                    "version": self.version,
                    "server_time": time.time(),
                    "thinking": self.thinking,
                    "search_started_at": self.search_started_at,
                    "turn_started_at": self.turn_started_at,
                    "clocks": {
                        "white_ms": self.session.wtime_ms,
                        "black_ms": self.session.btime_ms,
                        "initial_ms": self.session.initial_time_ms,
                    },
                    "last_our_move": self.last_our_move,
                    "rule_alerts": check_rule_alerts(
                        self.session.board, self.engine.last_eval_cp, is_our_turn=is_our_turn
                    ),
                    "engine": telem,
                    "settings": {
                        "profile": self.engine.options.get("OpponentProfile", "auto"),
                        "time_profile": self.engine.options.get("TimeProfile", "normal"),
                        "movetime_sec": (self.movetime_override_ms / 1000.0) if self.movetime_override_ms else None,
                        "ponder": self.session.enable_ponder,
                        "confirm": not getattr(self.args, "no_confirm", False),
                        "threads": self.engine.options.get("Threads"),
                        "hash": self.engine.options.get("Hash"),
                    },
                    "status": self.status,
                    "save_dir": self.session.save_dir,
                }
            )
            return snap

    # ------------------------------------------------------------------ motor

    def _engine_worker(self):
        while not self._closed:
            self._wake.wait(0.5)
            self._wake.clear()
            with self.lock:
                if self._closed or self.thinking:
                    continue
                board = self.session.board
                if board.turn != self.session.our_color or board.is_game_over(claim_draw=True):
                    continue
                self.thinking = True
                self.search_started_at = time.time()
                self.pv_fen = board.fen()
                self._set_status("Motor calculando…", "warn")
            self._bump()

            try:
                # O tabuleiro não muda durante a busca; ações concorrentes são recusadas por self.thinking.
                _, info, hit, elapsed_ms = self.session.play_our_move(
                    movetime_override_ms=self.movetime_override_ms
                )
            except Exception as err:
                with self.lock:
                    self.thinking = False
                    self.search_started_at = None
                    self._set_status(f"[ERRO DO MOTOR] {err} — nova tentativa em 1 s.", "error")
                self._bump()
                time.sleep(1.0)
                self._wake.set()
                continue

            with self.lock:
                tag, from_book = origin_tag_for_move(self.engine, self.session, hit, elapsed_ms)
                self.last_our_move = dict(info)
                self.last_our_move.update(
                    {
                        "san_pt": san_to_pt(str(info["san"])),
                        "origin": tag,
                        "from_book": from_book,
                        "ponderhit": hit,
                        "elapsed_ms": elapsed_ms,
                        "ply": len(self.session.moves_uci),
                    }
                )
                self.thinking = False
                self.search_started_at = None
                self.turn_started_at = time.time()
                self._refresh_board_cache()
                self._set_status(
                    f"[NOSSO LANCE] Execute {self.last_our_move['san_pt']} "
                    f"({info['from_sq']} → {info['to_sq']}) no tabuleiro físico [{tag}].",
                    "success",
                )
            self._bump()

    # ------------------------------------------------------------------ ações

    def _busy(self) -> Optional[dict[str, object]]:
        if self.thinking:
            return {"ok": False, "level": "warn", "message": "Motor calculando — aguarde ou use 'Jogar agora'."}
        return None

    def _done(self, message: str, level: str = "success") -> dict[str, object]:
        self._set_status(message, level)
        self._refresh_board_cache()
        self._bump()
        self._wake.set()
        return {"ok": True, "level": level, "message": message}

    def parse(self, text: str) -> dict[str, object]:
        """Valida (sem aplicar) um lance do adversário e devolve a descrição para confirmação."""
        with self.lock:
            board = self.session.board
            if board.turn == self.session.our_color:
                return {"ok": False, "level": "warn", "message": "Não é a vez do adversário."}
            try:
                mv = parse_user_move(board, text)
            except ValueError as err:
                return {"ok": False, "level": "error", "message": str(err)}
            info = describe_move_pt(board, mv)
            info["san_pt"] = san_to_pt(str(info["san"]))
            # Torre saindo do canto enquanto o roque daquele lado é legal: provável roque registrado errado
            piece = board.piece_at(mv.from_square)
            if piece is not None and piece.piece_type == chess.ROOK:
                for castle in board.legal_moves:
                    if board.is_castling(castle) and chess.square_file(mv.from_square) == (7 if board.is_kingside_castling(castle) else 0):
                        info["alerts"] = [
                            f"SE O ADVERSÁRIO ROCOU, cancele e registre {'O-O' if board.is_kingside_castling(castle) else 'O-O-O'} "
                            "(ou mova o REI até a torre)!"
                        ] + list(info["alerts"])  # type: ignore[arg-type]
                        break
            return {"ok": True, "level": "info", "message": "", "move": info}

    def opp_move(self, text: str) -> dict[str, object]:
        with self.lock:
            busy = self._busy()
            if busy:
                return busy
            if self.session.board.is_game_over(claim_draw=True):
                return {"ok": False, "level": "warn", "message": "Partida encerrada."}
            if self.session.board.turn == self.session.our_color:
                return {"ok": False, "level": "warn", "message": "Não é a vez do adversário."}
            try:
                mv = parse_user_move(self.session.board, text)
            except ValueError as err:
                self._set_status(f"[LANCE REJEITADO] {err}", "error")
                self._bump()
                return {"ok": False, "level": "error", "message": f"[LANCE REJEITADO] {err}"}
            san_pt = san_to_pt(self.session.board.san(mv))
            # Estimativa do tempo gasto pelo adversário (relógio físico prevalece: sincronize a cada 10 lances)
            spent_ms = int((time.time() - self.turn_started_at) * 1000)
            self.session.opp_time_ms = self.session.opp_time_ms - spent_ms
            self.session.apply_opponent_move(mv)
            self.last_our_move = None
            self.turn_started_at = time.time()
            return self._done(f"[LANCE DO ADVERSÁRIO] {san_pt} registrado.")

    def undo(self) -> dict[str, object]:
        with self.lock:
            busy = self._busy()
            if busy:
                return busy
            undone = self.session.undo_last()
            self.last_our_move = None
            self.turn_started_at = time.time()
            if undone == 0:
                return self._done("Nada para desfazer.", "warn")
            return self._done(f"[DESFEITO] {undone} meio(s)-lance(s) revertido(s).")

    def set_clock(self, side: str, value: str) -> dict[str, object]:
        with self.lock:
            try:
                if side == "ours":
                    ms = self.session.sync_our_clock(value)
                    msg = f"[RELÓGIO SINCRONIZADO] Nosso tempo ajustado para {format_clock_ms(ms)}."
                else:
                    ms = parse_clock_str(value)
                    self.session.opp_time_ms = ms
                    self.session.autosave()
                    msg = f"[RELÓGIO SINCRONIZADO] Tempo do adversário ajustado para {format_clock_ms(ms)}."
            except ValueError as err:
                return {"ok": False, "level": "error", "message": f"[ERRO DE RELÓGIO] {err}"}
            self.turn_started_at = time.time()
            return self._done(msg)

    def update_settings(self, data: dict[str, object]) -> dict[str, object]:
        with self.lock:
            busy = self._busy()
            if busy:
                return busy
            msgs = []
            if "profile" in data:
                prof = str(data["profile"])
                if prof not in ("auto", "forte", "medio", "fraco"):
                    return {"ok": False, "level": "error", "message": "Perfil inválido."}
                self.engine.set_option("OpponentProfile", prof)
                msgs.append(f"OpponentProfile = {prof}")
            if "time_profile" in data:
                tp = str(data["time_profile"])
                if tp not in ("normal", "rapido"):
                    return {"ok": False, "level": "error", "message": "TimeProfile inválido."}
                apply_time_profile(self.engine, self.args, tp)
                msgs.append(f"TimeProfile = {tp.upper()}")
            if "movetime_sec" in data:
                raw = data["movetime_sec"]
                try:
                    sec = float(raw) if raw not in (None, "", "auto") else 0.0
                except (TypeError, ValueError):
                    return {"ok": False, "level": "error", "message": "Tempo por lance inválido."}
                self.movetime_override_ms = max(100, int(sec * 1000)) if sec > 0 else None
                msgs.append(f"tempo fixo {sec:.1f}s/lance" if self.movetime_override_ms else "tempo automático pelo relógio")
            return self._done("[AJUSTES] " + "; ".join(msgs) if msgs else "Nenhum ajuste.")

    def new_game(self, color: Optional[str]) -> dict[str, object]:
        with self.lock:
            busy = self._busy()
            if busy:
                return busy
            new_color = None
            if color in ("white", "brancas"):
                new_color = chess.WHITE
            elif color in ("black", "pretas"):
                new_color = chess.BLACK
            self.session.restart_game(new_color)
            self.last_our_move = None
            self.turn_started_at = time.time()
            self.pv_fen = self.session.board.fen()
            cor = "BRANCAS" if self.session.our_color == chess.WHITE else "PRETAS"
            return self._done(f"[NOVA PARTIDA] Jogamos de {cor}. Tabuleiro e relógios reiniciados.")

    def move_now(self) -> dict[str, object]:
        if not self.thinking:
            return {"ok": False, "level": "warn", "message": "O motor não está calculando."}
        try:
            self.engine._send_raw("stop")
        except Exception as err:
            return {"ok": False, "level": "error", "message": f"Falha ao enviar 'stop': {err}"}
        return {"ok": True, "level": "info", "message": "Pedido de lance imediato enviado ao motor."}

    def close(self):
        self._closed = True
        self._wake.set()
        if self.thinking:
            try:
                self.engine._send_raw("stop")
            except Exception:
                pass
            self.worker.join(timeout=5.0)
        with self.lock:
            self.engine.close()


def make_handler(controller: ConsoleController):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SunTzuConsole/1.0"

        def log_message(self, format, *args):  # noqa: A002 - silencia o log por requisição
            pass

        def _send_json(self, payload: dict[str, object], status: int = 200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_json(self) -> dict[str, object]:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            try:
                data = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}
            return data if isinstance(data, dict) else {}

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(WEB_DIR, "index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/state":
                self._send_json(controller.snapshot())
            elif path == "/api/pgn":
                pgn_path = os.path.join(controller.session.save_dir, "ultima.pgn")
                with open(pgn_path, "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/x-chess-pgn")
                self.send_header("Content-Disposition", f'attachment; filename="suntzu_{controller.session.session_tag}.pgn"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif path == "/events":
                self._stream_events()
            else:
                self._send_json({"ok": False, "message": "Não encontrado."}, 404)

        def _stream_events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            last_sent = -1
            try:
                while not controller._closed:
                    with controller.changed:
                        # Durante a busca envia telemetria ao vivo a cada 0,5 s; fora dela, batimento a cada 2 s
                        controller.changed.wait_for(
                            lambda: controller.version != last_sent, timeout=0.5 if controller.thinking else 2.0
                        )
                    snap = controller.snapshot()
                    last_sent = int(snap["version"])  # type: ignore[arg-type]
                    self.wfile.write(b"data: " + json.dumps(snap, ensure_ascii=False).encode("utf-8") + b"\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def do_POST(self):
            path = self.path.split("?", 1)[0]
            data = self._read_json()
            if path == "/api/parse":
                res = controller.parse(str(data.get("move", "")))
            elif path == "/api/move":
                res = controller.opp_move(str(data.get("move", "")))
            elif path == "/api/undo":
                res = controller.undo()
            elif path == "/api/clock":
                res = controller.set_clock(str(data.get("side", "ours")), str(data.get("value", "")))
            elif path == "/api/settings":
                res = controller.update_settings(data)
            elif path == "/api/new":
                color = data.get("color")
                res = controller.new_game(str(color) if color else None)
            elif path == "/api/move-now":
                res = controller.move_now()
            else:
                self._send_json({"ok": False, "message": "Não encontrado."}, 404)
                return
            self._send_json(res)

    return Handler


def create_server(controller: ConsoleController, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(controller))
    httpd.daemon_threads = True
    return httpd


def run_web_console(args: argparse.Namespace) -> int:
    engine, session, movetime_override_ms, message = build_engine_and_session(args)
    controller = ConsoleController(engine, session, args, movetime_override_ms, message)
    try:
        httpd = create_server(controller, args.port)
    except OSError as err:
        engine.close()
        print(f"[ERRO] Não foi possível abrir a porta {args.port}: {err}. Use --port <outra>.", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    controller.start()
    print(f"  Console web SunTzu ativo em {url}  (Ctrl+C para encerrar; estado salvo em {session.save_dir})")
    if message:
        print(f"  {message}")
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()

    def _graceful_exit(signum, frame):
        raise KeyboardInterrupt

    # Fechar o terminal (SIGHUP) ou 'kill' (SIGTERM) também encerra o motor de forma limpa
    for sig_name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, sig_name):
            signal.signal(getattr(signal, sig_name), _graceful_exit)
    try:
        httpd.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\n  [ENCERRANDO CONSOLE — Estado salvo em partidas/ultima.fen]")
    finally:
        httpd.server_close()
        controller.close()
    return 0
