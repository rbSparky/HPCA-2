#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${MOSAIC_PYTHON:-/home/rishabh/miniconda/envs/taugat_pyg/bin/python}"
export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
export PYTHONPATH="$ROOT/src"
cd "$ROOT"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" -m pytest -q
"$PY" -m mosaic_validation.phase1_cli --config configs/phase1_quick.yaml
