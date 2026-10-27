import sys

pgn, eng = sys.argv[1], sys.argv[2]
w = d = l = 0
white = None
for line in open(pgn, encoding="utf-8"):
    if line.startswith("[White "):
        white = line.split('"')[1]
    elif line.startswith("[Result "):
        r = line.split('"')[1]
        if r == "1/2-1/2":
            d += 1
        elif r in ("1-0", "0-1"):
            if (r == "1-0") == (white == eng):
                w += 1
            else:
                l += 1
print(f"V={w} E={d} D={l} | pontos 3-1-0: {3*w+d} x {3*l+d}")
