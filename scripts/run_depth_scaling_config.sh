#!/usr/bin/env bash
# Train, capture, and run the corrected XORFLOW pipeline for one depth point.
set -euo pipefail

[[ $# -ge 1 && $# -le 2 ]] || { echo "usage: $0 CONFIG_ID [full|train|analyze]" >&2; exit 2; }
cfg="$1"
stage="${2:-full}"
[[ "$stage" == full || "$stage" == train || "$stage" == analyze ]] || {
  echo "invalid stage: $stage" >&2; exit 2;
}
root="results_hpca_xorflow/depth_scaling"
artifact="artifacts_hpca_xorflow/workloads/$cfg"
log="$root/logs/${cfg}.log"
export PYTHONPATH="$PWD/src${PYTHONPATH:+:$PYTHONPATH}"
mkdir -p "$root/logs"

case "$cfg" in
  ogbn_arxiv_deepres24_w128_s7) dataset=ogbn-arxiv; layers=24; extra=() ;;
  ogbn_arxiv_deepres32_w128_s7) dataset=ogbn-arxiv; layers=32; extra=() ;;
  reddit_deepres12_w128_s7_native) dataset=reddit; layers=12; extra=(--learning-rate 0.001 --csr-checkpoint-training) ;;
  reddit_deepres16_w128_s7_native) dataset=reddit; layers=16; extra=(--learning-rate 0.001 --csr-checkpoint-training) ;;
  yelp_deepres12_w128_s7_balanced_fallback) dataset=yelp; layers=12; extra=(--max-epochs 220 --csr-checkpoint-training --multi-label-pos-weight) ;;
  yelp_deepres16_w128_s7_balanced_fallback) dataset=yelp; layers=16; extra=(--max-epochs 220 --csr-checkpoint-training --multi-label-pos-weight) ;;
  flickr_deepres16_w128_s7) dataset=flickr; layers=16; extra=() ;;
  *) echo "unsupported depth-scaling configuration: $cfg" >&2; exit 2 ;;
esac

exec > >(tee -a "$log") 2>&1
echo "$(date -u +%FT%TZ) START config=$cfg stage=$stage gpu=${CUDA_VISIBLE_DEVICES:-unset}"
if [[ "$stage" != analyze && ( ! -s "$artifact/fp8_supports.npz" || ! -s "$artifact/record.json" ) ]]; then
  train=(python scripts/train_hpca_workload.py
    --dataset "$dataset" --config-id "$cfg" --seed 7 --width 128 --layers "$layers"
    --model-kind deepres --max-epochs 160 --min-epochs 50 --patience 25
    --learning-rate 0.005 --dropout 0.20 --residual-scale 0.20)
  train+=("${extra[@]}")
  printf 'TRAIN_COMMAND='; printf '%q ' "${train[@]}"; printf '\n'
  "${train[@]}"
else
  echo "$(date -u +%FT%TZ) REUSE verified cached trace $artifact/fp8_supports.npz"
fi

if [[ "$stage" == train ]]; then
  echo "$(date -u +%FT%TZ) COMPLETE config=$cfg stage=train"
  exit 0
fi
[[ -s "$artifact/fp8_supports.npz" && -s "$artifact/record.json" ]] || {
  echo "missing trained artifact for analysis: $artifact" >&2; exit 3;
}

python scripts/run_spec_workload.py --config-id "$cfg" --output "$root"
python -m xorflow.characterization --project . --config-id "$cfg" \
  --output "$root/characterization/adjacent_support_${cfg}.csv"
records="$root/online_replay/support_records_${cfg}_finite_retention.csv"
traffic="$root/physical_traffic/physical_traffic_${cfg}.csv"
encoder="$root/encoder/encoder_trace_${cfg}.csv"
python -m xorflow.physical_traffic --project . --config-id "$cfg" --records "$records" \
  --output "$traffic" --slice-width 128 --tile-rows 128 --feature-cache-bytes 524288 --edge-order O0
python -m xorflow.encoder_sim --records "$records" --output "$encoder"
for banks in 16 32; do
  python -m xorflow.decoder_sim --records "$records" --stream-root "$root/online_replay" \
    --output-dir "$root/decoder/$cfg" --banks "$banks" --lanes 8 --clusters 4
done
python -m xorflow.causal_schedule --project . --config-id "$cfg" --records "$records" \
  --traffic "$traffic" --encoder "$encoder" \
  --decoder "$root/decoder/$cfg/decoder_cluster_trace_b16.csv" \
  --output-dir "$root/schedule/$cfg"
echo "$(date -u +%FT%TZ) COMPLETE config=$cfg stage=$stage"
