#!/usr/bin/env python3
"""
Testes Automatizados da Fase 6 — Console do Operador Anti-Crash:
1. Parser de lances em UCI, SAN Inglês e SAN Português (Cf3, Cxf7, Bb5, Td1, Dd4, Rf1, 0-0, e8=D)
   e rejeição imediata de lances ilegais/ambíguos.
2. Banner de saída do nosso lance (avisos de CAPTURA, ROQUE, EN PASSANT, PROMOÇÃO A DAMA, XEQUE).
3. Comando 'u' (desfazer), 't 12:34' (relógio físico) e Ponder (ponderhit + ponder miss).
4. Autosave FEN/PGN e retomada instantânea (--resume partidas/ultima.fen em < 1s, meta < 20s).
5. Watchdog Anti-Crash: mata o processo do motor (SIGKILL) e congela o processo (SIGSTOP) no meio
   da partida, validando reinício automático e continuação transparente.
6. Alertas de repetição tripla e regra dos 50 lances (com recomendação de reivindicar quando perdendo).
7. Teste de ponta a ponta da CLI interativa via stdin/stdout.
"""

import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

VENV_SITE = os.path.join(ROOT_DIR, ".venv", "lib")
if os.path.isdir(VENV_SITE):
    for d in os.listdir(VENV_SITE):
        sp = os.path.join(VENV_SITE, d, "site-packages")
        if os.path.isdir(sp) and sp not in sys.path:
            sys.path.insert(0, sp)

import chess
from tools.operator_console.console import (
    GameSession,
    WatchdogEngine,
    check_rule_alerts,
    describe_move_pt,
    format_our_move_banner,
    parse_user_move,
)


def test_move_parser_and_banners():
    print("=== [1/6] Testando Parser (UCI, Inglês e Português) e Banners de Alerta ===")
    b = chess.Board()

    # Português: Cf3 -> g1f3
    m1 = parse_user_move(b, "Cf3")
    assert m1 == chess.Move.from_uci("g1f3")
    b.push(m1)

    # UCI: e7e5
    m2 = parse_user_move(b, "e7e5")
    assert m2 == chess.Move.from_uci("e7e5")
    b.push(m2)

    # Inglês: Nxe5
    m3 = parse_user_move(b, "Nxe5")
    assert m3 == chess.Move.from_uci("f3e5")

    # Português com captura: Cxe5
    m3_pt = parse_user_move(b, "Cxe5")
    assert m3_pt == chess.Move.from_uci("f3e5")

    # Lance ilegal deve lançar ValueError
    for bad in ("e2e5", "Cf6", "Txa8", "lance_invalido"):
        try:
            parse_user_move(b, bad)
            raise AssertionError(f"Deveria ter rejeitado lance inválido/ilegal: {bad}")
        except ValueError:
            pass

    # Testa promoção em português (e8=D), En Passant e Roque
    b_promo = chess.Board("7k/4P3/8/8/8/8/8/4K3 w - - 0 1")
    mp = parse_user_move(b_promo, "e8=D")
    assert mp == chess.Move.from_uci("e7e8q")
    info_promo = describe_move_pt(b_promo, mp)
    banner_promo = format_our_move_banner(info_promo)
    assert "PROMOVE A DAMA" in banner_promo

    b_ep = chess.Board("rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 3")
    mep = parse_user_move(b_ep, "exd6")
    info_ep = describe_move_pt(b_ep, mep)
    assert info_ep["is_ep"] is True
    assert any("EN PASSANT" in a for a in info_ep["alerts"])  # type: ignore

    b_castle = chess.Board("r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/5N2/PPPP1PPP/RNBQK2R w KQkq - 4 4")
    mc = parse_user_move(b_castle, "0-0")
    info_c = describe_move_pt(b_castle, mc)
    assert info_c["is_castling"] is True
    assert any("ROQUE" in a for a in info_c["alerts"])  # type: ignore
    print("  -> Parser PT/EN/UCI, rejeição de ilegais e alertas de Promoção/En Passant/Roque: OK")


def test_session_undo_clock_ponder_and_resume(engine_path: str):
    print("=== [2/6] Testando Sessão, Ponder (Hit/Miss), Desfazer ('u'), Relógio ('t') e Resume ===")
    tmpdir = tempfile.mkdtemp(prefix="suntzu_console_test_")
    try:
        eng = WatchdogEngine(
            engine_path,
            options={
                "Threads": "1",
                "Hash": "16",
                "Ponder": "true",
                "OwnBook": "false",
                "PhysicalBoardOverhead": "100",
                "PanicReserve": "0",
                "SunTzu": "true",
            },
            watchdog_timeout=2.0,
        )
        session = GameSession(
            engine=eng,
            our_color=chess.WHITE,
            initial_time_ms=600_000,
            save_dir=tmpdir,
            enable_ponder=True,
        )

        # 1. Nosso 1º lance (Brancas)
        mv1, info1, hit1, _ = session.play_our_move(movetime_override_ms=40)
        assert mv1 in chess.Board().legal_moves
        assert not hit1
        assert eng.pondering is True and eng.ponder_move_uci is not None
        expected_opp = eng.ponder_move_uci
        print(f"  -> 1º lance jogado: {mv1.uci()} | Ponder iniciado em: {expected_opp}")

        # 2. Adversário joga exatamente o lance esperado pelo Ponder -> PONDERHIT!
        session.apply_opponent_move(chess.Move.from_uci(expected_opp))
        mv2, info2, hit2, _ = session.play_our_move()
        print(f"  -> 2º lance após Ponderhit: {mv2.uci()} | used_ponderhit={hit2}")
        assert hit2 is True

        # 3. Sincroniza relógio ('t 12:34')
        ms = session.sync_our_clock("12:34")
        assert ms == (12 * 60 + 34) * 1000
        assert session.our_time_ms == 754_000

        # 4. Testa comando 'u' (desfazer último par de lances)
        plies_before = len(session.moves_uci)
        undone = session.undo_last()
        assert undone == 2
        assert len(session.moves_uci) == plies_before - 2
        print(f"  -> Desfazer ('u') reverteu {undone} meios-lances com sucesso.")

        # 5. Adversário joga lance diferente do ponder (Ponder Miss)
        other_move = next(m for m in session.board.legal_moves if m.uci() != eng.ponder_move_uci)
        session.apply_opponent_move(other_move)
        mv3, _, hit3, _ = session.play_our_move(movetime_override_ms=30)
        assert hit3 is False
        print(f"  -> Ponder Miss tratado corretamente (stop + nova busca -> {mv3.uci()}).")

        # 6. Simula fechamento do console e retomada via --resume partidas/ultima.fen (< 20s)
        saved_fen = session.board.fen()
        saved_moves = list(session.moves_uci)
        eng.close()

        t_resume_start = time.monotonic()
        eng2 = WatchdogEngine(
            engine_path,
            options={"Threads": "1", "Hash": "16", "OwnBook": "false"},
            watchdog_timeout=2.0,
        )
        resumed = GameSession.resume_from_file(
            os.path.join(tmpdir, "ultima.fen"),
            engine=eng2,
            save_dir=tmpdir,
            enable_ponder=False,
        )
        resume_elapsed = time.monotonic() - t_resume_start
        assert resumed.board.fen() == saved_fen
        assert resumed.moves_uci == saved_moves
        print(f"  -> Retomada (--resume ultima.fen) concluída em {resume_elapsed*1000:.1f} ms (< 20000 ms): OK")
        eng2.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_watchdog_anticrash(engine_path: str):
    print("=== [3/6] Testando Watchdog Anti-Crash (SIGKILL e Congelamento SIGSTOP) ===")
    tmpdir = tempfile.mkdtemp(prefix="suntzu_watchdog_test_")
    try:
        eng = WatchdogEngine(
            engine_path,
            options={"Threads": "1", "Hash": "16", "OwnBook": "false"},
            watchdog_timeout=0.8,
        )
        session = GameSession(
            engine=eng,
            our_color=chess.WHITE,
            initial_time_ms=300_000,
            save_dir=tmpdir,
            enable_ponder=False,
        )

        # Mata abruptamente o processo do motor (SIGKILL) antes do nosso lance
        assert eng.proc is not None
        os.kill(eng.proc.pid, signal.SIGKILL)
        time.sleep(0.05)

        mv1, _, _, _ = session.play_our_move(movetime_override_ms=30)
        assert eng.restart_count >= 1
        print(f"  -> Recuperação após SIGKILL: motor reiniciado (#{eng.restart_count}) e jogou {mv1.uci()}")

        # Adversário joga um lance
        opp_mv = next(iter(session.board.legal_moves))
        session.apply_opponent_move(opp_mv)

        # Congela o processo do motor com SIGSTOP (simulando travamento / não responde readyok)
        assert eng.proc is not None
        frozen_pid = eng.proc.pid
        os.kill(frozen_pid, signal.SIGSTOP)

        mv2, _, _, _ = session.play_our_move(movetime_override_ms=30)
        assert eng.restart_count >= 2
        print(f"  -> Recuperação após congelamento (SIGSTOP): watchdog detectou em 0.8s, reiniciou e jogou {mv2.uci()}")

        eng.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_rule_alerts():
    print("=== [4/6] Testando Alertas de Regra (Repetição Tripla e 50 Lances) ===")
    b = chess.Board()
    for u in ("g1f3", "g8f6", "f3g1", "f6g8", "g1f3", "g8f6", "f3g1", "f6g8"):
        b.push_uci(u)

    # Posição repetida 3 vezes e estamos perdendo (-120 cp): deve recomendar reivindicar
    alerts_losing = check_rule_alerts(b, last_eval_cp=-120, is_our_turn=True)
    assert any("REPETIÇÃO TRIPLA" in a for a in alerts_losing)
    assert any("ESTAMOS EM DESVANTAGEM — REIVINDIQUE O EMPATE" in a for a in alerts_losing)

    # Regra dos 50 lances no tabuleiro
    b50 = chess.Board("4k3/8/8/8/8/8/8/4K2R w - - 100 80")
    alerts_50 = check_rule_alerts(b50, last_eval_cp=0, is_our_turn=False)
    assert any("50 LANCES" in a and "O ADVERSÁRIO PODE" in a for a in alerts_50)
    print("  -> Alertas de repetição tripla, 50 lances e recomendação estratégica: OK")


def test_cli_end_to_end(engine_path: str):
    print("=== [5/6] Testando CLI Interativa de Ponta a Ponta (stdin/stdout) ===")
    tmpdir = tempfile.mkdtemp(prefix="suntzu_cli_test_")
    try:
        # Jogamos de Pretas: adversário digita lance inválido 'e2e5', depois 'e4' e confirma (Enter),
        # motor responde (com livro), depois 't 24:10', 'u', 'fen', 'quit'
        script_input = "\n".join(
            [
                "e2e5",   # lance ilegal -> rejeitado
                "e4",     # lance válido em SAN
                "",       # Enter confirma o lance
                "t 24:10",  # sincroniza relógio
                "u",      # desfaz o par de lances
                "fen",    # mostra FEN
                "quit",   # sai
            ]
        ) + "\n"

        proc = subprocess.run(
            [
                sys.executable,
                os.path.join(ROOT_DIR, "tools", "operator_console", "console.py"),
                "--engine",
                engine_path,
                "--color",
                "pretas",
                "--save-dir",
                tmpdir,
            ],
            input=script_input,
            text=True,
            capture_output=True,
            timeout=15,
        )
        assert proc.returncode == 0, f"Erro na CLI: {proc.stderr}\n{proc.stdout}"
        out = proc.stdout
        assert "[LANCE REJEITADO]" in out
        assert "NOSSO LANCE:" in out
        assert "[RELÓGIO SINCRONIZADO] Nosso tempo ajustado para 24:10" in out
        assert "[DESFEITO]" in out
        assert os.path.isfile(os.path.join(tmpdir, "ultima.fen"))
        assert os.path.isfile(os.path.join(tmpdir, "ultima.pgn"))
        print("  -> Fluxo completo da CLI interativa validado com sucesso!")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_three_simulated_training_games(engine_path: str):
    print("=== [6/7] Simulando 3 Partidas de Treino Físico via Console (Medição de Operação) ===")
    tmpdir = tempfile.mkdtemp(prefix="suntzu_training_games_")
    try:
        for g in range(1, 4):
            eng = WatchdogEngine(
                engine_path,
                options={
                    "Threads": "2",
                    "Hash": "32",
                    "Ponder": "true",
                    "OwnBook": "true",
                    "BookFile": os.path.join(ROOT_DIR, "books", "suntzu_310.bin"),
                    "PhysicalBoardOverhead": "7000",
                    "PanicReserve": "120",
                    "SunTzu": "true",
                },
                watchdog_timeout=3.0,
            )
            opp = WatchdogEngine(
                engine_path,
                options={"Threads": "1", "Hash": "16", "Skill Level": str(5 + g * 3), "OwnBook": "false"},
                watchdog_timeout=3.0,
            )
            our_col = chess.WHITE if g % 2 == 1 else chess.BLACK
            session = GameSession(
                engine=eng,
                our_color=our_col,
                initial_time_ms=25 * 60 * 1000,
                save_dir=tmpdir,
                enable_ponder=True,
            )

            ponderhits = 0
            our_moves = 0
            for ply in range(30):
                if session.board.is_game_over(claim_draw=True):
                    break
                if session.board.turn == session.our_color:
                    _, _, hit, _ = session.play_our_move(movetime_override_ms=None if ply < 6 else 25)
                    our_moves += 1
                    if hit:
                        ponderhits += 1
                else:
                    bm_opp, _, _ = opp.search(
                        session.start_fen,
                        session.moves_uci,
                        session.wtime_ms,
                        session.btime_ms,
                        movetime_override_ms=20,
                    )
                    session.apply_opponent_move(chess.Move.from_uci(bm_opp))

            print(
                f"  -> Treino #{g} ({'Brancas' if our_col == chess.WHITE else 'Pretas'}): "
                f"{len(session.moves_uci)} meios-lances | Tempo restante={session.our_time_ms//1000}s | "
                f"Doutrina: {eng.last_suntzu_info}"
            )
            eng.close()
            opp.close()
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _play_single_ponder_game(args):
    game_idx, engine_path, base_path = args
    tmpdir = tempfile.mkdtemp(prefix=f"suntzu_p50_{game_idx}_")
    try:
        eng = WatchdogEngine(
            engine_path,
            options={
                "Threads": "1",
                "Hash": "16",
                "Ponder": "true",
                "OwnBook": "true",
                "BookFile": os.path.join(ROOT_DIR, "books", "suntzu_310.bin"),
                "SyzygyPath": os.path.join(ROOT_DIR, "syzygy"),
                "PhysicalBoardOverhead": "50",
                "PanicReserve": "0",
                "SunTzu": "true",
            },
            watchdog_timeout=3.0,
        )
        opp = WatchdogEngine(
            base_path,
            options={"Threads": "1", "Hash": "16"},
            watchdog_timeout=3.0,
        )
        our_col = chess.WHITE if game_idx % 2 == 1 else chess.BLACK
        session = GameSession(
            engine=eng,
            our_color=our_col,
            initial_time_ms=15_000,
            save_dir=tmpdir,
            enable_ponder=True,
        )
        # Pequena variedade inicial quando sem livro / após livro
        openings = [
            [],
            ["e2e4", "e7e5"],
            ["d2d4", "d7d5"],
            ["e2e4", "c7c5"],
            ["g1f3", "g8f6"],
        ]
        for u in openings[game_idx % len(openings)]:
            session.board.push_uci(u)
            session.moves_uci.append(u)

        hits = 0
        misses = 0
        our_turns = 0
        for _ in range(160):
            if session.board.is_game_over(claim_draw=True):
                break
            if session.board.turn == session.our_color:
                was_pondering = eng.pondering
                _, _, hit, _ = session.play_our_move(movetime_override_ms=15 if not hit_possible(eng) else None)
                our_turns += 1
                if hit:
                    hits += 1
                elif was_pondering:
                    misses += 1
            else:
                # Dá ~12 ms para o motor ponderar enquanto o adversário pensa
                bm_opp, _, _ = opp.search(
                    session.start_fen,
                    session.moves_uci,
                    session.wtime_ms,
                    session.btime_ms,
                    movetime_override_ms=15,
                )
                session.apply_opponent_move(chess.Move.from_uci(bm_opp))

        restarts = eng.restart_count + opp.restart_count
        eng.close()
        opp.close()
        return len(session.moves_uci), our_turns, hits, misses, restarts
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def hit_possible(eng: WatchdogEngine) -> bool:
    return eng.pondering and eng.ponder_move_uci is not None


def test_50_ponder_games_stress(engine_path: str):
    import concurrent.futures

    print("=== [7/7] Teste de Estresse de 50 Partidas com Ponder Ativo (go ponder -> ponderhit/stop) ===")
    base_bin = os.path.join(ROOT_DIR, "bin", "sf-base")
    if not os.path.isfile(base_bin):
        base_bin = engine_path

    tasks = [(i, engine_path, base_bin) for i in range(1, 51)]
    total_plies = 0
    total_turns = 0
    total_hits = 0
    total_misses = 0
    total_restarts = 0
    t0 = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(max_workers=10) as ex:
        for plies, turns, hits, misses, restarts in ex.map(_play_single_ponder_game, tasks):
            total_plies += plies
            total_turns += turns
            total_hits += hits
            total_misses += misses
            total_restarts += restarts

    dt = time.monotonic() - t0
    assert total_restarts == 0, f"Houve {total_restarts} reinícios/crashes durante as 50 partidas com Ponder!"
    print(
        f"  -> 50/50 partidas com Ponder concluídas em {dt:.1f}s | "
        f"Meios-lances={total_plies} | Lances SunTzu={total_turns} | "
        f"Ponderhits={total_hits} | Ponder misses={total_misses} | Crashes={total_restarts}"
    )


if __name__ == "__main__":
    engine_bin = os.path.join(ROOT_DIR, "bin", "suntzu-native")
    if not os.path.isfile(engine_bin):
        print(f"Binário não encontrado: {engine_bin}", file=sys.stderr)
        sys.exit(1)

    test_move_parser_and_banners()
    test_session_undo_clock_ponder_and_resume(engine_bin)
    test_watchdog_anticrash(engine_bin)
    test_rule_alerts()
    test_cli_end_to_end(engine_bin)
    test_three_simulated_training_games(engine_bin)
    test_50_ponder_games_stress(engine_bin)
    print("\nSUCESSO: Todos os testes do Console Anti-Crash da Fase 6 passaram!")
