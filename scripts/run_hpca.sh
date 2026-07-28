#!/usr/bin/env bash
# Staged, content-addressed XORFLOW artifact entrypoint.  `--quick` never
# trains or downloads; it uses existing traces.  `--full` is intentionally
# explicit so expensive public-workload training cannot start by accident.
set -euo pipefail

MODE="quick"
STAGE="all"
if [[ "${1:-}" == "--full" ]]; then MODE="full"; shift; fi
if [[ "${1:-}" == "--quick" ]]; then MODE="quick"; shift; fi
if [[ "${1:-}" == "--stage" ]]; then STAGE="${2:?stage required}"; shift 2; fi
if [[ $# -ne 0 ]]; then echo "usage: $0 [--quick|--full] [--stage prepare|train|trace|encode|simulate|rtl|report|reproduce|overnight|all]" >&2; exit 2; fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="${MOSAIC_PY:-python3}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT"
mkdir -p artifacts_hpca_xorflow/logs results_hpca_xorflow
run() { "$@"; }

if [[ "$STAGE" == "prepare" || "$STAGE" == "all" ]]; then
  if [[ "$MODE" == "full" ]]; then
    run "$PYTHON_BIN" scripts/prepare_hpca_datasets.py --datasets Flickr Reddit Yelp
  else
    run "$PYTHON_BIN" - <<'PY'
from pathlib import Path
assert Path('artifacts_safezone/ogbn_arxiv/supports.npz').exists(), 'quick mode needs cached Arxiv trace'
print('quick prepare: cached inputs verified')
PY
  fi
fi
if [[ "$STAGE" == "train" || "$STAGE" == "all" ]]; then
  if [[ "$MODE" != "full" ]]; then echo "quick mode intentionally does not train"; else
    echo "Full training is workload-specific; invoke scripts/train_hpca_workload.py with a recorded config ID." >&2
  fi
fi
if [[ "$STAGE" == "trace" ]]; then
  echo "Trace capture is performed atomically by train_hpca_workload.py after exact full-neighbour inference."
fi
if [[ "$STAGE" == "encode" || "$STAGE" == "all" ]]; then
  run "$PYTHON_BIN" -m mosaic_validation.hpca_xorflow_cli --configs ogbn_arxiv_deepres8_w128
fi
if [[ "$STAGE" == "simulate" || "$STAGE" == "all" ]]; then
  run "$PYTHON_BIN" -m mosaic_validation.hpca_host
fi
if [[ "$STAGE" == "rtl" ]]; then
  run scripts/synth_decoder.sh
fi
if [[ "$STAGE" == "report" || "$STAGE" == "reproduce" ]]; then
  run "$PYTHON_BIN" -m pytest -q
fi
if [[ "$STAGE" == "overnight" ]]; then
  # Dependency-aware GPU-1 admission/tranche controller.  This command does
  # not train a missing model or turn a borderline metric into a hard gate.
  run "$PYTHON_BIN" -m mosaic_validation.hpca_overnight --stage overnight
fi
