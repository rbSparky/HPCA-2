#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${MOSAIC_PYTHON:-/home/rishabh/miniconda/envs/taugat_pyg/bin/python}"
cd "$ROOT"
export CUBLAS_WORKSPACE_CONFIG="${CUBLAS_WORKSPACE_CONFIG:-:4096:8}"
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PY" -m pytest -q
PYTHONPATH=src "$PY" -m mosaic_validation.cli --config configs/quick.yaml
