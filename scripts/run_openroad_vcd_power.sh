#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
flow="${ORFS_ROOT:-$HOME/src/OpenROAD-flow-scripts}/flow"
vcd="$root/results_hpca_xorflow/reviewer_spec_v3/decoder/vcd_or_saif/decoder_cluster_realstream.vcd"
test -s "$vcd"
cp "$root/scripts/openroad_vcd_power.tcl" "$flow/xorflow_vcd_power_tmp.tcl"
cp "$vcd" "$flow/xorflow_decoder_realstream_tmp.vcd"
cd "$flow"
set +e
util/docker_shell openroad -no_init -exit /work/xorflow_vcd_power_tmp.tcl > "$root/results_hpca_xorflow/reviewer_spec_v3/decoder/vcd_or_saif/openroad_vcd_power.log" 2>&1
rc=$?
set -e
PYTHONPATH="$root/src" "$root/scripts/collect_openroad_vcd_power.py" \
  --log "$root/results_hpca_xorflow/reviewer_spec_v3/decoder/vcd_or_saif/openroad_vcd_power.log" \
  --vcd "$vcd" \
  --output "$root/results_hpca_xorflow/reviewer_spec_v3/decoder/vcd_or_saif/openroad_vcd_power.json"
exit "$rc"
