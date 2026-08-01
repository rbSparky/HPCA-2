#!/usr/bin/env python3
"""Write a strict, path-linked FP8 inference quality audit for cached traces."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


FLOORS = {
    "ogbn_arxiv": ("accuracy", 0.68),
    "reddit_": ("accuracy", 0.90),
    "yelp_": ("micro_f1", 0.45),
    "flickr_": ("accuracy", 0.45),
}


def _contract(config_id: str) -> tuple[str, float]:
    lowered = config_id.lower()
    for prefix, contract in FLOORS.items():
        if lowered.startswith(prefix):
            return contract
    return "accuracy", float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--configs", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); project = args.project.resolve()
    rows = []
    for config_id in args.configs:
        record = project / "artifacts_hpca_xorflow/workloads" / config_id / "record.json"
        support = record.with_name("fp8_supports.npz")
        metric, floor = _contract(config_id)
        if not record.exists() or not support.exists():
            rows.append({"config_id": config_id, "metric": metric, "floor": floor, "value": None, "status": "MISSING", "finite_loss": False, "record_path": str(record.relative_to(project)), "record_sha256": "", "supports_sha256": "", "reason": "missing record or packed FP8 supports"}); continue
        payload = json.loads(record.read_text())
        value = payload.get(f"fp8_fp16_test_{metric}")
        if value is None:
            value = payload.get(f"fp32_test_{metric}")
        finite = bool(payload.get("finite_loss", False))
        numeric = float(value) if value is not None else None
        if numeric is None or not finite:
            status = "INVALID"
        elif numeric >= floor:
            status = "HARD_VALID"
        elif metric == "micro_f1" and numeric >= floor - 0.02:
            status = "BORDERLINE"
        else:
            status = "INVALID"
        rows.append({
            "config_id": config_id, "metric": metric, "floor": floor, "value": numeric,
            "status": status, "finite_loss": finite,
            "record_path": str(record.relative_to(project)),
            "record_sha256": hashlib.sha256(record.read_bytes()).hexdigest(),
            "supports_sha256": hashlib.sha256(support.read_bytes()).hexdigest(),
            "reason": "meets predeclared floor" if status == "HARD_VALID" else ("within allowed reporting-only borderline band" if status == "BORDERLINE" else "quality contract not satisfied"),
        })
    output = args.output if args.output.is_absolute() else project / args.output
    output.parent.mkdir(parents=True, exist_ok=True); pd.DataFrame(rows).to_csv(output, index=False)
    if any(row["status"] == "MISSING" for row in rows):
        raise SystemExit("quality audit has missing required traces")


if __name__ == "__main__":
    main()
