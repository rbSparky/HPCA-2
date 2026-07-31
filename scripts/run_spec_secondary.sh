#!/usr/bin/env bash
# One dependency-complete CPU job for a secondary/ablation trace.
set -euo pipefail
[[ $# -eq 1 ]] || { echo "usage: $0 CONFIG_ID" >&2; exit 2; }
cfg="$1"; root="results_hpca_xorflow/reviewer_spec_v3"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
python scripts/run_spec_workload.py --config-id "$cfg" --output "$root" --skip-serializer
python -m xorflow.characterization --project . --config-id "$cfg" --output "$root/characterization/adjacent_support_${cfg}.csv"
python -m xorflow.ablation --project . --config-id "$cfg" --output-dir "$root/ablation/$cfg"
records="$root/online_replay/support_records_${cfg}_finite_retention.csv"
traffic="$root/physical_traffic/physical_traffic_${cfg}.csv"
python -m xorflow.physical_traffic --project . --config-id "$cfg" --records "$records" --output "$traffic" --slice-width 128 --tile-rows 128 --feature-cache-bytes 524288 --edge-order O0
encoder="$root/encoder/encoder_trace_${cfg}.csv"
python -m xorflow.encoder_sim --records "$records" --output "$encoder"
for banks in 16 32; do
  python -m xorflow.decoder_sim --records "$records" --stream-root "$root/online_replay" --output-dir "$root/decoder/$cfg" --banks "$banks" --lanes 8 --clusters 4
done
python -m xorflow.system_schedule --project . --config-id "$cfg" --records "$records" --traffic "$traffic" --encoder "$encoder" --decoder "$root/decoder/$cfg/decoder_cluster_trace_b16.csv" --output-dir "$root/schedule/$cfg"
