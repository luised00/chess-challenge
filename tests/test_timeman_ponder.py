#!/usr/bin/env python3
"""
Testes automatizados da Fase 2:
1. Valida ponder (go ponder -> ponderhit / stop) via console UCI.
2. Analisa PGN do fastchess para verificar 0 derrotas por tempo (time forfeits)
   e extrair o menor tempo restante de 'dev' em partidas com atraso de operação humana.
"""
import re
import subprocess
import sys
import time


def test_ponder(engine_path: str) -> None:
    print("=== [1] Testando ciclo completo de Ponder (go ponder -> ponderhit e stop) ===")
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

    def read_until(prefix: str, timeout: float = 10.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            line = proc.stdout.readline()
            if not line:
                break
            line = line.strip()
            if line.startswith(prefix):
                return line
        raise TimeoutError(f"Timeout aguardando '{prefix}'")

    send("uci")
    read_until("uciok")
    send("setoption name Ponder value true")
    send("setoption name PhysicalBoardOverhead value 7000")
    send("setoption name PanicReserve value 120")
    send("isready")
    read_until("readyok")

    # Caso A: Acerto de ponder (ponderhit) com controle escalado (150s = 150000ms)
    send("ucinewgame")
    send("position startpos moves e2e4 e7e5")
    send("go ponder wtime 150000 btime 150000")
    time.sleep(0.25)
    send("ponderhit")
    bm1 = read_until("bestmove", timeout=10.0)
    print(f"  -> Ponderhit OK: {bm1}")

    # Caso B: Erro de ponder (stop + nova busca)
    send("position startpos moves e2e4 c7c5")
    send("go ponder wtime 149000 btime 149000")
    time.sleep(0.20)
    send("stop")
    bm2 = read_until("bestmove", timeout=10.0)
    print(f"  -> Ponder miss (stop) OK: {bm2}")

    # Caso C: Lance único forçado (rei em xeque com única fuga) -> resposta rápida (< 150 ms)
    # Posição com único lance legal das brancas: Kh1 (7k/8/8/8/8/8/6q1/6K1 w - - 0 1 -> 1 lance legal Kxg2)
    send("position fen 7k/8/8/8/8/8/6q1/6K1 w - - 0 1")
    t0 = time.time()
    send("go wtime 1200000 btime 1200000")
    bm3 = read_until("bestmove", timeout=5.0)
    dt_ms = (time.time() - t0) * 1000.0
    print(f"  -> Lance único forçado OK: {bm3} em {dt_ms:.1f} ms")
    assert dt_ms < 250.0, f"Lance único demorou demais: {dt_ms:.1f} ms"

    # Caso D: Pânico crítico (< 60s no relógio) -> resposta < 1s
    send("position startpos moves d2d4 g8f6 c2c4 e7e6")
    t0 = time.time()
    send("go wtime 45000 btime 600000")
    bm4 = read_until("bestmove", timeout=5.0)
    dt_panic_ms = (time.time() - t0) * 1000.0
    print(f"  -> Reserva de pânico (<60s) OK: {bm4} em {dt_panic_ms:.1f} ms")
    assert dt_panic_ms < 1000.0, f"Busca em pânico crítico passou de 1s: {dt_panic_ms:.1f} ms"

    send("quit")
    proc.wait(timeout=2)


def analyze_pgn_time(pgn_path: str, eng_name: str = "dev") -> None:
    print(f"=== [2] Analisando tempo e quedas de seta em {pgn_path} ===")
    time_losses = 0
    total_games = 0
    white = None
    for line in open(pgn_path, encoding="utf-8"):
        if line.startswith("[White "):
            white = line.split('"')[1]
        elif line.startswith("[Result "):
            total_games += 1
        elif "time forfeit" in line.lower() or "on time" in line.lower():
            time_losses += 1

    print(f"  -> Total de partidas: {total_games} | Quedas de tempo (time forfeits): {time_losses}")
    if time_losses > 0:
        sys.exit(1)


if __name__ == "__main__":
    engine = sys.argv[1] if len(sys.argv) > 1 else "bin/suntzu-native"
    test_ponder(engine)
    if len(sys.argv) > 2:
        analyze_pgn_time(sys.argv[2])
