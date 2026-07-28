#!/usr/bin/env bash
# Route the throughput-preserving pipelined XORFLOW decoder lane in ORFS.
set -euo pipefail
ORFS="${ORFS_ROOT:-$HOME/src/OpenROAD-flow-scripts}"
FLOW="$ORFS/flow"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESIGN_HOME="$FLOW/designs"
mkdir -p "$DESIGN_HOME/src/xorflow_decoder_pipelined" "$DESIGN_HOME/nangate45/xorflow_decoder_pipelined"
cp "$PROJECT_ROOT/rtl/xorflow_decoder_pipelined.sv" "$DESIGN_HOME/src/xorflow_decoder_pipelined/"
cp "$PROJECT_ROOT/artifacts_safezone/openroad/xorflow_decoder_pipelined/rtl/constraint.sdc" "$DESIGN_HOME/nangate45/xorflow_decoder_pipelined/"
cp "$PROJECT_ROOT/artifacts_safezone/openroad/xorflow_decoder_pipelined/rtl/config.mk" "$DESIGN_HOME/nangate45/xorflow_decoder_pipelined/"
cd "$FLOW"
util/docker_shell make DESIGN_HOME=/work/designs DESIGN_CONFIG=/work/designs/nangate45/xorflow_decoder_pipelined/config.mk
