#!/usr/bin/env bash
# Run the bounded local validation pipeline and retain every result in one
# timestamped paper-suite directory.  It never touches cluster GPU0/GPU1.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_TAG="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
PYTHON_BIN="${MOSAIC_PY:-<PROJECT_ROOT>"
RESULTS="$ROOT/results_hpca_xorflow/complete_suite/local_toolchain_$RUN_TAG"
ARTIFACTS="$ROOT/artifacts_hpca_xorflow/complete_suite/local_toolchain_$RUN_TAG"
mkdir -p "$RESULTS" "$ARTIFACTS"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"

STATUS_FILE="$RESULTS/toolchain_status.tsv"
printf 'step\tstatus\tlog\n' > "$STATUS_FILE"
run_step() {
  local name="$1"; shift
  local log="$ARTIFACTS/$name.log"
  if "$@" > "$log" 2>&1; then
    printf '%s\t%s\t%s\n' "$name" "SUCCEEDED" "$log" >> "$STATUS_FILE"
  else
    printf '%s\t%s\t%s\n' "$name" "FAILED" "$log" >> "$STATUS_FILE"
  fi
}

"$PYTHON_BIN" - <<'PY' > "$RESULTS/environment.json"
import json
import platform
import sys
import torch
print(json.dumps({
    "python": sys.version,
    "platform": platform.platform(),
    "torch": torch.__version__,
    "cuda": torch.version.cuda,
    "cuda_available": torch.cuda.is_available(),
    "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
}, indent=2, sort_keys=True))
PY

run_step pytest env PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$PYTHON_BIN" -m pytest -q
run_step cuda_microbench "$PYTHON_BIN" scripts/run_xorflow_cuda_bench.py \
  --output "$RESULTS/cuda_microbench.csv" --log "$ARTIFACTS/cuda_microbench.json" \
  --repetitions 100
run_step dramsim3_hbm2 "$PYTHON_BIN" scripts/run_dramsim3_smoke.py \
  --config tools/vendor/DRAMsim3/configs/HBM2_8Gb_x128.ini \
  --output "$RESULTS/dramsim3_hbm2_smoke.json"
run_step pipelined_synthesis scripts/synth_pipelined_decoder.sh
run_step pipelined_cosim scripts/run_xorflow_decoder_cosim.sh
run_step cacti_default scripts/cacti7_docker.sh

"$PYTHON_BIN" - <<PY > "$RESULTS/toolchain_summary.json"
import json
from pathlib import Path
root = Path(${RESULTS@Q})
artifacts = Path(${ARTIFACTS@Q})
cuda = root / "cuda_microbench.csv"
dram = root / "dramsim3_hbm2_smoke.json"
print(json.dumps({
    "run_tag": ${RUN_TAG@Q},
    "status": (root / "toolchain_status.tsv").read_text(),
    "cuda_rows": max(sum(1 for _ in cuda.open()) - 1, 0) if cuda.exists() else 0,
    "dramsim3": json.loads(dram.read_text()) if dram.exists() else None,
    "pipelined_cosim": (artifacts / "pipelined_cosim.log").read_text().strip().splitlines()[-1] if (artifacts / "pipelined_cosim.log").exists() else None,
}, indent=2, sort_keys=True))
PY

printf '%s\n' "$RESULTS"
