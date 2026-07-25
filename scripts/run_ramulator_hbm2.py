#!/usr/bin/env python3
"""Run an LD/ST trace through the pinned Ramulator 2.1 HBM2 model."""
import json
import sys

import ramulator


trace_path, output_path = sys.argv[1:3]
transactions_per_cycle = int(sys.argv[3]) if len(sys.argv) > 3 else 8
# HBM2 transactions are 32 bytes, so eight requests per memory cycle match
# the declared 256 B/cycle accelerator-side injection bandwidth.
frontend = ramulator.frontend.LoadStoreTrace(
    clock_ratio=transactions_per_cycle, path=trace_path
)
controllers = []
for _ in range(8):
    dram = ramulator.dram.HBM2(
        org_preset="HBM2_2Gb", timing_preset="HBM2_2000Mbps"
    )
    controllers.append(
        ramulator.controller.HBM12(
            dram=dram,
            scheduler=ramulator.scheduler.FRFCFS(),
            refresh_manager=ramulator.refresh_manager.AllBank(),
            row_policy=ramulator.row_policy.Open(),
            addr_mapper=ramulator.addr_mapper.RoBaRaCoCh(),
        )
    )
memory = ramulator.memory_system.GenericDRAM(
    clock_ratio=1,
    controllers=controllers,
    channel_mapper=ramulator.channel_mapper.CacheLineInterleave(),
)
simulation = ramulator.Simulation(frontend, memory)
simulation.run()
stats = simulation.stats
simulation.finalize()
with open(output_path, "w") as handle:
    json.dump(stats, handle, indent=2)
