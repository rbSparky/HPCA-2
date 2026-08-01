#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
YOSYS_BIN="${YOSYS_BIN:-$(command -v yosys || true)}"
if [[ -z "$YOSYS_BIN" ]]; then
  YOSYS_BIN="<PROJECT_ROOT>"
fi
OUT="$PROJECT_ROOT/artifacts_safezone/decoder"
mkdir -p "$OUT"

"$YOSYS_BIN" -p "
  read_verilog -sv $PROJECT_ROOT/rtl/xorflow_decoder.sv;
  hierarchy -check -top xorflow_decoder_lane;
  synth -noabc -flatten -top xorflow_decoder_lane;
  stat;
  ltp -noff;
" > "$OUT/lane_synthesis.log"

"$YOSYS_BIN" -p "
  read_verilog -sv $PROJECT_ROOT/rtl/xorflow_decoder.sv;
  hierarchy -check -top xorflow_decoder_bank;
  synth -noabc -flatten -top xorflow_decoder_bank;
  stat;
  ltp -noff;
" > "$OUT/bank_synthesis.log"

"$YOSYS_BIN" -p "
  read_verilog -sv -D FORMAL $PROJECT_ROOT/rtl/xorflow_decoder.sv;
  prep -top xorflow_decoder_lane;
  sat -verify -set mode 0 -prove formal_dense_ok 1;
  sat -verify -set mode 1 -prove formal_nondense_ok 1;
  sat -verify -set mode 2 -prove formal_gap0_ok 1;
  sat -verify -set mode 2 -prove formal_gap7_ok 1;
" > "$OUT/formal.log"
