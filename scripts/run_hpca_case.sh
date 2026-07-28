#!/usr/bin/env bash
# Run one isolated causal-XORFLOW preflight and normalized-host sensitivity.
# Every invocation writes under a caller-specified directory so results cannot
# overwrite another queue item.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 CONFIG_ID RUN_ID [slice_width] [feature_cache_bytes] [edge_order] [tile_rows] [support_cache_bytes] [dram_bytes_per_cycle] [decoder_lanes] [single_buffered]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_ID="$1"; RUN_ID="$2"
SLICE_WIDTH="${3:-128}"; FEATURE_CACHE_BYTES="${4:-524288}"
EDGE_ORDER="${5:-O0}"; TILE_ROWS="${6:-128}"
SUPPORT_CACHE_BYTES="${7:-16384}"; DRAM_BYTES_PER_CYCLE="${8:-256}"
DECODER_LANES="${9:-32}"; SINGLE_BUFFERED="${10:-0}"
PYTHON_BIN="${MOSAIC_PY:-python3}"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
RUN_DIR="$ROOT/results_hpca_xorflow/complete_suite/runs/$RUN_ID"
mkdir -p "$RUN_DIR"

PREFLIGHT="$RUN_DIR/causal_preflight.csv"
HOST="$RUN_DIR/host_model.csv"
"$PYTHON_BIN" -m mosaic_validation.hpca_xorflow_cli \
  --configs "$CONFIG_ID" --max-pairs 2 --slice-width "$SLICE_WIDTH" \
  --feature-cache-bytes "$FEATURE_CACHE_BYTES" --edge-order "$EDGE_ORDER" \
  --tile-rows "$TILE_ROWS" --output "$PREFLIGHT"

HOST_ARGS=(--input "$PREFLIGHT" --output "$HOST"
  --support-cache-bytes "$SUPPORT_CACHE_BYTES"
  --dram-bytes-per-cycle "$DRAM_BYTES_PER_CYCLE"
  --decoder-lanes "$DECODER_LANES" --encoder-lanes "$DECODER_LANES")
if [[ "$SINGLE_BUFFERED" == "1" ]]; then HOST_ARGS+=(--single-buffered); fi
"$PYTHON_BIN" -m mosaic_validation.hpca_host "${HOST_ARGS[@]}"
