#!/usr/bin/env python3
"""
Gera um livro de aberturas Polyglot (.bin) otimizado para o sistema 3-1-0:
    peso = 3 * vitorias + empates

Fontes suportadas:
1. Repertório curado 3-1-0 de linhas agressivas/desequilibradas de alto nível
   (Siciliana Najdorf/Sveshnikov, Índia do Rei, Grünfeld, Ruy Lopez, Italiana Giuoco Piano/Evans,
   Gambito da Dama, Nimzo-Índia, Francesa Winawer, Caro-Kann Avanço, etc.)
   filtrando linhas da lista `books/evitar.txt`.
2. Arquivos PGN adicionais passados por linha de comando (`--pgn arquivo.pgn`),
   contabilizando vitorias (3 pts) e empates (1 pt) até o lance 16 (32 plies).
"""
import argparse
import os
import struct
import sys
from collections import defaultdict

# Permite usar a venv local automaticamente se existir
ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENV_SITE = os.path.join(ROOT_DIR, ".venv", "lib")
if os.path.isdir(VENV_SITE):
    for d in os.listdir(VENV_SITE):
        sp = os.path.join(VENV_SITE, d, "site-packages")
        if os.path.isdir(sp) and sp not in sys.path:
            sys.path.insert(0, sp)

import chess
import chess.pgn
import chess.polyglot

ENTRY_STRUCT = struct.Struct(">QHHI")


def move_to_polyglot_u16(board: chess.Board, move: chess.Move) -> int:
    from_sq = move.from_square
    to_sq = move.to_square

    # No formato Polyglot, o roque é codificado como "rei captura a própria torre"
    if board.is_castling(move):
        if board.turn == chess.WHITE:
            to_sq = chess.H1 if chess.square_file(to_sq) > chess.square_file(from_sq) else chess.A1
        else:
            to_sq = chess.H8 if chess.square_file(to_sq) > chess.square_file(from_sq) else chess.A8

    promo = 0
    if move.promotion is not None:
        # 1=knight, 2=bishop, 3=rook, 4=queen
        promo = int(move.promotion) - 1

    return (to_sq & 0x3F) | ((from_sq & 0x3F) << 6) | ((promo & 0x7) << 12)


# Repertório mestre 3-1-0: (sequência UCI, vitórias_estimadas, empates_estimados)
# Peso 3-1-0 calculado automaticamente como: peso = 3 * V + E
CURATED_310_LINES = [
    # --- Aberturas de 1.e4 (foco em linhas assimétricas e de alta vitória) ---
    ("e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 f1e3 e7e5 d4b3 f8e7 f2f3 b8d7", 42, 18),
    ("e2e4 c7c5 g1f3 d7d6 d2d4 c5d4 f3d4 g8f6 b1c3 a7a6 f1g5 e7e6 f2f4 f8e7 d1f3 d8c7", 38, 15),
    ("e2e4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g8f6 b1c3 e7e5 d4b5 d7d6 c1g5 a7a6 b5a3 b7b5", 36, 16),
    ("e2e4 c7c5 g1f3 e7e6 d2d4 c5d4 f3d4 a7a6 b1c3 d8c7 f1d3 g8f6 e1g1 f8c5 d4b3 c5a7", 34, 15),
    ("e2e4 e7e5 g1f3 b8c6 f1c4 f8c5 c2c3 g8f6 d2d3 d7d6 e1g1 a7a5 f1e1 h7h6 b1d2 e8g8", 40, 20),
    ("e2e4 e7e5 g1f3 b8c6 f1c4 g8f6 d2d3 f8c5 c2c3 d7d6 e1g1 a7a5 f1e1 e8g8 h2h3 h7h6", 35, 19),
    ("e2e4 e7e5 g1f3 b8c6 f1b5 a7a6 b5a4 g8f6 e1g1 f8e7 f1e1 b7b5 a4b3 d7d6 c2c3 e8g8", 38, 22),
    ("e2e4 e7e6 d2d4 d7d5 b1c3 f8b4 e4e5 c7c5 a2a3 b4c3 b2c3 g8e7 d1g4 d8c7 g4g7 h8g8", 37, 12),
    ("e2e4 e7e6 d2d4 d7d5 b1d2 g8f6 e4e5 f6d7 f1d3 c7c5 c2c3 b8c6 g1e2 c5d4 c3d4 f7f6", 33, 14),
    ("e2e4 c7c6 d2d4 d7d5 e4e5 c8f5 g1f3 e7e6 f1e2 c6c5 c1e3 c5d4 f3d4 g8e7 e1g1 b8c6", 34, 16),
    ("e2e4 c7c6 d2d4 d7d5 b1c3 d5e4 c3e4 b8d7 g1f3 g8f6 e4g3 e7e6 f1d3 c6c5 e1g1 f8e7", 30, 15),
    ("e2e4 d7d6 d2d4 g8f6 b1c3 g7g6 f2f4 f8g7 g1f3 c7c5 d4c5 d8a5 f1d3 a5c5 d1e2 e8g8", 31, 12),
    # --- Aberturas de 1.d4 / 1.c4 / 1.Nf3 (evitando empates simétricos) ---
    ("d2d4 g8f6 c2c4 g7g6 b1c3 f8g7 e2e4 d7d6 g1f3 e8g8 f1e2 e7e5 e1g1 b8c6 d4d5 c6e7", 41, 16),
    ("d2d4 g8f6 c2c4 g7g6 b1c3 d7d5 c4d5 f6d5 e2e4 d5c3 b2c3 f8g7 f1c4 c7c5 g1e2 b8c6", 36, 17),
    ("d2d4 g8f6 c2c4 e7e6 b1c3 f8b4 e2e3 e8g8 f1d3 d7d5 g1f3 c7c5 e1g1 d5c4 d3c4 c5d4", 35, 19),
    ("d2d4 g8f6 c2c4 e7e6 g1f3 d7d5 b1c3 f8e7 c1g5 h7h6 g5h4 e8g8 e2e3 b7b6 c4d5 f6d5", 33, 18),
    ("d2d4 d7d5 c2c4 e7e6 b1c3 g8f6 c4d5 e6d5 c1g5 f8e7 e2e3 c7c6 f1d3 b8d7 d1c2 e8g8", 34, 18),
    ("d2d4 d7d5 c2c4 c7c6 g1f3 g8f6 b1c3 e7e6 e2e3 b8d7 f1d3 d5c4 d3c4 b7b5 c4d3 a7a6", 35, 16),
    ("d2d4 g8f6 c2c4 c7c5 d4d5 e7e6 b1c3 e6d5 c4d5 d7d6 e2e4 g7g6 g1f3 f8g7 f1e2 e8g8", 32, 11),
    ("c2c4 e7e5 b1c3 g8f6 g1f3 b8c6 g2g3 d7d5 c4d5 f6d5 f1g2 d5b6 e1g1 f8e7 a2a3 e8g8", 34, 15),
    ("c2c4 c7c5 g1f3 b8c6 d2d4 c5d4 f3d4 g8f6 b1c3 e7e6 g2g3 d8b6 d4b3 c6e5 e2e4 f8b4", 31, 14),
    ("g1f3 d7d5 d2d4 g8f6 c2c4 e7e6 g2g3 f8b4 c1d2 b4e7 f1g2 e8g8 e1g1 c7c6 d1c2 b7b6", 32, 16),
]


def load_avoid_prefixes(avoid_file: str) -> list[str]:
    prefixes = []
    if avoid_file and os.path.isfile(avoid_file):
        with open(avoid_file, encoding="utf-8") as f:
            for line in f:
                line = line.split("#")[0].strip()
                if line:
                    prefixes.append(line)
    return prefixes


def build_book(output_path: str, pgn_paths: list[str], avoid_file: str, max_ply: int = 32):
    avoid_prefixes = load_avoid_prefixes(avoid_file)
    # stats[(key, pg_move)] = [wins, draws, games]
    stats: dict[tuple[int, int], list[int]] = defaultdict(lambda: [0, 0, 0])

    # 1. Carrega linhas curadas 3-1-0
    for uci_line, wins, draws in CURATED_310_LINES:
        if any(uci_line.startswith(pref) for pref in avoid_prefixes):
            continue
        board = chess.Board()
        for ply, uci_move in enumerate(uci_line.split()):
            if ply >= max_ply:
                break
            move = chess.Move.from_uci(uci_move)
            if move not in board.legal_moves:
                break
            key = chess.polyglot.zobrist_hash(board)
            pg_move = move_to_polyglot_u16(board, move)
            rec = stats[(key, pg_move)]
            rec[0] += wins
            rec[1] += draws
            rec[2] += wins + draws
            board.push(move)

    # 2. Processa PGNs adicionais se fornecidos
    for pgn_path in pgn_paths:
        if not os.path.isfile(pgn_path):
            continue
        with open(pgn_path, encoding="utf-8", errors="ignore") as f:
            while True:
                game = chess.pgn.read_game(f)
                if game is None:
                    break
                res = game.headers.get("Result", "*")
                if res not in ("1-0", "0-1", "1/2-1/2"):
                    continue
                board = game.board()
                if board.fen() != chess.STARTING_FEN:
                    continue
                uci_seq = []
                for ply, move in enumerate(game.mainline_moves()):
                    if ply >= max_ply:
                        break
                    uci_seq.append(move.uci())
                    prefix_str = " ".join(uci_seq)
                    if any(prefix_str.startswith(pref) for pref in avoid_prefixes):
                        break
                    key = chess.polyglot.zobrist_hash(board)
                    pg_move = move_to_polyglot_u16(board, move)
                    rec = stats[(key, pg_move)]
                    if res == "1/2-1/2":
                        rec[1] += 1
                    elif (res == "1-0" and board.turn == chess.WHITE) or (
                        res == "0-1" and board.turn == chess.BLACK
                    ):
                        rec[0] += 1
                    rec[2] += 1
                    board.push(move)

    # 3. Converte para entradas Polyglot com peso = 3 * vitorias + empates
    entries = []
    for (key, pg_move), (wins, draws, _games) in stats.items():
        weight_310 = 3 * wins + draws
        if weight_310 <= 0:
            continue
        weight_u16 = min(65535, weight_310)
        entries.append((key, pg_move, weight_u16, 0))

    # Ordena estritamente por (key ASC, weight DESC) conforme especificação Polyglot
    entries.sort(key=lambda x: (x[0], -x[2]))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "wb") as out:
        for key, pg_move, weight_u16, learn in entries:
            out.write(ENTRY_STRUCT.pack(key, pg_move, weight_u16, learn))

    print(f"Livro Polyglot 3-1-0 gerado em '{output_path}': {len(entries)} entradas ({len(entries)*16} bytes).")


def main():
    parser = argparse.ArgumentParser(description="Construtor do Livro Polyglot 3-1-0 SunTzu")
    parser.add_argument("--out", default="books/suntzu_310.bin", help="Arquivo .bin de saída")
    parser.add_argument("--avoid", default="books/evitar.txt", help="Lista de variantes empatadoras a evitar")
    parser.add_argument("--max-ply", type=int, default=32, help="Profundidade máxima em meios-lances")
    parser.add_argument("--pgn", nargs="*", default=[], help="Arquivos PGN extras para contabilizar")
    args = parser.parse_args()
    build_book(args.out, args.pgn, args.avoid, args.max_ply)


if __name__ == "__main__":
    main()
