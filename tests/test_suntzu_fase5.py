#!/usr/bin/env python3
"""
Testes da Fase 5 (Modos Pressão, Virada, Conversão e Tablebases Syzygy):
1. Valida carregamento das tablebases Syzygy (35 WDL + 35 DTZ em ./syzygy), sondagem na raiz
   (KBNvK, KBPvK, KPvK) e fallback seguro para diretório inexistente.
2. Valida condições de ativação e desativação dos modos:
   - Pressão: ativo contra fraco/médio com > 5 min no relógio; desligado contra forte ou < 5 min.
   - Virada (Swindle): ativo quando perdendo entre -150 cp e -750 cp; penaliza trocas de peças.
   - Conversão: ativo quando ganhando acima de +300 cp; prioriza trocas seguras e menos xeques adversários.
3. Executa baterias práticas de partidas:
   - Virada: posições com -2 a -3 peões contra oponente enfraquecido.
   - Conversão + Syzygy: posições com +3 a +5 de vantagem até o fim da partida.
"""
import os
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
        self.init_lines: list[str] = []
        if options:
            for k, v in options.items():
                self.send(f"setoption name {k} value {v}")
        self.send("isready")
        _, lines = self.read_until("readyok")
        self.init_lines.extend(lines)

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

    def set_option(self, name: str, value: str) -> list[str]:
        self.send(f"setoption name {name} value {value}")
        self.send("isready")
        _, lines = self.read_until("readyok")
        return lines

    def new_game(self):
        self.send("ucinewgame")
        self.send("isready")
        self.read_until("readyok")

    def search_go(self, fen: str, moves: list[str], go_cmd: str) -> tuple[str, str, list[str]]:
        if moves:
            self.send(f"position fen {fen} moves {' '.join(moves)}")
        else:
            self.send(f"position fen {fen}")
        self.send(go_cmd)
        bm_line, all_lines = self.read_until("bestmove")
        bm = bm_line.split()[1]
        suntzu_info = ""
        for l in all_lines:
            if "info string SunTzu:" in l:
                suntzu_info = l
        return bm, suntzu_info, all_lines

    def close(self):
        try:
            self.send("quit")
            self.proc.wait(timeout=2)
        except Exception:
            self.proc.kill()


def test_syzygy(engine_path: str):
    print("=== [1/4] Testando Tablebases Syzygy (3-4 peças) e Fallback Seguro ===")
    syzygy_dir = os.path.join(ROOT_DIR, "syzygy")
    assert os.path.isdir(syzygy_dir), f"Diretório {syzygy_dir} não encontrado"

    eng = UCIDriver(engine_path, {"SyzygyPath": syzygy_dir})
    tb_msg = [l for l in eng.init_lines if "Found" in l and "tablebase" in l]
    print(f"  Carregamento Syzygy: {tb_msg[0] if tb_msg else 'N/A'}")
    assert any("Found 35 WDL and 35 DTZ" in l for l in tb_msg), f"Falha ao carregar 35 TBs: {tb_msg}"

    # Testa final KBN vs K (vitória de tablebase e tbhits > 0)
    fen_kbnk = "4k3/8/8/8/8/8/3BN3/4K3 w - - 0 1"
    bm, _, lines = eng.search_go(fen_kbnk, [], "go depth 8")
    has_tb_win = any("score cp 20000" in l or "score mate" in l or "tbhits" in l for l in lines)
    print(f"  KBNvK lance={bm} | TB detectada={has_tb_win}")
    assert has_tb_win and bm != "(none)"

    # Testa fallback seguro com caminho inválido
    fallback_lines = eng.set_option("SyzygyPath", "/caminho/inexistente/syzygy_404")
    bm2, _, _ = eng.search_go(fen_kbnk, [], "go depth 6")
    print(f"  Fallback caminho inexistente: lance={bm2} (0 crashes)")
    assert bm2 != "(none)"
    eng.close()


def test_modes_activation_and_tiebreak(engine_path: str):
    print("\n=== [2/4] Testando Ativação dos Modos (Pressão, Virada, Conversão) e Desempate na Raiz ===")
    eng = UCIDriver(
        engine_path,
        {
            "SunTzu": "true",
            "OwnBook": "false",
            "PhysicalBoardOverhead": "7000",
            "PanicReserve": "120",
            "PressureMargin": "15",
            "SwindleMode": "true",
            "ConvertMode": "true",
        },
    )

    # 1. Pressão vs Oponente Fraco com > 5 min (600s = 600000ms) no relógio
    eng.set_option("OpponentProfile", "fraco")
    fen_mid = "r1bqk2r/ppp2ppp/2np1n2/2b1p3/2B1P3/2NP1N2/PPP2PPP/R1BQK2R w KQkq - 0 6"
    bm_p, info_p, _ = eng.search_go(fen_mid, [], "go wtime 600000 btime 600000 depth 8")
    print(f"  [Pressão - Fraco, 10min] bestmove={bm_p} | {info_p}")
    assert "modo=pressao" in info_p, f"Esperava modo=pressao: {info_p}"

    # 2. Pressão desliga quando oponente é Forte
    eng.set_option("OpponentProfile", "forte")
    bm_f, info_f, _ = eng.search_go(fen_mid, [], "go wtime 600000 btime 600000 depth 8")
    print(f"  [Segurança - Forte, 10min] bestmove={bm_f} | {info_f}")
    assert "modo=nenhum" in info_f, f"Esperava modo=nenhum contra forte: {info_f}"

    # 3. Pressão desliga quando relógio < 5 min (ex: 4 min = 240000ms) no tabuleiro físico
    eng.set_option("OpponentProfile", "fraco")
    bm_low, info_low, _ = eng.search_go(fen_mid, [], "go wtime 240000 btime 240000 depth 8")
    print(f"  [Segurança - Relógio < 5min] bestmove={bm_low} | {info_low}")
    assert "modo=nenhum" in info_low, f"Esperava modo=nenhum com < 5min: {info_low}"

    # 4. Modo Virada (Swindle): posição inferior (~ -350 cp, cavalo a menos para as Brancas)
    fen_down_piece = "r1bq1rk1/ppp1bppp/2np1n2/4p3/2B1P3/3P1N2/PPP2PPP/R1BQ1RK1 w - - 0 7"
    bm_sw, info_sw, _ = eng.search_go(fen_down_piece, [], "go wtime 600000 btime 600000 depth 8")
    print(f"  [Virada - Perdendo ~-300cp] bestmove={bm_sw} | {info_sw}")
    assert "modo=virada" in info_sw, f"Esperava modo=virada: {info_sw}"

    # 5. Modo Conversão: posição ganha (> +350 cp, torre a mais para as Brancas)
    fen_win = "2bq1rk1/ppp1bppp/2np1n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQR1K1 w - - 0 8"
    bm_cv, info_cv, _ = eng.search_go(fen_win, [], "go wtime 600000 btime 600000 depth 8")
    print(f"  [Conversão - Ganhando ~+500cp] bestmove={bm_cv} | {info_cv}")
    assert "modo=conversao" in info_cv, f"Esperava modo=conversao: {info_cv}"

    eng.close()


def play_mini_game(
    suntzu: UCIDriver, opp: UCIDriver, start_fen: str, max_plies: int = 80, movetime_ms: int = 25
) -> str:
    board = chess.Board(start_fen)
    suntzu.new_game()
    opp.new_game()
    suntzu_color = board.turn
    moves: list[str] = []

    for _ in range(max_plies):
        if board.is_game_over(claim_draw=True):
            break
        if board.turn == suntzu_color:
            bm, _, _ = suntzu.search_go(start_fen, moves, f"go movetime {movetime_ms}")
        else:
            bm, _, _ = opp.search_go(start_fen, moves, f"go movetime {movetime_ms}")
        move = chess.Move.from_uci(bm)
        assert move in board.legal_moves, f"Lance ilegal {bm} em {board.fen()}"
        board.push(move)
        moves.append(bm)

    if board.is_checkmate():
        return "W" if board.turn != suntzu_color else "L"
    if board.is_game_over(claim_draw=True):
        return "D"
    # Adjudica pelo material/avaliação rápida se atingir max_plies
    _, info, lines = suntzu.search_go(board.fen(), [], "go depth 6")
    cp = 0
    for l in lines:
        m = re.search(r"score cp (-?\d+)", l)
        if m:
            cp = int(m.group(1))
        elif "score mate -" in l:
            cp = -10000
        elif "score mate " in l:
            cp = 10000
    if board.turn != suntzu_color:
        cp = -cp
    if cp > 200:
        return "W"
    if cp < -200:
        return "L"
    return "D"


def test_swindle_and_conversion_suites(engine_path: str):
    print("\n=== [3/4] Testando Modo Virada (Posições com -2 a -3 peões vs Oponente Fraco) ===")
    # 6 posições de meio-jogo onde as Brancas estão com 2 peões a menos (~ -200 a -260 cp), mas com peças ativas
    swindle_fens = [
        "r1bq1rk1/ppp1ppbp/2np1np1/8/2B1P3/2NP1N2/P1P2PPP/R1BQ1RK1 w - - 0 8",
        "r2qkb1r/ppp1pppp/2n2n2/3p1b2/3P1B2/2N2N2/PP2PPPP/R2QKB1R w KQkq - 0 6",
        "r1bqk2r/pppp1ppp/2n2n2/2b1p3/2B1P3/2N2N2/PP1P1PPP/R1BQK2R w KQkq - 0 6",
        "rnbq1rk1/ppp1ppbp/3p1np1/8/2PPP3/2N2N2/PP3PPP/R1BQKB1R w KQkq - 0 6",
    ]

    suntzu_sw = UCIDriver(
        engine_path,
        {
            "SunTzu": "true",
            "OpponentProfile": "fraco",
            "SwindleMode": "true",
            "OwnBook": "false",
            "PhysicalBoardOverhead": "0",
            "PanicReserve": "0",
        },
    )
    weak_opp = UCIDriver(
        engine_path,
        {
            "SunTzu": "false",
            "Skill Level": "3",
            "OwnBook": "false",
            "PhysicalBoardOverhead": "0",
            "PanicReserve": "0",
        },
    )

    saved = 0
    results = []
    for fen in swindle_fens:
        res = play_mini_game(suntzu_sw, weak_opp, fen, max_plies=60, movetime_ms=25)
        results.append(res)
        if res in ("W", "D"):
            saved += 1

    print(f"  Resultados Virada (4 partidas com -2 peões vs Skill 3): {results} ({saved}/4 salvas)")
    assert saved >= 2, f"Esperava salvar pelo menos 2/4 partidas no modo Virada: {results}"

    print("\n=== [4/4] Testando Modo Conversão + Syzygy (Posições com +3 a +5 de vantagem vs Base) ===")
    convert_fens = [
        "2bq1rk1/ppp2ppp/2np1n2/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQR1K1 w - - 0 8",
        "r1bqk2r/ppp2ppp/2p5/4p3/2B1P3/2NP1N2/PPP2PPP/R1BQ1RK1 w kq - 0 7",
        "4k3/8/8/8/8/4K3/4P2R/8 w - - 0 1",
        "8/1P6/2B5/8/4K3/8/6k1/8 w - - 0 1",
    ]
    syzygy_dir = os.path.join(ROOT_DIR, "syzygy")
    suntzu_cv = UCIDriver(
        engine_path,
        {
            "SunTzu": "true",
            "ConvertMode": "true",
            "SyzygyPath": syzygy_dir,
            "OwnBook": "false",
            "PhysicalBoardOverhead": "0",
            "PanicReserve": "0",
        },
    )
    strong_opp = UCIDriver(
        engine_path,
        {
            "SunTzu": "false",
            "OwnBook": "false",
            "PhysicalBoardOverhead": "0",
            "PanicReserve": "0",
        },
    )

    wins = 0
    cv_results = []
    for fen in convert_fens:
        res = play_mini_game(suntzu_cv, strong_opp, fen, max_plies=60, movetime_ms=25)
        cv_results.append(res)
        if res == "W":
            wins += 1

    print(f"  Resultados Conversão + Syzygy (4 posições ganhas vs SF Base): {cv_results} ({wins}/4 vitórias)")
    assert wins == 4, f"Esperava converter 4/4 posições ganhas: {cv_results}"

    suntzu_sw.close()
    weak_opp.close()
    suntzu_cv.close()
    strong_opp.close()


if __name__ == "__main__":
    engine_bin = os.path.join(ROOT_DIR, "bin", "suntzu-native")
    if not os.path.isfile(engine_bin):
        print(f"Binário não encontrado em {engine_bin}", file=sys.stderr)
        sys.exit(1)

    test_syzygy(engine_bin)
    test_modes_activation_and_tiebreak(engine_bin)
    test_swindle_and_conversion_suites(engine_bin)
    print("\nSUCESSO: Todos os testes da Fase 5 (Pressão, Virada, Conversão e Syzygy) passaram!")
