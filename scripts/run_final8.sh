#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="/home/rishabh/miniconda/envs/taugat_pyg/bin/python"
cd "$PROJECT_ROOT"

PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PYTHON_BIN" -m pytest -q
PYTHONPATH=src "$PYTHON_BIN" -m mosaic_validation.final8_cli --project .
PYTHONPATH=src "$PYTHON_BIN" -m mosaic_validation.final8_controls --project .
"$PYTHON_BIN" scripts/finalize_final8.py
