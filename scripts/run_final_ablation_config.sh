#!/usr/bin/env bash
set -euo pipefail
cfg="${1:?config id required}"
lifecycle="${2:?augmented record path required}"
root="${3:-results_hpca_xorflow/final_review4}"
shift_count=3
variants=()
if [[ $# -gt $shift_count ]]; then
  variants=(--variants "${@:4}")
fi
export PYTHONPATH="${PYTHONPATH:-}:src"
python_bin="${PYTHON_BIN:-python}"
"$python_bin" scripts/run_final_ablation_schedules.py \
  --config-id "$cfg" \
  --selected-dir "$root/ablation_records/records" \
  --lifecycle "$lifecycle" \
  --traffic "results_hpca_xorflow/reviewer_spec_v3/physical_traffic/physical_traffic_${cfg}.csv" \
  --encoder "results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_trace_${cfg}.csv" \
  --decoder "results_hpca_xorflow/reviewer_spec_v3/decoder/${cfg}/decoder_cluster_trace_b16.csv" \
  --output-dir "$root/ablation_schedules/${cfg}" \
  "${variants[@]}"
