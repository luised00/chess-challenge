#!/usr/bin/env python3
"""
Console do Operador Anti-Crash — Motor SunTzu (Chess Challenge III ICEV 2026)

Recursos:
- Entrada de lances em UCI (e2e4) ou SAN em Português (Cf3, Cxf7, Bb5, Td1, Dd4, Rf1, O-O) e Inglês (Nf3, Qxf7).
- Rejeição imediata de lances ilegais ou ambíguos antes de alterar o estado.
- Confirmação visual com diagrama ASCII antes de enviar ao motor.
- Saída do lance do motor em destaque (banner grande) com alertas de CAPTURA, ROQUE, EN PASSANT, PROMOÇÃO e XEQUE.
- Comando 'u' para desfazer o último lance digitado errado.
- Relógio físico integrado com sincronização rápida ('t mm:ss').
- Suporte completo a Ponder ('go ponder' -> 'ponderhit' no acerto ou 'stop' + nova busca no erro).
- Autosave automático de FEN (com histórico de lances e relógio) e PGN a cada lance em 'partidas/'.
- Recuperação instantânea via '--resume partidas/ultima.fen'.
- Watchdog com timeout de 3 s no 'isready' -> 'readyok': reinicia o motor e retoma a partida automaticamente.
- Exibição da Doutrina SunTzu ('info string SunTzu: perfil, modo, motivo') e alertas de repetição tripla / 50 lances.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from typing import Optional

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)
VENV_SITE = os.path.join(ROOT_DIR, ".venv", "lib")
if os.path.isdir(VENV_SITE):
    for d in os.listdir(VENV_SITE):
        sp = os.path.join(VENV_SITE, d, "site-packages")
        if os.path.isdir(sp) and sp not in sys.path:
            sys.path.insert(0, sp)

import chess
import chess.pgn

PT_PIECE_NAMES = {
    chess.PAWN: "Peão",
    chess.KNIGHT: "Cavalo",
    chess.BISHOP: "Bispo",
    chess.ROOK: "Torre",
    chess.QUEEN: "Dama",
    chess.KING: "Rei",
}

PT_PROMO_NAMES = {
    chess.QUEEN: "DAMA",
    chess.ROOK: "TORRE",
    chess.BISHOP: "BISPO",
    chess.KNIGHT: "CAVALO",
}

# Mapa de peças em português (C=Cavalo, B=Bispo, T=Torre, D=Dama, R=Rei) para inglês (N, B, R, Q, K)
PT_TO_EN_PIECE = {
    "C": "N",
    "B": "B",
    "T": "R",
    "D": "Q",
    "R": "K",
}


def translate_pt_san_to_en(text: str) -> str:
    """Converte notação algébrica em português (ex: Cxf7+, Td1, e8=D, 0-0) para SAN inglês."""
    s = text.strip()
    if not s:
        return s

    # Roque com zeros
    if s in ("0-0", "O-O", "o-o"):
        return "O-O"
    if s in ("0-0-0", "O-O-O", "o-o-o"):
        return "O-O-O"

    # Promoção em português no final (ex: e8=D, exd8=C+, e8D)
    s = re.sub(
        r"=([CBTDR])([+#]?)$",
        lambda m: "=" + PT_TO_EN_PIECE[m.group(1)] + m.group(2),
        s,
    )

    # Peça inicial maiúscula em português (C, B, T, D, R) seguida de coluna/linha/captura
    if len(s) >= 2 and s[0] in PT_TO_EN_PIECE:
        return PT_TO_EN_PIECE[s[0]] + s[1:]

    return s


def parse_user_move(board: chess.Board, raw_input: str) -> chess.Move:
    """
    Interpreta um lance digitado pelo operador em UCI (e2e4, e7e8q), SAN Inglês (Nf3, exd5)
    ou SAN Português (Cf3, Cxf7, Td1, Dd4, Rf1, e8=D).
    Lança ValueError se o lance for inválido, ilegal ou ambíguo.
    """
    s = raw_input.strip()
    if not s:
        raise ValueError("Lance vazio.")

    # 1. Tenta UCI direto (ex: e2e4, e7e8q)
    if re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbnQRBN]?", s):
        try:
            move = chess.Move.from_uci(s.lower())
            if move in board.legal_moves:
                return move
            # Verifica se é promoção sem letra (ex: peão chegando na 8ª/1ª fila)
            for promo in (chess.QUEEN,):
                pm = chess.Move(move.from_square, move.to_square, promotion=promo)
                if pm in board.legal_moves:
                    return pm
            raise ValueError(f"Lance UCI '{s}' é ilegal na posição atual.")
        except ValueError as e:
            raise ValueError(str(e)) from e

    # 2. Tenta SAN em Português traduzido para Inglês (ex: Cf3 -> Nf3, Td1 -> Rd1, e8=D -> e8=Q)
    candidates_san = []
    pt_translated = translate_pt_san_to_en(s)
    candidates_san.append(pt_translated)
    if s != pt_translated:
        candidates_san.append(s)

    for san_cand in candidates_san:
        try:
            move = board.parse_san(san_cand)
            if move in board.legal_moves:
                return move
        except chess.IllegalMoveError as e:
            raise ValueError(f"Lance '{s}' é ilegal na posição atual.") from e
        except chess.AmbiguousMoveError as e:
            raise ValueError(f"Lance '{s}' é ambíguo (especifique a coluna ou linha de origem).") from e
        except chess.InvalidMoveError:
            continue

    raise ValueError(f"Sintaxe de lance inválida ou ilegal: '{s}'. Use ex: e2e4, e4, Cf3, Cxf7, O-O.")


def describe_move_pt(board: chess.Board, move: chess.Move) -> dict[str, object]:
    """Retorna descrição detalhada e alertas de operação física para um lance legal."""
    uci_str = move.uci()
    san_str = board.san(move)
    from_sq = chess.square_name(move.from_square)
    to_sq = chess.square_name(move.to_square)
    piece = board.piece_at(move.from_square)
    piece_name = PT_PIECE_NAMES.get(piece.piece_type, "Peça") if piece else "Peça"

    is_capture = board.is_capture(move)
    is_ep = board.is_en_passant(move)
    is_castling = board.is_castling(move)
    is_kingside_castle = board.is_kingside_castling(move)
    is_promotion = move.promotion is not None
    promo_name = PT_PROMO_NAMES.get(move.promotion, "DAMA") if move.promotion else ""

    board_after = board.copy()
    board_after.push(move)
    gives_check = board_after.is_check()
    is_mate = board_after.is_checkmate()

    alerts: list[str] = []
    if is_castling:
        side_str = "ROQUE MENOR (ALA DO REI)" if is_kingside_castle else "ROQUE MAIOR (ALA DA DAMA)"
        spoken = f"{side_str}: Rei {from_sq} -> {to_sq}"
        alerts.append(f"ATENÇÃO: {side_str} — MOVA O REI E A TORRE NO TABULEIRO!")
    else:
        action = "captura em" if is_capture else "para"
        spoken = f"{piece_name} de {from_sq} {action} {to_sq}"

    if is_ep:
        ep_victim_sq = chess.square(chess.square_file(move.to_square), chess.square_rank(move.from_square))
        alerts.append(
            f"ATENÇÃO: CAPTURA EN PASSANT! Remova o peão adversário da casa {chess.square_name(ep_victim_sq)}!"
        )
    elif is_capture:
        captured_piece = board.piece_at(move.to_square)
        cap_name = PT_PIECE_NAMES.get(captured_piece.piece_type, "peça") if captured_piece else "peça"
        alerts.append(f"ATENÇÃO: CAPTURA ({cap_name} em {to_sq})!")

    if is_promotion:
        alerts.append(f"ATENÇÃO: PROMOVE A {promo_name} NA CASA {to_sq.upper()}!")
        spoken += f" (PROMOVE A {promo_name})"

    if is_mate:
        alerts.append("XEQUE-MATE! PARTIDA ENCERRADA!")
    elif gives_check:
        alerts.append("XEQUE AO REI ADVERSÁRIO!")

    return {
        "uci": uci_str,
        "san": san_str,
        "from_sq": from_sq,
        "to_sq": to_sq,
        "spoken": spoken,
        "alerts": alerts,
        "is_capture": is_capture,
        "is_ep": is_ep,
        "is_castling": is_castling,
        "is_promotion": is_promotion,
        "gives_check": gives_check,
        "is_mate": is_mate,
    }


def format_ascii_board(board: chess.Board, last_move: Optional[chess.Move] = None) -> str:
    """Renderiza o tabuleiro ASCII com coordenadas a-h / 1-8 e destaque opcional da última jogada."""
    lines = ["    +------------------------+"]
    for rank in range(7, -1, -1):
        row_items = []
        for file in range(8):
            sq = chess.square(file, rank)
            p = board.piece_at(sq)
            sym = p.symbol() if p else "."
            if last_move and sq in (last_move.from_square, last_move.to_square):
                row_items.append(f"[{sym}]")
            else:
                row_items.append(f" {sym} ")
        lines.append(f"  {rank + 1} |{''.join(row_items)}|")
    lines.append("    +------------------------+")
    lines.append("      a  b  c  d  e  f  g  h")
    turn_str = "BRANCAS (w)" if board.turn == chess.WHITE else "PRETAS (b)"
    lines.append(f"  Vez: {turn_str} | Lance: {board.fullmove_number} | Regra 50 lances: {board.halfmove_clock}/100")
    return "\n".join(lines)


def format_our_move_banner(info: dict[str, object]) -> str:
    """Formata o banner em destaque do nosso lance para leitura rápida pelo Operador C."""
    uci_up = str(info["uci"]).upper()
    san_str = str(info["san"])
    spoken = str(info["spoken"])
    alerts = list(info["alerts"])  # type: ignore

    border = "=" * 68
    out = [
        "",
        border,
        f"  >>> NOSSO LANCE:  {uci_up}   ({san_str}) <<<",
        f"  >>> DITAR EM VOZ ALTA: {spoken.upper()} <<<",
    ]
    for alert in alerts:
        out.append(f"  *** {alert} ***")
    out.append(border)
    return "\n".join(out)


def check_rule_alerts(board: chess.Board, last_eval_cp: int, is_our_turn: bool) -> list[str]:
    """
    Verifica alertas de repetição tripla e regra dos 50 lances no tabuleiro físico:
    - Se a posição atual já permite reivindicar repetição tripla ou 50 lances;
    - Se algum lance legal permite reivindicar;
    - Se estamos em desvantagem (last_eval_cp < -50), sugere reivindicar imediatamente.
    """
    alerts: list[str] = []

    rep3_now = board.is_repetition(3)
    fifty_now = board.is_fifty_moves()
    can_claim_3fold = board.can_claim_threefold_repetition()
    can_claim_50 = board.can_claim_fifty_moves()

    who = "NÓS PODEMOS" if is_our_turn else "O ADVERSÁRIO PODE"

    if rep3_now:
        alerts.append(f"[REGRA - REPETIÇÃO TRIPLA NO TABULEIRO] {who} REIVINDICAR EMPATE AGORA!")
    elif can_claim_3fold:
        alerts.append(
            f"[REGRA - REPETIÇÃO TRIPLA DISPONÍVEL] {who} REIVINDICAR EMPATE APÓS ANUNCIAR O LANCE QUE REPETE!"
        )
    elif board.is_repetition(2):
        alerts.append("[AVISO DE REPETIÇÃO] Posição ocorreu pela 2ª vez (próxima repetição permite empate).")

    if fifty_now:
        alerts.append(f"[REGRA - 50 LANCES NO TABULEIRO] {who} REIVINDICAR EMPATE AGORA ({board.halfmove_clock} meios-lances)!")
    elif can_claim_50:
        alerts.append(f"[REGRA - 50 LANCES DISPONÍVEL] {who} REIVINDICAR EMPATE NO PRÓXIMO LANCE!")
    elif board.halfmove_clock >= 80:
        alerts.append(
            f"[AVISO 50 LANCES] Contador em {board.halfmove_clock}/100 meios-lances sem captura ou movimento de peão."
        )

    if (rep3_now or fifty_now or can_claim_3fold or can_claim_50) and is_our_turn:
        if last_eval_cp < -50:
            alerts.append(
                f">>> RECOMENDAÇÃO SUNTZU (Avaliação {last_eval_cp} cp): ESTAMOS EM DESVANTAGEM — REIVINDIQUE O EMPATE! <<<"
            )
        elif last_eval_cp > 100:
            alerts.append(
                f">>> RECOMENDAÇÃO SUNTZU (Avaliação +{last_eval_cp} cp): ESTAMOS GANHOS — NÃO REIVINDIQUE EMPATE! <<<"
            )

    return alerts


def format_clock_ms(ms: int) -> str:
    ms = max(0, int(ms))
    total_sec = ms // 1000
    m = total_sec // 60
    s = total_sec % 60
    return f"{m:02d}:{s:02d}"


def parse_clock_str(clock_str: str) -> int:
    """Converte 'mm:ss' ou 'ss' para milissegundos."""
    s = clock_str.strip()
    if ":" in s:
        parts = s.split(":")
        if len(parts) != 2:
            raise ValueError(f"Formato de tempo inválido: '{clock_str}' (use mm:ss)")
        mins = int(parts[0])
        secs = float(parts[1])
        if mins < 0 or secs < 0 or secs >= 60:
            raise ValueError(f"Valores de tempo fora da faixa: '{clock_str}'")
        return int(round((mins * 60 + secs) * 1000))
    return int(round(float(s) * 1000))


class WatchdogEngine:
    """
    Gerencia o processo UCI do motor SunTzu com:
    - Leitura assíncrona por fila (sem bloqueio infinito).
    - Watchdog de 3 segundos no 'isready' -> 'readyok'.
    - Reinicialização automática e restauração transparente de opções e posição em caso de falha/travamento.
    - Suporte completo a 'go ponder', 'ponderhit' e 'stop'.
    """

    def __init__(
        self,
        engine_path: str,
        options: dict[str, str],
        watchdog_timeout: float = 3.0,
    ):
        self.engine_path = engine_path
        self.options = dict(options)
        self.watchdog_timeout = watchdog_timeout
        self.proc: Optional[subprocess.Popen[str]] = None
        self.out_queue: queue.Queue[Optional[str]] = queue.Queue()
        self.reader_thread: Optional[threading.Thread] = None
        self.pondering = False
        self.ponder_move_uci: Optional[str] = None
        self.last_suntzu_info: str = "SunTzu: aguardando primeiro lance"
        self.last_eval_cp: int = 0
        self.restart_count: int = 0
        self._start_process()

    def _reader_loop(self, proc: subprocess.Popen[str], q: queue.Queue[Optional[str]]):
        assert proc.stdout is not None
        try:
            for line in proc.stdout:
                q.put(line.rstrip("\r\n"))
        except Exception:
            pass
        finally:
            q.put(None)

    def _start_process(self):
        self._kill_process()
        self.out_queue = queue.Queue()
        self.proc = subprocess.Popen(
            [self.engine_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self.reader_thread = threading.Thread(
            target=self._reader_loop, args=(self.proc, self.out_queue), daemon=True
        )
        self.reader_thread.start()
        self.pondering = False
        self.ponder_move_uci = None

        self._send_raw("uci")
        self._read_until("uciok", timeout=self.watchdog_timeout)
        for k, v in self.options.items():
            self._send_raw(f"setoption name {k} value {v}")
        self._send_raw("isready")
        self._read_until("readyok", timeout=self.watchdog_timeout)

    def _kill_process(self):
        if self.proc is not None:
            try:
                if self.proc.poll() is None:
                    self.proc.kill()
                    self.proc.wait(timeout=1.0)
            except Exception:
                pass
            self.proc = None
        self.pondering = False
        self.ponder_move_uci = None

    def _send_raw(self, cmd: str):
        if self.proc is None or self.proc.poll() is not None or self.proc.stdin is None:
            raise RuntimeError("Processo do motor não está ativo.")
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def _read_until(self, prefix: str, timeout: float) -> tuple[str, list[str]]:
        deadline = time.monotonic() + timeout
        lines: list[str] = []
        while True:
            rem = deadline - time.monotonic()
            if rem <= 0:
                raise TimeoutError(f"Timeout ({timeout:.1f}s) aguardando '{prefix}'")
            try:
                line = self.out_queue.get(timeout=rem)
            except queue.Empty as e:
                raise TimeoutError(f"Timeout ({timeout:.1f}s) aguardando '{prefix}'") from e

            if line is None:
                raise RuntimeError(f"Processo do motor encerrou inesperadamente aguardando '{prefix}'")

            lines.append(line)
            if "info string SunTzu:" in line:
                self.last_suntzu_info = line.replace("info string ", "", 1)
            m_cp = re.search(r"score cp (-?\d+)", line)
            if m_cp:
                self.last_eval_cp = int(m_cp.group(1))
            elif "score mate -" in line:
                self.last_eval_cp = -10000
            elif "score mate " in line:
                self.last_eval_cp = 10000

            if line.startswith(prefix):
                return line, lines

    def ensure_healthy(self) -> bool:
        """
        Envia 'isready' e exige 'readyok' dentro de watchdog_timeout (3s).
        Se falhar ou travar, reinicia o motor automaticamente e retorna False (indicando que reiniciou).
        """
        try:
            self._send_raw("isready")
            self._read_until("readyok", timeout=self.watchdog_timeout)
            return True
        except Exception as err:
            print(f"\n[WATCHDOG ALERTA] Motor não respondeu ({err}). Reiniciando motor automaticamente...")
            self.restart_count += 1
            self._start_process()
            print(f"[WATCHDOG OK] Motor reiniciado com sucesso (reinício #{self.restart_count}).")
            return False

    def set_option(self, name: str, value: str):
        self.stop_ponder_if_active()
        self.options[name] = value
        self.ensure_healthy()
        self._send_raw(f"setoption name {name} value {value}")
        self.ensure_healthy()

    def stop_ponder_if_active(self):
        if not self.pondering:
            return
        try:
            self._send_raw("stop")
            self._read_until("bestmove", timeout=self.watchdog_timeout)
        except Exception:
            self.restart_count += 1
            self._start_process()
        finally:
            self.pondering = False
            self.ponder_move_uci = None

    def start_ponder(
        self,
        start_fen: str,
        moves_uci: list[str],
        expected_opp_move_uci: str,
        wtime_ms: int,
        btime_ms: int,
    ):
        """Inicia busca 'go ponder' assumindo que o adversário jogará expected_opp_move_uci."""
        self.stop_ponder_if_active()
        self.ensure_healthy()
        ponder_moves = list(moves_uci) + [expected_opp_move_uci]
        pos_cmd = f"position fen {start_fen} moves {' '.join(ponder_moves)}"
        self._send_raw(pos_cmd)
        self._send_raw(f"go ponder wtime {max(1, int(wtime_ms))} btime {max(1, int(btime_ms))}")
        self.pondering = True
        self.ponder_move_uci = expected_opp_move_uci

    def search(
        self,
        start_fen: str,
        moves_uci: list[str],
        wtime_ms: int,
        btime_ms: int,
        movetime_override_ms: Optional[int] = None,
        search_timeout: float = 120.0,
    ) -> tuple[str, Optional[str], bool]:
        """
        Executa a busca na posição atual.
        Se estivermos em ponder e o último lance de moves_uci coincidir com ponder_move_uci,
        envia 'ponderhit' para aproveitar a busca adiantada!
        Retorna (bestmove_uci, ponder_uci, used_ponderhit).
        """
        used_ponderhit = False
        if (
            self.pondering
            and self.ponder_move_uci is not None
            and len(moves_uci) > 0
            and moves_uci[-1] == self.ponder_move_uci
            and movetime_override_ms is None
        ):
            try:
                self._send_raw("ponderhit")
                self.pondering = False
                self.ponder_move_uci = None
                bm_line, _ = self._read_until("bestmove", timeout=search_timeout)
                used_ponderhit = True
                parts = bm_line.split()
                bm = parts[1]
                ponder = parts[3] if len(parts) >= 4 and parts[2] == "ponder" else None
                return bm, ponder, used_ponderhit
            except Exception as err:
                print(f"\n[WATCHDOG ALERTA] Falha durante ponderhit ({err}). Reiniciando e buscando novamente...")
                self.restart_count += 1
                self._start_process()

        # Caso não seja ponderhit (ou se era ponder em outro lance), para o ponder primeiro
        if self.pondering:
            self.stop_ponder_if_active()

        # Verifica saúde antes da busca; se o motor morreu, reinicia e busca
        for attempt in range(2):
            try:
                self.ensure_healthy()
                if moves_uci:
                    self._send_raw(f"position fen {start_fen} moves {' '.join(moves_uci)}")
                else:
                    self._send_raw(f"position fen {start_fen}")

                if movetime_override_ms is not None:
                    self._send_raw(f"go movetime {max(1, int(movetime_override_ms))}")
                else:
                    self._send_raw(f"go wtime {max(1, int(wtime_ms))} btime {max(1, int(btime_ms))}")

                bm_line, _ = self._read_until("bestmove", timeout=search_timeout)
                parts = bm_line.split()
                bm = parts[1]
                ponder = parts[3] if len(parts) >= 4 and parts[2] == "ponder" else None
                return bm, ponder, used_ponderhit
            except Exception as err:
                if attempt == 0:
                    print(f"\n[WATCHDOG ALERTA] Erro/Timeout na busca ({err}). Reiniciando motor e retomando...")
                    self.restart_count += 1
                    self._start_process()
                else:
                    raise

        raise RuntimeError("Falha crítica ao obter lance do motor após reinício.")

    def close(self):
        self.stop_ponder_if_active()
        try:
            if self.proc and self.proc.poll() is None:
                self._send_raw("quit")
                self.proc.wait(timeout=1.5)
        except Exception:
            pass
        finally:
            self._kill_process()


class GameSession:
    """
    Mantém o estado completo da partida (tabuleiro, histórico de lances, relógios, autosave FEN/PGN)
    e coordena o fluxo entre os Operadores A, B e C e o WatchdogEngine.
    """

    def __init__(
        self,
        engine: WatchdogEngine,
        our_color: chess.Color = chess.WHITE,
        initial_time_ms: int = 25 * 60 * 1000,
        save_dir: str = os.path.join(ROOT_DIR, "partidas"),
        enable_ponder: bool = True,
        start_fen: str = chess.STARTING_FEN,
    ):
        self.engine = engine
        self.our_color = our_color
        self.initial_time_ms = initial_time_ms
        self.wtime_ms = initial_time_ms
        self.btime_ms = initial_time_ms
        self.save_dir = save_dir
        self.enable_ponder = enable_ponder
        self.start_fen = start_fen
        self.board = chess.Board(start_fen)
        self.moves_uci: list[str] = []
        self.clock_History: list[tuple[int, int]] = [(self.wtime_ms, self.btime_ms)]
        self.session_tag = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(self.save_dir, exist_ok=True)
        self.autosave()

    @property
    def our_time_ms(self) -> int:
        return self.wtime_ms if self.our_color == chess.WHITE else self.btime_ms

    @our_time_ms.setter
    def our_time_ms(self, val: int):
        v = max(1000, int(val))
        if self.our_color == chess.WHITE:
            self.wtime_ms = v
        else:
            self.btime_ms = v

    @property
    def opp_time_ms(self) -> int:
        return self.btime_ms if self.our_color == chess.WHITE else self.wtime_ms

    @opp_time_ms.setter
    def opp_time_ms(self, val: int):
        v = max(1000, int(val))
        if self.our_color == chess.WHITE:
            self.btime_ms = v
        else:
            self.wtime_ms = v

    def sync_our_clock(self, clock_str: str) -> int:
        """Sincroniza nosso relógio a partir da leitura física 'mm:ss'."""
        ms = parse_clock_str(clock_str)
        self.our_time_ms = ms
        if self.clock_History:
            self.clock_History[-1] = (self.wtime_ms, self.btime_ms)
        self.autosave()
        return ms

    def autosave(self):
        """
        Salva instantaneamente:
        - partidas/ultima.fen (primeira linha = FEN atual; segunda linha = metadados JSON para retomada completa com histórico)
        - partidas/ultima.pgn e partidas/partida_<timestamp>.pgn
        """
        os.makedirs(self.save_dir, exist_ok=True)
        fen_path = os.path.join(self.save_dir, "ultima.fen")
        meta = {
            "current_fen": self.board.fen(),
            "start_fen": self.start_fen,
            "moves_uci": self.moves_uci,
            "our_color": "white" if self.our_color == chess.WHITE else "black",
            "wtime_ms": self.wtime_ms,
            "btime_ms": self.btime_ms,
            "initial_time_ms": self.initial_time_ms,
        }
        tmp_fen = fen_path + ".tmp"
        with open(tmp_fen, "w", encoding="utf-8") as f:
            f.write(self.board.fen() + "\n")
            f.write("# SUNTZU_STATE " + json.dumps(meta, ensure_ascii=False) + "\n")
        os.replace(tmp_fen, fen_path)

        # Gera PGN completo
        game = chess.pgn.Game()
        game.headers["Event"] = "Chess Challenge III ICEV 2026"
        game.headers["Date"] = datetime.datetime.now().strftime("%Y.%m.%d")
        game.headers["White"] = "SunTzu" if self.our_color == chess.WHITE else "Oponente"
        game.headers["Black"] = "Oponente" if self.our_color == chess.WHITE else "SunTzu"
        game.headers["Result"] = self.board.result(claim_draw=True) if self.board.is_game_over(claim_draw=True) else "*"
        if self.start_fen != chess.STARTING_FEN:
            game.headers["SetUp"] = "1"
            game.headers["FEN"] = self.start_fen

        node: chess.pgn.GameNode = game
        b_tmp = chess.Board(self.start_fen)
        for m_uci in self.moves_uci:
            mv = chess.Move.from_uci(m_uci)
            node = node.add_variation(mv)
            b_tmp.push(mv)

        pgn_text = str(game) + "\n"
        pgn_latest = os.path.join(self.save_dir, "ultima.pgn")
        pgn_archive = os.path.join(self.save_dir, f"partida_{self.session_tag}.pgn")
        for p in (pgn_latest, pgn_archive):
            with open(p, "w", encoding="utf-8") as f:
                f.write(pgn_text)

    @classmethod
    def resume_from_file(
        cls,
        resume_path: str,
        engine: WatchdogEngine,
        default_color: Optional[chess.Color] = None,
        default_time_ms: int = 25 * 60 * 1000,
        save_dir: str = os.path.join(ROOT_DIR, "partidas"),
        enable_ponder: bool = True,
    ) -> "GameSession":
        """
        Retoma uma partida salva em menos de 1 segundo a partir de partidas/ultima.fen
        (ou qualquer arquivo FEN puro / estado SunTzu).
        """
        with open(resume_path, "r", encoding="utf-8") as f:
            lines = [ln.strip() for ln in f if ln.strip()]

        if not lines:
            raise ValueError(f"Arquivo de retomada vazio: {resume_path}")

        fen_line = lines[0]
        meta_json = None
        for ln in lines[1:]:
            if ln.startswith("# SUNTZU_STATE "):
                meta_json = json.loads(ln[len("# SUNTZU_STATE ") :])
                break

        if meta_json is not None:
            our_color = chess.WHITE if meta_json.get("our_color", "white") == "white" else chess.BLACK
            if default_color is not None:
                our_color = default_color
            start_fen = meta_json.get("start_fen", chess.STARTING_FEN)
            session = cls(
                engine=engine,
                our_color=our_color,
                initial_time_ms=int(meta_json.get("initial_time_ms", default_time_ms)),
                save_dir=save_dir,
                enable_ponder=enable_ponder,
                start_fen=start_fen,
            )
            session.board = chess.Board(start_fen)
            session.moves_uci = []
            for m_uci in meta_json.get("moves_uci", []):
                mv = chess.Move.from_uci(m_uci)
                session.board.push(mv)
                session.moves_uci.append(m_uci)
            session.wtime_ms = int(meta_json.get("wtime_ms", default_time_ms))
            session.btime_ms = int(meta_json.get("btime_ms", default_time_ms))
            session.clock_History = [(session.wtime_ms, session.btime_ms)]
            session.autosave()
            return session

        # Fallback: arquivo contendo apenas 1 linha de FEN puro
        board = chess.Board(fen_line)
        our_color = default_color if default_color is not None else board.turn
        session = cls(
            engine=engine,
            our_color=our_color,
            initial_time_ms=default_time_ms,
            save_dir=save_dir,
            enable_ponder=enable_ponder,
            start_fen=fen_line,
        )
        return session

    def apply_opponent_move(self, move: chess.Move):
        """Registra o lance confirmado do adversário no tabuleiro e salva."""
        if self.board.turn == self.our_color:
            raise ValueError("Não é a vez do adversário.")
        if move not in self.board.legal_moves:
            raise ValueError(f"Lance ilegal: {move.uci()}")
        self.board.push(move)
        self.moves_uci.append(move.uci())
        self.clock_History.append((self.wtime_ms, self.btime_ms))
        self.autosave()

    def play_our_move(
        self, movetime_override_ms: Optional[int] = None
    ) -> tuple[chess.Move, dict[str, object], bool, int]:
        """
        Solicita o lance ao motor (usando ponderhit se aplicável), atualiza o tabuleiro,
        desconta o tempo gasto + overhead físico, faz autosave e inicia o próximo ponder.
        Retorna (move, move_info, used_ponderhit, elapsed_ms).
        """
        if self.board.turn != self.our_color:
            raise ValueError("Não é a nossa vez de jogar.")

        t0 = time.monotonic()
        bm_uci, ponder_uci, used_ponderhit = self.engine.search(
            start_fen=self.start_fen,
            moves_uci=self.moves_uci,
            wtime_ms=self.wtime_ms,
            btime_ms=self.btime_ms,
            movetime_override_ms=movetime_override_ms,
        )
        elapsed_ms = int(round((time.monotonic() - t0) * 1000))

        move = chess.Move.from_uci(bm_uci)
        if move not in self.board.legal_moves:
            raise RuntimeError(f"Motor retornou lance ilegal: {bm_uci}")

        info = describe_move_pt(self.board, move)
        self.board.push(move)
        self.moves_uci.append(bm_uci)

        # Desconta tempo de pensamento + estimativa de operação física
        phys_overhead = int(self.engine.options.get("PhysicalBoardOverhead", "7000"))
        self.our_time_ms = max(1000, self.our_time_ms - elapsed_ms - phys_overhead)
        self.clock_History.append((self.wtime_ms, self.btime_ms))
        self.autosave()

        # Inicia Ponder no lance esperado do adversário se a partida continuar
        if self.enable_ponder and ponder_uci and not self.board.is_game_over(claim_draw=True):
            try:
                ponder_move = chess.Move.from_uci(ponder_uci)
                if ponder_move in self.board.legal_moves:
                    self.engine.start_ponder(
                        start_fen=self.start_fen,
                        moves_uci=self.moves_uci,
                        expected_opp_move_uci=ponder_uci,
                        wtime_ms=self.wtime_ms,
                        btime_ms=self.btime_ms,
                    )
            except Exception:
                pass

        return move, info, used_ponderhit, elapsed_ms

    def undo_last(self) -> int:
        """
        Desfaz o último par de lances (lance do adversário + nossa resposta) ou o último lance
        se for nossa vez, parando o ponder e atualizando o autosave.
        Retorna quantos meios-lances foram desfeitos.
        """
        self.engine.stop_ponder_if_active()
        if not self.moves_uci:
            return 0

        # Se estamos na vez do adversário e já jogamos, desfaz o nosso lance e o lance anterior do adversário
        plies_to_undo = 2 if (self.board.turn != self.our_color and len(self.moves_uci) >= 2) else 1
        for _ in range(plies_to_undo):
            if self.moves_uci:
                self.board.pop()
                self.moves_uci.pop()
                if len(self.clock_History) > 1:
                    self.clock_History.pop()

        self.wtime_ms, self.btime_ms = self.clock_History[-1]
        self.autosave()
        return plies_to_undo


def detect_default_hardware() -> tuple[int, int]:
    """Calcula Threads (núcleos físicos) e Hash (<= 25% da RAM, limitado a 2048 MB)."""
    cpus = os.cpu_count() or 4
    phys_cores = max(1, cpus // 2)
    hash_mb = 512
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    ram_mb = kb // 1024
                    hash_mb = min(2048, max(64, (ram_mb // 4) & ~63))
                    break
    except Exception:
        pass
    return phys_cores, hash_mb


def build_arg_parser() -> argparse.ArgumentParser:
    phys_cores, default_hash = detect_default_hardware()
    p = argparse.ArgumentParser(
        description="Console do Operador Anti-Crash — Motor SunTzu (Chess Challenge III ICEV 2026)"
    )
    p.add_argument(
        "--engine",
        default=os.path.join(ROOT_DIR, "bin", "suntzu-native"),
        help="Caminho do binário UCI do motor SunTzu",
    )
    p.add_argument(
        "--color",
        choices=["white", "black", "brancas", "pretas"],
        default="white",
        help="Nossa cor na partida (white/brancas ou black/pretas)",
    )
    p.add_argument(
        "--time-min",
        type=float,
        default=25.0,
        help="Tempo inicial por jogador em minutos (padrão: 25)",
    )
    p.add_argument(
        "--overhead-ms",
        type=int,
        default=7000,
        help="PhysicalBoardOverhead em ms descontado por lance (padrão: 7000)",
    )
    p.add_argument(
        "--panic-sec",
        type=int,
        default=120,
        help="PanicReserve em segundos (padrão: 120)",
    )
    p.add_argument(
        "--threads",
        type=int,
        default=phys_cores,
        help=f"Número de threads da CPU (padrão detectado: {phys_cores})",
    )
    p.add_argument(
        "--hash",
        type=int,
        default=default_hash,
        help=f"Tamanho da tabela Hash em MB (padrão <=25%% RAM: {default_hash})",
    )
    p.add_argument(
        "--profile",
        choices=["auto", "forte", "medio", "fraco"],
        default="auto",
        help="Perfil inicial do oponente (OpponentProfile)",
    )
    p.add_argument(
        "--time-profile",
        choices=["normal", "rapido"],
        default="normal",
        help="Perfil de controle de tempo (normal=25min, rapido=curto)",
    )
    p.add_argument(
        "--no-book",
        action="store_true",
        help="Desativa o livro de aberturas Polyglot (OwnBook=false)",
    )
    p.add_argument(
        "--no-ponder",
        action="store_true",
        help="Desativa o pensamento no tempo do adversário (Ponder)",
    )
    p.add_argument(
        "--eco",
        action="store_true",
        help="Modo de economia de bateria (reduz Threads para metade, Hash=256MB e desliga Ponder)",
    )
    p.add_argument(
        "--no-confirm",
        action="store_true",
        help="Não exige Enter de confirmação após digitar o lance adversário (para testes rápidos)",
    )
    p.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Retoma partida salva de um arquivo FEN (ex: --resume partidas/ultima.fen)",
    )
    p.add_argument(
        "--save-dir",
        type=str,
        default=os.path.join(ROOT_DIR, "partidas"),
        help="Diretório de autosave para FEN e PGN (padrão: partidas/)",
    )
    p.add_argument(
        "--simple",
        action="store_true",
        help="Usa modo texto simples (ASCII sem cores) em vez do painel TUI completo",
    )
    return p


def run_interactive_console(args: argparse.Namespace) -> int:
    from tools.operator_console.tui import (
        ALERT_BG,
        BOLD,
        BRIGHT_GOLD,
        CYAN,
        GOLD,
        JADE,
        RESET,
        render_dashboard,
    )

    threads = max(1, args.threads // 2) if args.eco else args.threads
    hash_mb = min(256, args.hash) if args.eco else args.hash
    enable_ponder = False if (args.eco or args.no_ponder) else True
    is_tty = sys.stdout.isatty() and not args.simple

    book_path = os.path.join(ROOT_DIR, "books", "suntzu_310.bin")
    syzygy_dir = os.path.join(ROOT_DIR, "syzygy")

    options: dict[str, str] = {
        "Threads": str(threads),
        "Hash": str(hash_mb),
        "Ponder": "true" if enable_ponder else "false",
        "PhysicalBoardOverhead": str(args.overhead_ms),
        "PanicReserve": str(args.panic_sec),
        "TimeProfile": args.time_profile,
        "OwnBook": "false" if args.no_book else "true",
        "BookFile": book_path,
        "SunTzu": "true",
        "OpponentProfile": args.profile,
    }
    if os.path.isdir(syzygy_dir):
        options["SyzygyPath"] = syzygy_dir

    our_color = chess.WHITE if args.color in ("white", "brancas") else chess.BLACK
    initial_ms = int(round(args.time_min * 60 * 1000))

    engine = WatchdogEngine(args.engine, options=options, watchdog_timeout=3.0)

    status_flash = ""
    if args.resume:
        session = GameSession.resume_from_file(
            args.resume,
            engine=engine,
            default_color=our_color if "--color" in sys.argv else None,
            default_time_ms=initial_ms,
            save_dir=args.save_dir,
            enable_ponder=enable_ponder,
        )
        status_flash = (
            f"[RETOMADA OK] Posição restaurada de '{args.resume}' ({len(session.moves_uci)} meios-lances)."
        )
    else:
        session = GameSession(
            engine=engine,
            our_color=our_color,
            initial_time_ms=initial_ms,
            save_dir=args.save_dir,
            enable_ponder=enable_ponder,
        )

    last_our_move_info: Optional[dict[str, object]] = None
    last_origin_tag = ""
    last_used_ponderhit = False
    last_from_book = False

    try:
        while True:
            r_alerts = check_rule_alerts(
                session.board, engine.last_eval_cp, is_our_turn=(session.board.turn == session.our_color)
            )

            # Se é a nossa vez e o jogo ainda não acabou, o motor calcula e joga imediatamente
            if session.board.turn == session.our_color and not session.board.is_game_over(claim_draw=True):
                if is_tty:
                    print(
                        render_dashboard(
                            board=session.board,
                            our_color=session.our_color,
                            our_time_ms=session.our_time_ms,
                            opp_time_ms=session.opp_time_ms,
                            suntzu_info=engine.last_suntzu_info,
                            last_eval_cp=engine.last_eval_cp,
                            last_our_move_info=last_our_move_info,
                            last_origin_tag=last_origin_tag,
                            ponder_move_uci=engine.ponder_move_uci if engine.pondering else None,
                            used_ponderhit=last_used_ponderhit,
                            from_book=last_from_book,
                            rule_alerts=r_alerts,
                            status_flash="General Sun Tzu meditando sobre o próximo golpe...",
                            clear_screen=True,
                        )
                    )
                else:
                    print("\n  [MOTOR PENSANDO...]")

                mv, info, hit, elapsed_ms = session.play_our_move()
                last_our_move_info = info
                last_used_ponderhit = hit
                last_from_book = elapsed_ms < 15 and len(session.moves_uci) <= 16 and not hit
                if hit:
                    last_origin_tag = f"PONDERHIT ({elapsed_ms} ms)"
                elif last_from_book:
                    last_origin_tag = f"LIVRO 3-1-0 ({elapsed_ms} ms)"
                else:
                    last_origin_tag = f"BUSCA ({elapsed_ms} ms)"

                if not is_tty:
                    print(format_our_move_banner(info))
                continue

            # Renderiza o Dashboard TUI (ou ASCII simples se --simple)
            if not args.simple:
                print(
                    render_dashboard(
                        board=session.board,
                        our_color=session.our_color,
                        our_time_ms=session.our_time_ms,
                        opp_time_ms=session.opp_time_ms,
                        suntzu_info=engine.last_suntzu_info,
                        last_eval_cp=engine.last_eval_cp,
                        last_our_move_info=last_our_move_info,
                        last_origin_tag=last_origin_tag,
                        ponder_move_uci=engine.ponder_move_uci if engine.pondering else None,
                        used_ponderhit=last_used_ponderhit,
                        from_book=last_from_book,
                        rule_alerts=r_alerts,
                        status_flash=status_flash,
                        clear_screen=is_tty,
                    )
                )
            else:
                last_mv = chess.Move.from_uci(session.moves_uci[-1]) if session.moves_uci else None
                print("\n" + format_ascii_board(session.board, last_move=last_mv))
                if last_our_move_info:
                    print(format_our_move_banner(last_our_move_info))
                if status_flash:
                    print(f"  {status_flash}")

            status_flash = ""

            if session.board.is_game_over(claim_draw=True):
                res = session.board.result(claim_draw=True)
                print(f"\n  {GOLD}{BOLD}═══ FIM DE PARTIDA! Resultado: {res} ═══{RESET}")
                cmd_end = input("  Digite 'u' para desfazer último lance ou Enter/quit para sair: ").strip()
                if cmd_end.lower() == "u":
                    undone = session.undo_last()
                    last_our_move_info = None
                    status_flash = f"[DESFEITO] {undone} meio(s)-lance(s) revertido(s)."
                    print(f"  {status_flash}")
                    continue
                break

            # Vez do adversário: aguarda comando do Operador B
            prompt_str = (
                f"\n  {GOLD}{BOLD}⚔ Comando / Lance do adversário{RESET} "
                f"{CYAN}(ex: e4, Cf6, Cxf7, 0-0, u, t 18:30){RESET}: "
            )
            raw = input(prompt_str).strip()
            if not raw:
                continue

            low = raw.lower()
            if low in ("quit", "exit", "q", "sair"):
                break

            if low in ("ajuda", "help", "?"):
                status_flash = (
                    "Comandos: lance (e4, Cf6, Cxf7, 0-0, e8=D) | u=desfazer | t mm:ss=nosso relógio | "
                    "t opp mm:ss=relógio oponente | perfil fraco|medio|forte|auto | rapido|normal | fen | quit"
                )
                print(f"  {status_flash}")
                continue

            if low == "u":
                undone = session.undo_last()
                last_our_move_info = None
                status_flash = f"[DESFEITO] {undone} meio(s)-lance(s) revertido(s)."
                print(f"  {status_flash}")
                continue

            if low == "fen":
                status_flash = f"FEN atual: {session.board.fen()}"
                print(f"  {status_flash}")
                continue

            if low in ("rapido", "normal"):
                engine.set_option("TimeProfile", low)
                if low == "rapido":
                    engine.set_option("PhysicalBoardOverhead", "10000")
                    engine.set_option("PanicReserve", "180")
                else:
                    engine.set_option("PhysicalBoardOverhead", str(args.overhead_ms))
                    engine.set_option("PanicReserve", str(args.panic_sec))
                status_flash = f"[MODO DE TEMPO] TimeProfile ajustado para '{low.upper()}'."
                print(f"  {status_flash}")
                continue

            if low.startswith("t opp "):
                try:
                    ms = parse_clock_to_ms(raw[6:].strip())
                    session.opp_time_ms = ms
                    session.autosave()
                    status_flash = f"[RELÓGIO SINCRONIZADO] Tempo do adversário ajustado para {format_clock_ms(ms)}."
                    print(f"  {status_flash}")
                except ValueError as err:
                    status_flash = f"[ERRO DE RELÓGIO] {err}"
                    print(f"  {status_flash}")
                continue

            if low.startswith("t "):
                try:
                    ms = session.sync_our_clock(raw[2:].strip())
                    status_flash = f"[RELÓGIO SINCRONIZADO] Nosso tempo ajustado para {format_clock_ms(ms)}."
                    print(f"  {status_flash}")
                except ValueError as err:
                    status_flash = f"[ERRO DE RELÓGIO] {err}"
                    print(f"  {status_flash}")
                continue

            if low.startswith("perfil "):
                prof = low.split(maxsplit=1)[1]
                if prof in ("auto", "forte", "medio", "fraco"):
                    engine.set_option("OpponentProfile", prof)
                    status_flash = f"[PERFIL ATUALIZADO] OpponentProfile = {prof}"
                    print(f"  {status_flash}")
                else:
                    status_flash = "[ERRO] Use: perfil auto | forte | medio | fraco"
                    print(f"  {status_flash}")
                continue

            # Interpreta e valida o lance do adversário
            try:
                opp_move = parse_user_move(session.board, raw)
            except ValueError as err:
                status_flash = f"[LANCE REJEITADO] {err}"
                print(f"  {ALERT_BG} {status_flash} {RESET}")
                continue

            opp_info = describe_move_pt(session.board, opp_move)
            if not args.no_confirm:
                if is_tty:
                    print(
                        render_dashboard(
                            board=session.board,
                            our_color=session.our_color,
                            our_time_ms=session.our_time_ms,
                            opp_time_ms=session.opp_time_ms,
                            suntzu_info=engine.last_suntzu_info,
                            last_eval_cp=engine.last_eval_cp,
                            last_our_move_info=last_our_move_info,
                            last_origin_tag=last_origin_tag,
                            ponder_move_uci=engine.ponder_move_uci if engine.pondering else None,
                            used_ponderhit=last_used_ponderhit,
                            from_book=last_from_book,
                            rule_alerts=r_alerts,
                            pending_opp_move=opp_move,
                            pending_opp_info=opp_info,
                            clear_screen=True,
                        )
                    )
                else:
                    print(f"  CONFIRMAR LANCE DO ADVERSÁRIO: {opp_info['uci']} ({opp_info['san']}) — {opp_info['spoken']}")

                ans = input(
                    f"  {BRIGHT_GOLD}{BOLD}? Confirmar lance '{opp_info['san']}' ({opp_info['spoken']})? "
                    f"[Enter = SIM / 'n' = cancelar]: {RESET}"
                ).strip().lower()
                if ans not in ("", "s", "sim", "y", "yes"):
                    status_flash = "[CANCELADO] Digite o lance novamente."
                    print(f"  {status_flash}")
                    continue

            session.apply_opponent_move(opp_move)

    except (EOFError, KeyboardInterrupt):
        print("\n  [ENCERRANDO CONSOLE — Estado salvo em partidas/ultima.fen]")
    finally:
        engine.close()

    return 0


if __name__ == "__main__":
    parser = build_arg_parser()
    sys.exit(run_interactive_console(parser.parse_args()))
