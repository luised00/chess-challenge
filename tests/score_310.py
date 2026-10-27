#!/usr/bin/env python3
"""
Pontuação 3-1-0 de um PGN do fastchess, com intervalos de confiança.

uso: python3 tests/score_310.py <arquivo.pgn> <nome_do_motor> [--by-opponent] [--clock]

As partidas são agrupadas em pares (mesma abertura com cores invertidas, -repeat),
que são as unidades independentes usadas no bootstrap e no erro do Elo.
"""
import math
import random
import re
import sys
from collections import defaultdict

BOOTSTRAP = 2000
FALHAS = ("time forfeit", "illegal move", "stall", "disconnect", "crash")


def ler_partidas(pgn):
    jogos, tags = [], {}
    for line in open(pgn, encoding="utf-8", errors="replace"):
        if line.startswith("[Event ") and tags:
            jogos.append(tags)
            tags = {}
        if line.startswith("[") and '"' in line:
            tags[line[1:line.index(" ")]] = line.split('"')[1]
        elif tags:
            tags["_moves"] = tags.get("_moves", "") + line
    if tags:
        jogos.append(tags)
    return jogos


def relogio_minimo(t, eng):
    """Menor tempo restante (s) do motor na partida, a partir de 'tl=' (pgnout timeleft=true)."""
    tls = re.findall(r"\{[^}]*\}", t.get("_moves", ""))
    brancas_primeiro = t.get("FEN", " w").split()[1] == "w" if t.get("FEN") else True
    meu_primeiro = brancas_primeiro == (t["White"] == eng)
    meus = [c for i, c in enumerate(tls) if (i % 2 == 0) == meu_primeiro]
    vals = [float(m) for c in meus for m in re.findall(r"tl=([0-9.]+)s", c)]
    return min(vals) if vals else None


def pontos_310(res):
    return {"V": 3, "E": 1, "D": 0}[res]


def elo(score):
    score = min(max(score, 1e-6), 1 - 1e-6)
    return -400 * math.log10(1 / score - 1)


def resumo(rotulo, pares):
    """pares: lista de listas de resultados 'V'/'E'/'D' do ponto de vista do motor."""
    jogos = [r for p in pares for r in p]
    n = len(jogos)
    if n == 0:
        return f"{rotulo}: sem partidas"
    w, d, l = jogos.count("V"), jogos.count("E"), jogos.count("D")
    ppg = (3 * w + d) / n

    # Bootstrap dos pontos 3-1-0 por partida sobre os pares
    rng = random.Random(310)
    amostras = []
    for _ in range(BOOTSTRAP):
        s = [pares[rng.randrange(len(pares))] for _ in pares]
        g = [r for p in s for r in p]
        amostras.append(sum(map(pontos_310, g)) / len(g))
    amostras.sort()
    lo, hi = amostras[int(0.025 * BOOTSTRAP)], amostras[int(0.975 * BOOTSTRAP) - 1]

    # Elo clássico (V=1, E=0.5) com variância por par (pentanomial)
    sc = (w + 0.5 * d) / n
    medias = [sum({"V": 1, "E": 0.5, "D": 0}[r] for r in p) / len(p) for p in pares]
    var = sum((m - sc) ** 2 for m in medias) / max(len(medias) - 1, 1)
    se = math.sqrt(var / len(medias)) if len(medias) > 1 else 0.5
    e, e_lo, e_hi = elo(sc), elo(sc - 1.96 * se), elo(sc + 1.96 * se)
    txt_elo = f"Elo: {e:+.1f} +/- {(e_hi - e_lo)/2:.1f}" if 0.02 < sc < 0.98 else "Elo: fora de escala"

    return (f"{rotulo}: V={w} E={d} D={l} | pontos 3-1-0: {3*w+d} x {3*l+d}\n"
            f"  pontos/partida: {ppg:.3f} [IC95 {lo:.3f}–{hi:.3f}]  "
            f"empates: {100*d/n:.1f}%  "
            f"{txt_elo}  ({n} partidas, {len(pares)} pares)")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    por_oponente = "--by-opponent" in sys.argv
    if len(args) != 2:
        sys.exit("uso: score_310.py <arquivo.pgn> <nome_do_motor> [--by-opponent] [--clock]")
    pgn, eng = args

    grupos = defaultdict(lambda: defaultdict(list))
    falhas = defaultdict(int)
    relogios = []
    for t in ler_partidas(pgn):
        if eng not in (t.get("White"), t.get("Black")):
            continue
        op = t["Black"] if t["White"] == eng else t["White"]
        r = t["Result"]
        if r == "1/2-1/2":
            res = "E"
        elif r in ("1-0", "0-1"):
            res = "V" if (r == "1-0") == (t["White"] == eng) else "D"
        else:
            continue
        term = t.get("Termination", "").lower()
        if any(f in term for f in FALHAS) and res == "D":
            falhas[term] += 1
        if "--clock" in sys.argv:
            m = relogio_minimo(t, eng)
            if m is not None:
                relogios.append(m)
        chave = (t.get("Round", ""), t.get("FEN", ""))
        grupos[op][chave].append(res)

    todos = [p for g in grupos.values() for p in g.values()]
    if not todos:
        # Mantém o formato antigo mesmo sem partidas
        print("V=0 E=0 D=0 | pontos 3-1-0: 0 x 0")
        return
    print(resumo(eng, todos))
    if por_oponente:
        for op in sorted(grupos):
            print(resumo(f"  vs {op}", list(grupos[op].values())))
    if falhas:
        print("  derrotas por falha: " + ", ".join(f"{k}={v}" for k, v in falhas.items()))
    else:
        print("  derrotas por falha (tempo/ilegal/crash): 0")
    if relogios:
        relogios.sort()
        print(f"  relógio mínimo por partida: pior {relogios[0]:.1f}s, "
              f"mediana {relogios[len(relogios)//2]:.1f}s ({len(relogios)} partidas)")


if __name__ == "__main__":
    main()
