#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/artifacts_hpca_xorflow/complete_suite/encoder_rtl"
build="$out/engine_obj_dir"
mkdir -p "$out" "$build"
verilator --cc --exe --build --trace --Wno-fatal --top-module xorflow_encoder_tile_engine \
  --Mdir "$build" "$root/rtl/xorflow_encoder_pipelined.sv" "$root/rtl/xorflow_encoder_engine_tb.cpp" \
  -o encoder_engine_tb >/dev/null
"$build/encoder_engine_tb" | tee "$out/encoder_engine_cosim.log"
cp "$out/encoder_engine_cosim.log" "$root/results_hpca_xorflow/artifact_runs/encoder/encoder_engine_cosim.log"

stream_build="$out/stream_obj_dir"
mkdir -p "$stream_build"
verilator --cc --exe --build --trace --Wno-fatal --top-module xorflow_encoder_stream_engine \
  --Mdir "$stream_build" "$root/rtl/xorflow_encoder_pipelined.sv" "$root/rtl/xorflow_encoder_stream_tb.cpp" \
  -o encoder_stream_tb >/dev/null
"$stream_build/encoder_stream_tb" | tee "$out/encoder_stream_cosim.log"
cp "$out/encoder_stream_cosim.log" "$root/results_hpca_xorflow/artifact_runs/encoder/encoder_stream_cosim.log"
