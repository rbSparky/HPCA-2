#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${MOSAIC_PYTHON:-/home/rishabh/miniconda/envs/taugat_pyg/bin/python}"
cd "$ROOT"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" -m pytest -q
