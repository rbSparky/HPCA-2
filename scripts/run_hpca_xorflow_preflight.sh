#!/usr/bin/env bash
# Causal XORFLOW stage-1: exact support bytes and cache-line traffic only.
# It deliberately does not overwrite any preserved Phase-0--safe-zone result.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${MOSAIC_PY:-/home/rishabh/miniconda/envs/taugat_pyg/bin/python}"
log_dir="$project_root/artifacts_hpca_xorflow/logs"
mkdir -p "$log_dir"

cd "$project_root"
{
  date -u +'%Y-%m-%dT%H:%M:%SZ'
  printf 'python=%s\n' "$python_bin"
  "$python_bin" - <<'PY'
import platform, torch
print(f"python_version={platform.python_version()}")
print(f"torch={torch.__version__}")
print(f"cuda_available={torch.cuda.is_available()}")
print(f"gpu={torch.cuda.get_device_name(0) if torch.cuda.is_available() else ''}")
PY
  PYTHONPATH=src "$python_bin" -m mosaic_validation.hpca_xorflow_cli \
    --configs cora_gcnii16 pubmed_gcnii16 cora_deepres28_w128 ogbn_arxiv_deepres8_w128 \
    --slice-width 128 --tile-rows 128 --feature-cache-bytes $((512 * 1024)) --edge-order O0
} 2>&1 | tee "$log_dir/run_hpca_xorflow_preflight.log"
