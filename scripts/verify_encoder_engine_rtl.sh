#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/artifacts_hpca_xorflow/complete_suite/encoder_rtl"
build="$out/engine_obj_dir"
mkdir -p "$out" "$build"
verilator --cc --exe --build --Wno-fatal --top-module xorflow_encoder_tile_engine \
  --Mdir "$build" "$root/rtl/xorflow_encoder_pipelined.sv" "$root/rtl/xorflow_encoder_engine_tb.cpp" \
  -o encoder_engine_tb >/dev/null
"$build/encoder_engine_tb" | tee "$out/encoder_engine_cosim.log"
cp "$out/encoder_engine_cosim.log" "$root/results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_engine_cosim.log"
