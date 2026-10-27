#!/usr/bin/env bash
# Wrapper executável para o fastchess rodar bin/suntzu-native através do lag_proxy.py
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "${ROOT_DIR}/tests/lag_proxy.py" "${ROOT_DIR}/bin/suntzu-native" "${LAG_MS:-700}"
