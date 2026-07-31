#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$root/artifacts_hpca_xorflow/complete_suite/encoder_rtl"
mkdir -p "$out"
yosys -p "read_verilog -sv $root/rtl/xorflow_encoder_pipelined.sv; hierarchy -check -top xorflow_encoder_pipelined; proc; opt; techmap; opt; abc -g simple; clean; stat" > "$out/yosys_encoder_synthesis.log"
# The 384-bit fixed-ID packing bus is intentionally retained for exactness.
# Keep this wide RTL evidence build at the proc/RTL-cell level; global boolean
# rewriting of the full tile packer is prohibitively expensive on a laptop and
# is not needed to establish elaboration, finite state, and cell accounting.
yosys -p "read_verilog -sv $root/rtl/xorflow_encoder_pipelined.sv; hierarchy -check -top xorflow_encoder_tile_engine; proc; opt; clean; stat" > "$out/yosys_encoder_engine_synthesis.log"
verilator --lint-only --Wall --Wno-fatal "$root/rtl/xorflow_encoder_pipelined.sv" > "$out/verilator_encoder_lint.log" 2>&1
cp "$out/yosys_encoder_synthesis.log" "$root/results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_rtl_synthesis.log"
cp "$out/yosys_encoder_engine_synthesis.log" "$root/results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_engine_rtl_synthesis.log"
cp "$out/verilator_encoder_lint.log" "$root/results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_verilator_lint.log"
echo "$out"
