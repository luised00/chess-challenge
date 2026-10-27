#!/usr/bin/env python3
"""
Testes da Fase 3 (Livro Polyglot):
1. Confere 1000 posições aleatórias (incluindo roques, promoções e en passant cravados/livres)
   comparando a chave gerada pelo motor (`bookkey`) com `chess.polyglot.zobrist_hash` do python-chess.
2. Verifica o tempo de resposta (< 5 ms) para lances do livro (`books/suntzu_310.bin`).
3. Testa a robustez contra arquivo ausente e arquivo corrompido (o motor nunca trava e joga normalmente).
"""
import os
import random
import subprocess
import sys
import tempfile
import time

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENV_SITE = os.path.join(ROOT_DIR, ".venv", "lib")
if os.path.isdir(VENV_SITE):
    for d in os.listdir(VENV_SITE):
        sp = os.path.join(VENV_SITE, d, "site-packages")
        if os.path.isdir(sp) and sp not in sys.path:
            sys.path.insert(0, sp)

import chess
import chess.polyglot


def run_tests(engine_path: str, book_path: str):
    proc = subprocess.Popen(
        [engine_path],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    assert proc.stdin and proc.stdout

    def send(cmd: str):
        proc.stdin.write(cmd + "\n")
        proc.stdin.flush()

    def readline() -> str:
        return proc.stdout.readline().strip()

    def read_until(prefix: str) -> str:
        while True:
            line = readline()
            if line.startswith(prefix):
                return line

    send("uci")
    read_until("uciok")
    send("isready")
    read_until("readyok")

    # 1. Conferir posição inicial e casos especiais de en passant (incluindo peão cravado)
    special_fens = [
        chess.STARTING_FEN,
        "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
        "rnbqkbnr/ppp1pppp/8/3pP3/8/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2",
        "8/8/8/K2pP2r/8/8/8/7k w - d6 0 1",  # Peão em e5 cravado na horizontal pela torre em h5
    ]

    rng = random.Random(20261106)
    random_fens = list(special_fens)
    board = chess.Board()
    while len(random_fens) < 1000:
        if board.is_game_over() or board.fullmove_number > 60:
            board.reset()
        legal = list(board.legal_moves)
        if not legal:
            board.reset()
            continue
        m = rng.choice(legal)
        board.push(m)
        random_fens.append(board.fen())

    matches = 0
    for idx, fen in enumerate(random_fens):
        b = chess.Board(fen)
        expected = f"{chess.polyglot.zobrist_hash(b):016x}"
        send(f"position fen {fen}")
        send("bookkey")
        got = readline()
        if got != expected:
            print(f"ERRO na posição #{idx} ({fen}): esperado {expected}, obtido {got}")
            sys.exit(1)
        matches += 1

    print(f"=== [1/3] Chaves Polyglot: {matches}/1000 (100.0%) idênticas ao python-chess! ===")

    # 2. Tempo de resposta com livro (< 5 ms)
    send("setoption name OwnBook value true")
    send(f"setoption name BookFile value {book_path}")
    send("setoption name BookDepth value 16")
    send("setoption name BookVariety value false")
    send("isready")
    read_until("readyok")

    timings_ms = []
    test_moves = ["", "e2e4", "e2e4 c7c5", "e2e4 c7c5 g1f3", "d2d4", "d2d4 g8f6"]
    for mv in test_moves:
        pos_cmd = "position startpos" + (f" moves {mv}" if mv else "")
        send(pos_cmd)
        t0 = time.perf_counter()
        send("go wtime 1500000 btime 1500000")
        bm = read_until("bestmove")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        timings_ms.append(dt_ms)
        assert bm != "bestmove (none)", f"Lance inválido: {bm}"

    avg_ms = sum(timings_ms) / len(timings_ms)
    max_ms = max(timings_ms)
    print(f"=== [2/3] Tempo de resposta do livro: média {avg_ms:.3f} ms | máx {max_ms:.3f} ms (< 5 ms) ===")
    assert max_ms < 5.0, f"Tempo do livro excedeu 5 ms: {max_ms:.3f} ms"

    # 3. Robustez contra arquivo ausente e arquivo corrompido
    send("setoption name BookFile value books/arquivo_que_nao_existe.bin")
    send("position startpos")
    send("go movetime 30")
    bm_missing = read_until("bestmove")
    assert bm_missing.startswith("bestmove "), "Falha com arquivo ausente"

    with tempfile.NamedTemporaryFile("wb", suffix=".bin", delete=False) as bad:
        bad.write(b"corrupted_book_not_multiple_of_16_bytes")
        bad_path = bad.name

    try:
        send(f"setoption name BookFile value {bad_path}")
        send("position startpos")
        send("go movetime 30")
        bm_corrupt = read_until("bestmove")
        assert bm_corrupt.startswith("bestmove "), "Falha com arquivo corrompido"
    finally:
        os.remove(bad_path)

    print("=== [3/3] Robustez comprovada: arquivo ausente e corrompido fazem fallback limpo! ===")
    send("quit")
    proc.wait(timeout=2)


if __name__ == "__main__":
    engine = sys.argv[1] if len(sys.argv) > 1 else "bin/suntzu-native"
    book = sys.argv[2] if len(sys.argv) > 2 else "books/suntzu_310.bin"
    run_tests(engine, book)
