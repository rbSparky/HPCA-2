#!/usr/bin/env python3
"""Expose the reviewer-requested codec/component decomposition.

The underlying ablation campaign already evaluates every variant with the
same physical layout, cache, and traffic accounting.  This table renames the
existing variants into the reviewer vocabulary and selects the best legal
slice width independently for each component.
"""
from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ABL = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3" / "ablation"
OUT = ABL / "ablation_decomposition.csv"

MAP = {
    "BEICSR_OPT": "optimized_BEICSR",
    "EVENT_ONLY": "independent_A0",
    "A2_ONLY": "independent_A2",
    "XOR_NO_A2": "fixed_anchor_XOR_without_A2",
    "FORCED_XORFLOW": "forced_delta",
    "FULL_ONLINE_SERIAL": "complete_XORFLOW_serial",
    "FULL_ONLINE_EVENT": "complete_XORFLOW_event",
    "GENERIC_XOR_RLE": "generic_XOR_RLE",
    "PAIR_ORACLE_UPPER_BOUND": "pair_oracle_non_deployable",
}

FIELDS = [
    "config_id", "component", "source_variant", "slice_width", "anchor_policy",
    "total_physical_bytes", "cycles", "support_bytes", "value_bytes", "topology_bytes",
    "descriptor_bytes", "padding_bytes", "deployable", "same_physical_accounting",
]


def main() -> None:
    output: list[dict[str, object]] = []
    for path in sorted(ABL.glob("*/component_ablation_*.csv")):
        rows = list(csv.DictReader(path.open()))
        if not rows:
            continue
        config = rows[0]["run_id"]
        for source, component in MAP.items():
            candidates = [r for r in rows if r["variant"] == source]
            if not candidates:
                continue
            chosen = min(candidates, key=lambda r: (int(r["cycles"]), int(r["slice_width"])))
            output.append({
                "config_id": config, "component": component, "source_variant": source,
                "slice_width": chosen["slice_width"], "anchor_policy": chosen["anchor_policy"],
                "total_physical_bytes": chosen["total_physical_bytes"], "cycles": chosen["cycles"],
                "support_bytes": chosen["support_bytes"], "value_bytes": chosen["value_bytes"],
                "topology_bytes": chosen["topology_bytes"], "descriptor_bytes": chosen["descriptor_bytes"],
                "padding_bytes": chosen["padding_bytes"], "deployable": chosen["deployable"],
                "same_physical_accounting": True,
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS); writer.writeheader(); writer.writerows(output)
    print(f"configs={len({r['config_id'] for r in output})} rows={len(output)} output={OUT}")


if __name__ == "__main__":
    main()
