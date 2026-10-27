#!/usr/bin/env bash
# uso: tests/sprt.sh bin/suntzu-native bin/sf-base nome_do_teste [opcoes_extras_dev] [rounds]
set -euo pipefail

DEV_ENGINE="${1:?Informe o binário dev (ex: bin/suntzu-native)}"
BASE_ENGINE="${2:?Informe o binário base (ex: bin/sf-base)}"
TEST_NAME="${3:?Informe o nome do teste}"
EXTRA_DEV_OPTS="${4:-}"
ROUNDS="${5:-2000}"
CONCURRENCY="${CONCURRENCY:-4}"
TC="${TC:-10+0.1}"

mkdir -p tests/results

# shellcheck disable=SC2086
./fastchess/fastchess \
  -engine cmd="$DEV_ENGINE" name=dev option.PhysicalBoardOverhead=0 option.PanicReserve=0 $EXTRA_DEV_OPTS \
  -engine cmd="$BASE_ENGINE" name=base \
  -each tc="$TC" option.Hash=16 option.Threads=1 \
  -openings file=books/UHO.epd format=epd order=random \
  -rounds "$ROUNDS" -repeat -concurrency "$CONCURRENCY" \
  -sprt elo0=0 elo1=5 alpha=0.05 beta=0.05 \
  -pgnout file="tests/results/${TEST_NAME}.pgn"

python3 tests/score_310.py "tests/results/${TEST_NAME}.pgn" dev
