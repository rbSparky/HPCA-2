#!/usr/bin/env python3
"""Parse real HBM2 timings and add decode/descriptor pipeline costs."""
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = pd.read_csv(ROOT / "artifacts_safezone/dram/manifest.csv")
    values = []
    for row in manifest.itertuples():
        stats = json.load(open(row.trace_path.replace(".trace", ".json")))
        controllers = stats["memory_system"]["controller"]
        submitted = sum(item["num_read_reqs"] for item in controllers)
        served = sum(item["num_read_reqs_served"] for item in controllers)
        values.append({
            **row._asdict(),
            "ramulator_cycles": max(item["cycles"] for item in controllers) - 4096,
            "requests_submitted": submitted,
            "requests_served": served,
            "drain_complete": submitted == served,
        })
    frame = pd.DataFrame(values)
    rows = []
    for (cid, seed), group in frame.groupby(["config_id", "seed"]):
        beic = group[group.format == "beicsr"].iloc[0]
        xor = group[group.format == "xorflow"].iloc[0]
        beic_total = beic.ramulator_cycles + beic.descriptor_cycles
        xor_serial = (
            xor.ramulator_cycles + xor.sampled_decode_cycles
            + xor.descriptor_cycles
        )
        xor_overlap = max(
            xor.ramulator_cycles, xor.sampled_decode_cycles
        ) + xor.descriptor_cycles
        rows.append({
            "config_id": cid,
            "seed": seed,
            "beicsr_hbm_cycles": beic.ramulator_cycles,
            "xorflow_hbm_cycles": xor.ramulator_cycles,
            "xorflow_decode_cycles": xor.sampled_decode_cycles,
            "descriptor_cycles_each": xor.descriptor_cycles,
            "hbm_only_speedup": beic.ramulator_cycles / xor.ramulator_cycles,
            "serialized_speedup": beic_total / xor_serial,
            "double_buffered_speedup": beic_total / xor_overlap,
            "all_requests_drained": bool(beic.drain_complete and xor.drain_complete),
        })
    result = pd.DataFrame(rows)
    result.to_csv(ROOT / "results_safezone/55_ramulator_hbm2.csv", index=False)
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
