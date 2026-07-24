#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="${MOSAIC_PYTHON:-/home/rishabh/miniconda/envs/taugat_pyg/bin/python}"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
"$PY" -m pytest -q
"$PY" -m mosaic_validation.phase3a_cli --config configs/phase3a_quick.yaml
