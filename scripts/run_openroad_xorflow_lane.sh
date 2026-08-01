#!/usr/bin/env bash
# Reproduce the bounded routed PPA audit in the verified ORFS Docker image.
set -euo pipefail
ORFS="${ORFS_ROOT:-$HOME/src/OpenROAD-flow-scripts}"
FLOW="$ORFS/flow"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DESIGN_HOME="$FLOW/designs"
mkdir -p "$DESIGN_HOME/src/xorflow_decoder" "$DESIGN_HOME/src/xorflow_decoder_lane" "$DESIGN_HOME/nangate45/xorflow_decoder_lane"
cp "$PROJECT_ROOT/rtl/xorflow_decoder.sv" "$DESIGN_HOME/src/xorflow_decoder/xorflow_decoder.sv"
cp "$PROJECT_ROOT/artifacts_safezone/openroad/xorflow_decoder_lane/rtl/xorflow_decoder_lane_top.v" "$DESIGN_HOME/src/xorflow_decoder_lane/"
cp "$PROJECT_ROOT/artifacts_safezone/openroad/xorflow_decoder_lane/rtl/config.mk" "$DESIGN_HOME/nangate45/xorflow_decoder_lane/"
cp "$PROJECT_ROOT/artifacts_safezone/openroad/xorflow_decoder_lane/rtl/constraint.sdc" "$DESIGN_HOME/nangate45/xorflow_decoder_lane/"
cd "$FLOW"
util/docker_shell make DESIGN_HOME=/work/designs DESIGN_CONFIG=/work/designs/nangate45/xorflow_decoder_lane/config.mk
