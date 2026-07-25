#!/usr/bin/env python3
import json
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = pd.read_csv(ROOT / "artifacts_safezone/dram/manifest.csv")
    manifest = manifest[manifest.seed == 7]
    rows = []
    for injection in (4, 8, 16):
        for cid, group in manifest.groupby("config_id"):
            data = {}
            for row in group.itertuples():
                path = row.trace_path.replace(".trace", f"_inj{injection}.json")
                controllers = json.load(open(path))["memory_system"]["controller"]
                data[row.format] = (
                    max(x["cycles"] for x in controllers) - 4096, row
                )
            beic_cycles, beic = data["beicsr"]
            xor_cycles, xor = data["xorflow"]
            beic_total = beic_cycles + beic.descriptor_cycles
            serial = xor_cycles + xor.sampled_decode_cycles + xor.descriptor_cycles
            overlap = max(xor_cycles, xor.sampled_decode_cycles) + xor.descriptor_cycles
            rows.append({
                "config_id": cid,
                "transactions_32B_per_cycle": injection,
                "injection_bytes_per_cycle": injection * 32,
                "hbm_only_speedup": beic_cycles / xor_cycles,
                "serialized_speedup": beic_total / serial,
                "double_buffered_speedup": beic_total / overlap,
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results_safezone/56_hbm_injection_sensitivity.csv", index=False)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
