#!/usr/bin/env python3
"""Fail-closed audit for an exact B0–B4/X0–X2/oracle format matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


EXPECTED = {
    "DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST",
    "X0_CAUSAL_INDEPENDENT", "X1_CAUSAL_AUTO", "X2_CAUSAL_FORCE",
    "O0_OFFLINE_MAJORITY", "O1_FREE_SUPPORT",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frame = pd.read_csv(args.input)
    failures: list[str] = []
    if set(frame.format) != EXPECTED:
        failures.append("format set does not match the predeclared common matrix")
    if len(frame) != len(EXPECTED):
        failures.append("matrix must contain exactly one row per format for this smoke pair")
    if not bool(frame.exact_layout_pass.all()) or not bool(frame.exact_decode_pass.all()):
        failures.append("an exactness flag is false")
    if not bool((frame.total_traffic_bytes > 0).all()):
        failures.append("a format has non-positive traffic")
    deployable = frame.set_index("format").deployable.to_dict()
    for name in ("DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST", "X0_CAUSAL_INDEPENDENT", "X1_CAUSAL_AUTO", "X2_CAUSAL_FORCE"):
        if not bool(deployable.get(name, False)):
            failures.append(f"{name} must be deployable")
    for name in ("O0_OFFLINE_MAJORITY", "O1_FREE_SUPPORT"):
        if bool(deployable.get(name, True)):
            failures.append(f"{name} must remain a non-deployable oracle")
    x1 = frame.loc[frame.format == "X1_CAUSAL_AUTO"].iloc[0]
    audit = {
        "status": "PASS" if not failures else "FAIL",
        "rows": len(frame),
        "x1_traffic_ratio_to_beicsr": float(x1.traffic_ratio_to_beicsr),
        "x1_selected_tile_slices": int(x1.selected_xorflow_tile_slices),
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "failures": failures,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    if failures:
        raise SystemExit("format-matrix audit failed: " + "; ".join(failures))
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
