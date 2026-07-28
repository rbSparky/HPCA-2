#!/usr/bin/env python3
"""Produce a compact, reviewer-auditable summary for one local toolchain run."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-tag", required=True)
    args = parser.parse_args()
    root = Path.cwd()
    results = root / "results_hpca_xorflow/complete_suite" / f"local_toolchain_{args.run_tag}"
    artifacts = root / "artifacts_hpca_xorflow/complete_suite" / f"local_toolchain_{args.run_tag}"
    checks = {
        "pytest": (artifacts / "pytest.log", "passed"),
        "cuda_microbench": (results / "cuda_microbench.csv", "true"),
        "dramsim3_hbm2": (results / "dramsim3_hbm2_smoke.json", '"tool_run_success": true'),
        "pipelined_synthesis": (artifacts / "pipelined_synthesis.log", "End of script"),
        "pipelined_cosim": (artifacts / "pipelined_cosim.log", "PASS cycles=9999"),
        "cacti": (artifacts / "cacti_default.log", "Access time (ns):"),
    }
    rows: list[dict[str, str]] = []
    for name, (path, marker) in checks.items():
        text = path.read_text(errors="replace") if path.exists() else ""
        rows.append({"step": name, "status": "SUCCEEDED" if marker in text else "FAILED", "artifact": str(path.relative_to(root))})
    with (results / "toolchain_status.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("step", "status", "artifact")); writer.writeheader(); writer.writerows(rows)
    dram = results / "dramsim3_hbm2_smoke.json"
    payload = {
        "run_tag": args.run_tag,
        "steps": rows,
        "dramsim3": json.loads(dram.read_text()) if dram.exists() else None,
        "cuda_rows": max(sum(1 for _ in (results / "cuda_microbench.csv").open()) - 1, 0) if (results / "cuda_microbench.csv").exists() else 0,
    }
    (results / "toolchain_summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
