#!/usr/bin/env python3
"""Collect OpenROAD VCD-annotated power without turning warnings into claims."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--log", type=Path, required=True)
    p.add_argument("--vcd", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    text = args.log.read_text(errors="replace")
    annotations = re.findall(r"Annotated (\d+) pin activities", text)
    totals = re.findall(r"Total\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+100\.0%", text)
    # The first report can be the unannotated default; the last is the scoped
    # TOP VCD report and is the one retained below.
    power = totals[-1] if totals else ("", "", "", "")
    payload = {
        "tool": "OpenROAD",
        "openroad_vcd_scope": "TOP",
        "vcd": str(args.vcd),
        "vcd_sha256": sha(args.vcd),
        "annotated_pin_activities": int(annotations[-1]) if annotations else 0,
        "annotation_pass": bool(annotations and int(annotations[-1]) > 0),
        "internal_power_w": power[0], "switching_power_w": power[1],
        "leakage_power_w": power[2], "total_power_w": power[3],
        "power_status": "VCD_ANNOTATED_OPENROAD_REPORT" if annotations and int(annotations[-1]) > 0 else "NO_VCD_ANNOTATION",
        "clock_warning": "clock clk vcd period 0.002 differs from SDC clock period 1.000" in text,
        "note": "A real serialized support-stream prefix from the Arxiv s17 online replay was mapped onto the routed compact cluster; this is not a full-workload energy result.",
        "log_sha256": sha(args.log),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
