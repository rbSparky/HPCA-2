#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
decoder="results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_trace.csv"
out_root="${REVIEW5_OUT_ROOT:-results_hpca_xorflow/final_review5_unified/primary}"

for cfg_dir in results_hpca_xorflow/final_review4/ablation_schedules/*; do
    test -d "$cfg_dir/prepared/COMPLETE_XORFLOW" || continue
    cfg="$(basename "$cfg_dir")"
    prep="$cfg_dir/prepared/COMPLETE_XORFLOW"
    out="$out_root/$cfg"
    mkdir -p "$out"
    if test -s "$out/causal_event_schedule.csv"; then
        continue
    fi
    echo "START $(date -u +%FT%TZ) $cfg"
    PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 ./.phase1-python -m xorflow.causal_schedule \
        --project . --config-id "$cfg" \
        --records "$prep/COMPLETE_XORFLOW_records.csv" \
        --traffic "$prep/COMPLETE_XORFLOW_traffic.csv" \
        --encoder "$prep/COMPLETE_XORFLOW_encoder.csv" \
        --decoder "$decoder" --output-dir "$out" > "$out/run.log" 2>&1
    echo "DONE  $(date -u +%FT%TZ) $cfg"
done
