#!/usr/bin/env bash
# Build and run cycle-accurate Verilator/software equivalence for the pipeline.
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$PROJECT_ROOT/artifacts_safezone/decoder/verilator_pipelined_cosim"
mkdir -p "$OUT"
verilator --cc --exe --build -Wno-fatal --top-module xorflow_decoder_lane_pipelined \
  "$PROJECT_ROOT/rtl/xorflow_decoder_pipelined.sv" \
  "$PROJECT_ROOT/tests/rtl/xorflow_decoder_pipelined_tb.cpp" \
  -Mdir "$OUT" -o xorflow_decoder_pipelined_tb
"$OUT/xorflow_decoder_pipelined_tb" | tee "$OUT/result.log"
