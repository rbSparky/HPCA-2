export DESIGN_NAME = xorflow_decoder_cluster8_pipelined
export PLATFORM = nangate45
export VERILOG_FILES = $(DESIGN_HOME)/src/xorflow_decoder_cluster8_pipelined/xorflow_decoder_pipelined.sv $(DESIGN_HOME)/src/xorflow_decoder_cluster8_pipelined/xorflow_decoder_cluster_pipelined.sv
export SDC_FILE = $(DESIGN_HOME)/$(PLATFORM)/xorflow_decoder_cluster8_pipelined/constraint.sdc
export ABC_AREA = 1
# The compact hierarchical top still has 827 control/status pins.  Reserve
# enough perimeter for deterministic IO placement; this is an explicit
# physical consequence of exposing a tile control interface, not a hidden
# timing/area fudge factor.
export CORE_UTILIZATION ?= 10
export PLACE_DENSITY_LB_ADDON = 0.20
export TNS_END_PERCENT = 100
export SYNTH_REPEATABLE_BUILD ?= 1
