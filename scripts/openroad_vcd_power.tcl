# OpenROAD activity check for the routed compact decoder top.
# The VCD is generated from the same physical top and serialized test stream.
read_db /work/results/nangate45/xorflow_decoder_cluster8_pipelined/base/6_final.odb
read_liberty /work/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
read_spef /work/results/nangate45/xorflow_decoder_cluster8_pipelined/base/6_final.spef
read_sdc /work/results/nangate45/xorflow_decoder_cluster8_pipelined/base/6_final.sdc
read_vcd /work/xorflow_decoder_realstream_tmp.vcd -scope TOP
report_power
