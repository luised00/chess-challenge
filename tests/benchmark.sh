#!/usr/bin/env bash
# Benchmark completo do SunTzu: não regressão (SPRT), escada 3-1-0 e condições de torneio.
# uso: tests/benchmark.sh [quick|full|smoke]
#   quick: ~2h  (SPRT STC limitado, escada curta, 20 partidas de torneio)
#   full:  noite inteira ou mais (SPRT STC + LTC até decidir, escada de 200 rounds, 200 partidas de torneio)
set -euo pipefail

MODE="${1:-quick}"
CONCURRENCY="${CONCURRENCY:-14}"
NAME="bench_$(date +%Y%m%d_%H%M)"
OUT="tests/results/$NAME"
mkdir -p "$OUT"
export CONCURRENCY

case "$MODE" in
  quick) SPRT_ROUNDS=1000; LADDER_ROUNDS=50;  TORNEIO_ROUNDS=10;  LTC=false ;;
  full)  SPRT_ROUNDS=20000; LADDER_ROUNDS=200; TORNEIO_ROUNDS=100; LTC=true ;;
  smoke) SPRT_ROUNDS=4;     LADDER_ROUNDS=1;   TORNEIO_ROUNDS=1;   LTC=false ;;
  *) echo "uso: $0 [quick|full|smoke]"; exit 1 ;;
esac

STC=10+0.1
# Torneio real: 25 min sudden death. Escalado para 5 min (fator 1/5):
# atraso físico 7 s -> 1.4 s, reserva de pânico 120 s -> 24 s
TORNEIO_TC=300+0
LAG=1400
RESERVA=24
if [ "$MODE" = smoke ]; then STC=1+0.01; TORNEIO_TC=30+0; LAG=140; RESERVA=2; fi

DEV_OPTS="option.SunTzu=true option.OwnBook=true option.SyzygyPath=$PWD/syzygy"

{
  echo "# Benchmark SunTzu — $NAME ($MODE)"
  echo
  echo "Commit: \`$(git rev-parse --short HEAD)\`  Máquina: $(nproc) núcleos, concurrency $CONCURRENCY"
  echo
} > "$OUT/summary.md"

secao() { echo -e "\n## $1\n\n\`\`\`" >> "$OUT/summary.md"; }
fim() { echo '```' >> "$OUT/summary.md"; }

# 1. Não regressão contra o Stockfish 19 base (SunTzu completo, sem atraso físico)
secao "1. Não regressão vs sf-base — STC $STC, SPRT [-5, 0]"
SPRT_BOUNDS="-5 0" TC=$STC tests/sprt.sh bin/suntzu-native bin/sf-base "$NAME/sprt_stc" \
  "$DEV_OPTS" "$SPRT_ROUNDS" > "$OUT/sprt_stc.log" 2>&1
tail -n 12 "$OUT/sprt_stc.log" >> "$OUT/summary.md"
fim

if [ "$LTC" = true ]; then
  secao "1b. Não regressão vs sf-base — LTC 60+0.6, SPRT [-5, 0]"
  SPRT_BOUNDS="-5 0" TC=60+0.6 tests/sprt.sh bin/suntzu-native bin/sf-base "$NAME/sprt_ltc" \
    "$DEV_OPTS" "$SPRT_ROUNDS" > "$OUT/sprt_ltc.log" 2>&1
  tail -n 12 "$OUT/sprt_ltc.log" >> "$OUT/summary.md"
  fim
fi

# 2. Escada 3-1-0: SunTzu ligado x desligado, mesmas aberturas
secao "2. Escada de oponentes 3-1-0 (SunTzu on x off)"
TC=$STC tests/ladder.sh "$OUT" "$LADDER_ROUNDS" > "$OUT/ladder.log" 2>&1
sed -n '/^### SunTzu/,$p' "$OUT/ladder.log" >> "$OUT/summary.md"
fim

# 3. Condições de torneio escaladas (atraso físico real via lag_proxy)
secao "3. Torneio escalado — $TORNEIO_TC, atraso ${LAG} ms, reserva ${RESERVA} s"
# shellcheck disable=SC2086
LAG_MS=$LAG ./fastchess/fastchess \
  -engine cmd=tests/lag_suntzu.sh name=dev option.PhysicalBoardOverhead=$LAG option.PanicReserve=$RESERVA $DEV_OPTS \
  -engine cmd=bin/sf-base name=base \
  -each tc="$TORNEIO_TC" option.Hash=64 option.Threads=1 \
  -openings file=books/UHO.epd format=epd order=random \
  -rounds "$TORNEIO_ROUNDS" -repeat -concurrency "$CONCURRENCY" -recover \
  -pgnout file="$OUT/torneio.pgn" timeleft=true > "$OUT/torneio.log" 2>&1
python3 tests/score_310.py "$OUT/torneio.pgn" dev --clock >> "$OUT/summary.md"
fim

echo "Resumo em $OUT/summary.md"
cat "$OUT/summary.md"
