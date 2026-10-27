#!/usr/bin/env bash
# Escada de oponentes 3-1-0: compara SunTzu=true x SunTzu=false contra a mesma escada.
# uso: tests/ladder.sh <diretorio_saida> [rounds_por_oponente]
#   OPENINGS=books/UHO.epd TC=10+0.1 CONCURRENCY=14 SEED=310
set -euo pipefail

OUT="${1:?Informe o diretório de saída (ex: tests/results/bench_x)}"
ROUNDS="${2:-200}"
CONCURRENCY="${CONCURRENCY:-14}"
TC="${TC:-10+0.1}"
OPENINGS="${OPENINGS:-books/UHO.epd}"
SEED="${SEED:-310}"
DEV="${DEV:-bin/suntzu-native}"
BASE="${BASE:-bin/sf-base}"

mkdir -p "$OUT"

for ARM in on off; do
  if [ "$ARM" = on ]; then OPTS="option.SunTzu=true option.OwnBook=true"; else OPTS="option.SunTzu=false option.OwnBook=false"; fi
  # shellcheck disable=SC2086
  ./fastchess/fastchess \
    -tournament gauntlet -seeds 1 \
    -engine cmd="$DEV" name=dev option.PhysicalBoardOverhead=0 option.PanicReserve=0 $OPTS \
    -engine cmd="$BASE" name=forte \
    -engine cmd="$BASE" name=medio option.UCI_LimitStrength=true option.UCI_Elo=2800 \
    -engine cmd="$BASE" name=fraco option.UCI_LimitStrength=true option.UCI_Elo=2200 \
    -engine cmd="$BASE" name=muito_fraco "option.Skill Level=5" \
    -each tc="$TC" option.Hash=16 option.Threads=1 \
    -openings file="$OPENINGS" format=epd order=random -srand "$SEED" \
    -rounds "$ROUNDS" -repeat -concurrency "$CONCURRENCY" -recover \
    -pgnout file="$OUT/ladder_suntzu_${ARM}.pgn"
done

for ARM in on off; do
  echo "### SunTzu=$ARM"
  python3 tests/score_310.py "$OUT/ladder_suntzu_${ARM}.pgn" dev --by-opponent
done
