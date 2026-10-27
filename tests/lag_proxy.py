#!/usr/bin/env python3
"""
Proxy UCI para simular atraso de operação humana (tabuleiro físico) em testes com fastchess.

Uso:
  python3 tests/lag_proxy.py <caminho_do_motor> [delay_ms]
ou via variável de ambiente:
  LAG_MS=700 python3 tests/lag_proxy.py bin/suntzu-native
"""
import os
import subprocess
import sys
import threading
import time


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Uso: lag_proxy.py <engine_bin> [delay_ms]\n")
        sys.exit(1)

    engine_cmd = sys.argv[1]
    delay_ms = float(sys.argv[2]) if len(sys.argv) >= 3 else float(os.environ.get("LAG_MS", "700"))
    delay_sec = max(0.0, delay_ms / 1000.0)

    proc = subprocess.Popen(
        [engine_cmd],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )

    def forward_stdin():
        try:
            for line in sys.stdin:
                if proc.stdin:
                    proc.stdin.write(line)
                    proc.stdin.flush()
                if line.strip() == "quit":
                    break
        except BrokenPipeError:
            pass

    t = threading.Thread(target=forward_stdin, daemon=True)
    t.start()

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if line.startswith("bestmove ") and delay_sec > 0:
                time.sleep(delay_sec)
            sys.stdout.write(line)
            sys.stdout.flush()
    except BrokenPipeError:
        pass
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    main()
