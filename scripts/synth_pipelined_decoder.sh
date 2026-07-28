#!/usr/bin/env bash
# Synthesize both hierarchy levels of the timing-closed XORFLOW decoder.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YOSYS_BIN="${YOSYS_BIN:-$(command -v yosys || true)}"
if [[ -z "$YOSYS_BIN" ]]; then
  echo "error: yosys is required" >&2
  exit 1
fi
OUT="$PROJECT_ROOT/artifacts_safezone/decoder"
mkdir -p "$OUT"

for top in xorflow_decoder_lane_pipelined xorflow_decoder_bank_pipelined; do
  "$YOSYS_BIN" -p "
    read_verilog -sv $PROJECT_ROOT/rtl/xorflow_decoder_pipelined.sv;
    hierarchy -check -top $top;
    synth -noabc -flatten -top $top;
    stat;
  " > "$OUT/${top}_synthesis.log"
done
