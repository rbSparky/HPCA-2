#!/usr/bin/env bash
# Run the corrected causal finite-queue schedule for one bounded CPU lane.
set -euo pipefail
[[ $# -eq 1 && "$1" =~ ^[0-3]$ ]] || { echo 'usage: run_corrected_schedule_lane.sh LANE(0..3)' >&2; exit 2; }
lane="$1"; root="results_hpca_xorflow/artifact_runs"; log="$root/schedule/corrected_lane_${lane}.log"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
case "$lane" in
  0) configs=(ogbn_arxiv_deepres8_w128_s7 ogbn_arxiv_deepres8_w128_s17 ogbn_arxiv_deepres8_w128_s27 citeseer_deepres8_w128_s7 chameleon_gcnii16 flickr_graphsage8_w128_s7_overnight ogbn_arxiv_deepres8_w256_s7 ogbn_arxiv_graphsage8_residual_w128_s7) ;;
  1) configs=(reddit_deepres8_w128_s7_native reddit_deepres8_w128_s17_native reddit_deepres8_w128_s27_native pubmed_gin8_w128_s7_overnight ogbn_arxiv_deepres4_w128_s7 ogbn_arxiv_gin8_w128_s7) ;;
  2) configs=(flickr_deepres8_w128_s7 flickr_deepres8_w128_s17 flickr_deepres8_w128_s27 pubmed_graphsage8_w128_s7_overnight cora_deepres28_w128 ogbn_arxiv_deepres16_w128_s7 ogbn_arxiv_graphsage8_w128_s7) ;;
  3) configs=(yelp_deepres8_w128_s7_balanced_fallback pubmed_gcnii16 flickr_gin8_w128_s7_overnight ogbn_arxiv_deepres8_w64_s7 ogbn_arxiv_gin8_residual_w128_s7) ;;
esac
mkdir -p "$(dirname "$log")"; : > "$log"
for cfg in "${configs[@]}"; do
  records="$root/online_replay/support_records_${cfg}_finite_retention.csv"
  traffic="$root/physical_traffic/physical_traffic_${cfg}.csv"
  encoder="$root/encoder/encoder_trace_${cfg}.csv"
  decoder="$root/decoder/$cfg/decoder_cluster_trace_b16.csv"
  if [[ ! -s "$records" || ! -s "$traffic" || ! -s "$encoder" || ! -s "$decoder" ]]; then
    echo "$(date -u +%FT%TZ) FAIL $cfg missing dependency" | tee -a "$log"; exit 3
  fi
  echo "$(date -u +%FT%TZ) START $cfg" | tee -a "$log"
  python -m xorflow.causal_schedule --project . --config-id "$cfg" --records "$records" --traffic "$traffic" --encoder "$encoder" --decoder "$decoder" --output-dir "$root/schedule/$cfg" >>"$log" 2>&1
  echo "$(date -u +%FT%TZ) COMPLETE $cfg" | tee -a "$log"
done
