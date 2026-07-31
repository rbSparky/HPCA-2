#!/usr/bin/env bash
# Deterministic dependency-ordered reviewer-spec worker for one CPU lane.
set -euo pipefail
[[ $# -eq 1 && "$1" =~ ^[0-3]$ ]] || { echo "usage: $0 LANE(0..3)" >&2; exit 2; }
lane="$1"; root="results_hpca_xorflow/reviewer_spec_v3"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"

case "$lane" in
  0) configs=(ogbn_arxiv_deepres8_w128_s7 ogbn_arxiv_deepres8_w128_s17 ogbn_arxiv_deepres8_w128_s27 citeseer_deepres8_w128_s7 chameleon_gcnii16 flickr_graphsage8_w128_s7_overnight ogbn_arxiv_deepres8_w256_s7 ogbn_arxiv_graphsage8_residual_w128_s7) ;;
  1) configs=(reddit_deepres8_w128_s7_native reddit_deepres8_w128_s17_native reddit_deepres8_w128_s27_native pubmed_gin8_w128_s7_overnight ogbn_arxiv_deepres4_w128_s7 ogbn_arxiv_gin8_w128_s7) ;;
  2) configs=(flickr_deepres8_w128_s7 flickr_deepres8_w128_s17 flickr_deepres8_w128_s27 pubmed_graphsage8_w128_s7_overnight cora_deepres28_w128 ogbn_arxiv_deepres16_w128_s7 ogbn_arxiv_graphsage8_w128_s7) ;;
  3) configs=(yelp_deepres8_w128_s7_balanced_fallback pubmed_gcnii16 flickr_gin8_w128_s7_overnight ogbn_arxiv_deepres8_w64_s7 ogbn_arxiv_gin8_residual_w128_s7) ;;
esac

is_primary() {
  case "$1" in
    ogbn_arxiv_deepres8_w128_s7|ogbn_arxiv_deepres8_w128_s17|ogbn_arxiv_deepres8_w128_s27|reddit_deepres8_w128_s7_native|reddit_deepres8_w128_s17_native|reddit_deepres8_w128_s27_native|flickr_deepres8_w128_s7|flickr_deepres8_w128_s17|flickr_deepres8_w128_s27|yelp_deepres8_w128_s7_balanced_fallback) return 0 ;;
    *) return 1 ;;
  esac
}

for cfg in "${configs[@]}"; do
  echo "[$(date -u +%FT%TZ)] START $cfg"
  records="$root/online_replay/support_records_${cfg}_finite_retention.csv"
  if [[ ! -s "$records" ]]; then
    extra=(--skip-serializer); is_primary "$cfg" && extra=()
    python scripts/run_spec_workload.py --config-id "$cfg" --output "$root" "${extra[@]}"
  fi
  char="$root/characterization/adjacent_support_${cfg}.csv"
  [[ -s "$char" ]] || python -m xorflow.characterization --project . --config-id "$cfg" --output "$char"
  ablation="$root/ablation/$cfg/component_ablation_${cfg}.csv"
  [[ -s "$ablation" ]] || python -m xorflow.ablation --project . --config-id "$cfg" --output-dir "$root/ablation/$cfg"
  traffic="$root/physical_traffic/physical_traffic_${cfg}.csv"
  [[ -s "$traffic" ]] || python -m xorflow.physical_traffic --project . --config-id "$cfg" --records "$records" --output "$traffic" --slice-width 128 --tile-rows 128 --feature-cache-bytes 524288 --edge-order O0
  encoder="$root/encoder/encoder_trace_${cfg}.csv"
  [[ -s "$encoder" ]] || python -m xorflow.encoder_sim --records "$records" --output "$encoder"
  for banks in 8 16 32; do
    decoder="$root/decoder/$cfg/decoder_cluster_trace_b${banks}.csv"
    [[ -s "$decoder" ]] || python -m xorflow.decoder_sim --records "$records" --stream-root "$root/online_replay" --output-dir "$root/decoder/$cfg" --banks "$banks" --lanes 8 --clusters 4
  done
  schedule="$root/schedule/$cfg/system_cycles.csv"
  [[ -s "$schedule" ]] || python -m xorflow.system_schedule --project . --config-id "$cfg" --records "$records" --traffic "$traffic" --encoder "$encoder" --decoder "$root/decoder/$cfg/decoder_cluster_trace_b16.csv" --output-dir "$root/schedule/$cfg"
  echo "[$(date -u +%FT%TZ)] COMPLETE $cfg"
done
