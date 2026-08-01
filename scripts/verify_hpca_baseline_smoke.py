#!/usr/bin/env python3
"""Fail-closed audit for the first common-format Arxiv smoke run."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


EXPECTED = {"DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baselines", type=Path, required=True)
    parser.add_argument("--causal", type=Path, required=True)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    baseline = pd.read_csv(args.baselines)
    causal = pd.read_csv(args.causal)
    host = pd.read_csv(args.host)
    failures: list[str] = []
    if set(baseline.format) != EXPECTED:
        failures.append(f"baseline format set is {sorted(set(baseline.format))}, expected {sorted(EXPECTED)}")
    if len(baseline) != len(EXPECTED):
        failures.append(f"expected one row per baseline, observed {len(baseline)}")
    if not bool(baseline.exact_layout_pass.all()) or not bool(baseline.exact_decode_pass.all()):
        failures.append("a baseline layout/decode exactness flag is false")
    if not bool((baseline.total_traffic_bytes > 0).all()):
        failures.append("a baseline reported non-positive traffic")
    if len(causal) != 1 or not bool(causal.exact_decode_pass.all()) or not bool(causal.causal_deployable.all()):
        failures.append("causal preflight is missing, non-exact, or non-causal")
    if len(host) != 1 or not bool(host.combination_scalesim_success.all()) or not bool(host.support_cache_fits.all()):
        failures.append("host smoke lacks successful SCALE-Sim or a fitting support cache")
    audit = {
        "status": "PASS" if not failures else "FAIL",
        "baseline_rows": len(baseline),
        "causal_rows": len(causal),
        "host_rows": len(host),
        "best_independent_format": str(baseline.loc[baseline.total_traffic_bytes.idxmin(), "format"]) if len(baseline) else "",
        "failures": failures,
        "input_sha256": {
            name: hashlib.sha256(path.read_bytes()).hexdigest()
            for name, path in (("baselines", args.baselines), ("causal", args.causal), ("host", args.host))
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    if failures:
        raise SystemExit("baseline smoke audit failed: " + "; ".join(failures))
    print(json.dumps(audit, sort_keys=True))


if __name__ == "__main__":
    main()
