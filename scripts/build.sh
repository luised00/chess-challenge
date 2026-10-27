#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/src"
BIN_DIR="${ROOT_DIR}/bin"
JOBS="${JOBS:-$(nproc 2>/dev/null || echo 4)}"

mkdir -p "${BIN_DIR}"
cd "${SRC_DIR}"

echo "=== [1/4] Verificando rede NNUE ==="
make net

echo "=== [2/4] Compilando build principal (PGO ARCH=native) ==="
make clean
make -j"${JOBS}" profile-build ARCH=native
cp stockfish "${BIN_DIR}/suntzu-native"

echo "=== [3/4] Verificando bench de bin/suntzu-native ==="
"${BIN_DIR}/suntzu-native" bench 2>&1 | tail -n 6

echo "=== [4/4] Compilando build reserva (ARCH=x86-64-avx2) ==="
make clean
make -j"${JOBS}" build ARCH=x86-64-avx2
cp stockfish "${BIN_DIR}/suntzu-avx2"
make clean

echo "=== Build concluído com sucesso ==="
ls -lh "${BIN_DIR}/suntzu-native" "${BIN_DIR}/suntzu-avx2"
