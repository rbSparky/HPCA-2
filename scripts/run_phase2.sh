#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${MOSAIC_PYTHON:-/home/rishabh/miniconda/envs/taugat_pyg/bin/python}"
export PYTHONPATH="$ROOT/src"
export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
cd "$ROOT"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" -m pytest -q
"$PY" -m mosaic_validation.phase2_cli --config configs/phase2_quick.yaml
