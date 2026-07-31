#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/artifacts_hpca_xorflow/complete_suite/decoder_cluster_rtl"
mkdir -p "$out"
yosys -p "read_verilog -sv $root/rtl/xorflow_decoder_pipelined.sv $root/rtl/xorflow_decoder_cluster_pipelined.sv; hierarchy -check -top xorflow_decoder_cluster8_pipelined; proc; opt; techmap; opt; abc -g simple; clean; stat" > "$out/yosys_cluster_synthesis.log"
verilator --lint-only --Wall --Wno-fatal "$root/rtl/xorflow_decoder_pipelined.sv" "$root/rtl/xorflow_decoder_cluster_pipelined.sv" > "$out/verilator_cluster_lint.log" 2>&1
build="$out/cluster_obj_dir"
mkdir -p "$build"
verilator --cc --exe --build --Wno-fatal --top-module xorflow_decoder_cluster8_debug \
  --Mdir "$build" "$root/rtl/xorflow_decoder_pipelined.sv" "$root/rtl/xorflow_decoder_cluster_pipelined.sv" \
  "$root/rtl/xorflow_decoder_cluster_tb.cpp" -o decoder_cluster_tb >/dev/null
"$build/decoder_cluster_tb" | tee "$out/decoder_cluster_cosim.log"
cp "$out/yosys_cluster_synthesis.log" "$root/results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_rtl_synthesis.log"
cp "$out/verilator_cluster_lint.log" "$root/results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_verilator_lint.log"
cp "$out/decoder_cluster_cosim.log" "$root/results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_cosim.log"
echo "$out"
