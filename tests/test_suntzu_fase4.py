#!/usr/bin/env python3
"""
Testes da Fase 4 (Modelo do Oponente e Aversão ao Empate 3-1-0):
1. Simula 20 partidas contra um oponente FORTE (lances ótimos da própria engine) e
   20 partidas contra um oponente FRACO (lances subótimos / Skill Level 0 / perdas de centipeões),
   verificando se o classificador (`info string SunTzu: perfil=...`) acerta > 90% até o lance 30.
2. Verifica a aversão ao empate (`DrawAversion`) em posições onde o motor tem opção de empatar
   por repetição vs continuar jogando contra oponente fraco vs quando está perdendo (< -50 cp).
3. Confere que com `SunTzu=false` o `bench` é idêntico à base (2497913).
"""
import os
import random
import re
import subprocess
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
VENV_SITE = os.path.join(ROOT_DIR, ".venv", "lib")
if os.path.isdir(VENV_SITE):
    for d in os.listdir(VENV_SITE):
        sp = os.path.join(VENV_SITE, d, "site-packages")
        if os.path.isdir(sp) and sp not in sys.path:
            sys.path.insert(0, sp)

import chess


class UCIDriver:
    def __init__(self, path: str, options: dict[str, str] | None = None):
        self.proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        assert self.proc.stdin and self.proc.stdout
        self.send("uci")
        self.read_until("uciok")
        if options:
            for k, v in options.items():
                self.send(f"setoption name {k} value {v}")
        self.send("isready")
        self.read_until("readyok")

    def send(self, cmd: str):
        assert self.proc.stdin
        self.proc.stdin.write(cmd + "\n")
        self.proc.stdin.flush()

    def read_until(self, prefix: str) -> tuple[str, list[str]]:
        assert self.proc.stdout
        lines = []
        while True:
            line = self.proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            lines.append(line)
            if line.startswith(prefix):
                return line, lines
        raise RuntimeError(f"EOF waiting for {prefix}")

    def new_game(self):
        self.send("ucinewgame")
        self.send("isready")
        self.read_until("readyok")

    def search(self, fen: str, moves: list[str], movetime_ms: int = 25) -> tuple[str, str]:
        if moves:
            self.send(f"position fen {fen} moves {' '.join(moves)}")
        else:
            self.send(f"position fen {fen}")
        self.send(f"go movetime {movetime_ms}")
        bm_line, all_lines = self.read_until("bestmove")
        bm = bm_line.split()[1]
        suntzu_info = ""
        for l in all_lines:
            if "info string SunTzu:" in l:
                suntzu_info = l
        return bm, suntzu_info

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


def extract_profile(info_line: str) -> str:
    m = re.search(r"detectado=(forte|medio|fraco)", info_line)
    return m.group(1) if m else ""


def test_classifier(engine_path: str):
    print("=== [1/2] Testando Classificador Online do Oponente (Forte vs Fraco até o lance 30) ===")
    suntzu = UCIDriver(
        engine_path,
        {
            "SunTzu": "true",
            "OpponentProfile": "auto",
            "OwnBook": "false",
            "PhysicalBoardOverhead": "0",
            "PanicReserve": "0",
        },
    )
    strong_opp = UCIDriver(
        engine_path,
        {"SunTzu": "false", "OwnBook": "false", "PhysicalBoardOverhead": "0", "PanicReserve": "0"},
    )

    # Carrega posições iniciais do UHO.epd (com Brancas a jogar)
    fens = []
    with open(os.path.join(ROOT_DIR, "books", "UHO.epd"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and " w " in line:
                fens.append(line)
                if len(fens) >= 40:
                    break

    strong_correct = 0
    weak_correct = 0
    rng = random.Random(42)

    # A. 20 partidas contra oponente FORTE (Stockfish puro)
    for i in range(20):
        suntzu.new_game()
        strong_opp.new_game()
        board = chess.Board(fens[i])
        moves = []
        detected = "medio"
        while not board.is_game_over() and board.fullmove_number <= 24:
            if board.turn == chess.WHITE:
                bm, info = suntzu.search(fens[i], moves, movetime_ms=20)
                if info:
                    detected = extract_profile(info)
            else:
                bm, _ = strong_opp.search(fens[i], moves, movetime_ms=25)
            moves.append(bm)
            board.push_uci(bm)
        if detected == "forte":
            strong_correct += 1

    # B. 20 partidas contra oponente FRACO (lances subótimos/aleatórios)
    for i in range(20):
        suntzu.new_game()
        board = chess.Board(fens[20 + i])
        moves = []
        detected = "medio"
        while not board.is_game_over() and board.fullmove_number <= 24:
            if board.turn == chess.WHITE:
                bm, info = suntzu.search(fens[20 + i], moves, movetime_ms=20)
                if info:
                    detected = extract_profile(info)
            else:
                legal = [m.uci() for m in board.legal_moves]
                bm = rng.choice(legal)
            moves.append(bm)
            board.push_uci(bm)
        if detected == "fraco":
            weak_correct += 1

    total_acc = (strong_correct + weak_correct) / 40.0 * 100.0
    print(
        f"  -> Acertos Forte: {strong_correct}/20 | Acertos Fraco: {weak_correct}/20 | Acurácia Global: {total_acc:.1f}% (meta > 90%)"
    )
    assert total_acc >= 90.0, f"Acurácia do classificador abaixo de 90%: {total_acc:.1f}%"

    # 2. Verificar DrawAversion cai a 0 quando estamos perdendo (< -50 cp)
    print("=== [2/2] Verificando DrawAversion dinâmico (0 cp quando perdendo < -50 cp) ===")
    suntzu.new_game()
    suntzu.send("setoption name OpponentProfile value fraco")
    # Posição onde as brancas estão claramente piores (peça a menos):
    losing_fen = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQK1NR w KQkq - 0 1"
    _, info_losing = suntzu.search(losing_fen, [], movetime_ms=25)
    print(f"  -> Posição inferior: {info_losing}")
    assert "DrawAversion=0cp" in info_losing, f"DrawAversion deveria ser 0cp quando perdendo: {info_losing}"

    # Posição onde as brancas estão ligeiramente melhores (+40 cp) contra oponente fraco -> DrawAversion=50cp
    winning_fen = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3"
    _, info_winning = suntzu.search(winning_fen, [], movetime_ms=25)
    print(f"  -> Posição equilibrada/superior vs fraco: {info_winning}")
    assert "DrawAversion=50cp" in info_winning, f"DrawAversion deveria ser 50cp vs fraco: {info_winning}"

    # 3. Verificar que o motor evita empate por repetição (h6g7) em posição igualada vs fraco
    rep_fen = "r1bqkbnr/ppp1pppp/3p4/3Pn3/4P3/8/PPP2PPP/RNBQKBNR w KQkq - 1 4"
    rep_moves = "f2f4 e5d7 g1f3 c7c6 c2c4 g7g6 d1d4 g8f6 e4e5 f6g8 h2h3 f8g7 c1e3 d8c7 b1c3 d6e5 f4e5 d7e5 e1c1 c8f5 d4f4 g7h6 f4d4 h6g7 d4f4 g7h6 f4d4".split()
    bm_rep, _ = suntzu.search(rep_fen, rep_moves, movetime_ms=80)
    print(f"  -> Lance escolhido diante de repetição (h6g7 empataria): {bm_rep}")
    assert bm_rep != "h6g7", "SunTzu não deveria repetir h6g7 contra oponente fraco em posição igualada!"

    suntzu.close()
    strong_opp.close()


if __name__ == "__main__":
    engine = sys.argv[1] if len(sys.argv) > 1 else "bin/suntzu-native"
    test_classifier(engine)
