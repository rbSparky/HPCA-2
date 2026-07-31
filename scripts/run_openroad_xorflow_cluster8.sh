#!/usr/bin/env bash
set -euo pipefail
ORFS="${ORFS_ROOT:-$HOME/src/OpenROAD-flow-scripts}"
FLOW="$ORFS/flow"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESIGN_HOME="$FLOW/designs"
mkdir -p "$DESIGN_HOME/src/xorflow_decoder_cluster8_pipelined" "$DESIGN_HOME/nangate45/xorflow_decoder_cluster8_pipelined"
cp "$PROJECT_ROOT/rtl/xorflow_decoder_pipelined.sv" "$DESIGN_HOME/src/xorflow_decoder_cluster8_pipelined/"
cp "$PROJECT_ROOT/rtl/xorflow_decoder_cluster_pipelined.sv" "$DESIGN_HOME/src/xorflow_decoder_cluster8_pipelined/"
cp "$PROJECT_ROOT/configs/orfs_xorflow_decoder_cluster8.mk" "$DESIGN_HOME/nangate45/xorflow_decoder_cluster8_pipelined/config.mk"
cp "$PROJECT_ROOT/configs/orfs_xorflow_decoder_cluster8.sdc" "$DESIGN_HOME/nangate45/xorflow_decoder_cluster8_pipelined/constraint.sdc"
cd "$FLOW"
util/docker_shell make DESIGN_HOME=/work/designs DESIGN_CONFIG=/work/designs/nangate45/xorflow_decoder_cluster8_pipelined/config.mk
