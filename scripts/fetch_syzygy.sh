#!/usr/bin/env bash
# Instala tablebases Syzygy de 3 e 4 peças (e opcionalmente 5 peças com --5man) em ./syzygy
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SYZYGY_DIR="${ROOT_DIR}/syzygy"
mkdir -p "${SYZYGY_DIR}"

CACHE_TB="$(find "${HOME}/.cache" -path "*/syzygy/regular/KPvK.rtbw" 2>/dev/null | head -1 || true)"
if [[ -n "${CACHE_TB}" ]]; then
    SRC_DIR="$(dirname "${CACHE_TB}")"
    cp -f "${SRC_DIR}"/*.rtbw "${SRC_DIR}"/*.rtbz "${SYZYGY_DIR}/"
    echo "[syzygy] Copiados $(ls -1 "${SYZYGY_DIR}"/*.rtbw | wc -l) arquivos WDL e $(ls -1 "${SYZYGY_DIR}"/*.rtbz | wc -l) DTZ (3-4 peças) do cache local para ${SYZYGY_DIR}"
elif [[ -d "${ROOT_DIR}/tests/syzygy/data/syzygy/regular" ]]; then
    cp -f "${ROOT_DIR}/tests/syzygy/data/syzygy/regular"/*.rtbw "${ROOT_DIR}/tests/syzygy/data/syzygy/regular"/*.rtbz "${SYZYGY_DIR}/"
    echo "[syzygy] Copiados arquivos de 3-4 peças de tests/syzygy para ${SYZYGY_DIR}"
else
    echo "[syzygy] Baixando tablebases de 3-4 peças..."
    python3 -c "import sys; sys.path.insert(0, '${ROOT_DIR}/tests'); from testing import Syzygy; Syzygy.download_syzygy()"
    cp -f "${ROOT_DIR}/tests/syzygy/data/syzygy/regular"/*.rtbw "${ROOT_DIR}/tests/syzygy/data/syzygy/regular"/*.rtbz "${SYZYGY_DIR}/"
fi

if [[ "${1:-}" == "--5man" ]]; then
    echo "[syzygy] Baixando tablebases de 5 peças de tablebase.sesse.net/syzygy/3-4-5/ ..."
    wget -q -np -nd -r -l 1 -A "*.rtbw,*.rtbz" -P "${SYZYGY_DIR}" http://tablebase.sesse.net/syzygy/3-4-5/
fi

echo "[syzygy] Pronto em ${SYZYGY_DIR}"
