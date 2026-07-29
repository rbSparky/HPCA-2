#!/usr/bin/env python3
"""Aggregate isolated HPCA campaign runs into reviewer-facing evidence tables."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def _geomean(values: pd.Series) -> float:
    positive = values[values > 0]
    return float(positive.prod() ** (1.0 / len(positive))) if len(positive) else float("nan")


def run(project: Path) -> pd.DataFrame:
    root = project / "results_hpca_xorflow/complete_suite"
    # Isolated cases are deliberately written to one stable result root.  The
    # campaign ledgers live under ``paper_suite_*`` while their case outputs
    # live under ``runs/``; keeping the latter outside campaign directories
    # makes reruns replace only the intended case and keeps one reviewer-facing
    # table across primary, remediation, and sensitivity campaigns.
    # Keep compatibility with the original per-campaign layout used by small
    # artifact tests, while preferring the current shared ``runs/`` root.
    hosts = sorted({
        *root.glob("runs/*/host_model.csv"),
        *root.glob("paper_suite_*/runs/*/host_model.csv"),
    })
    records: list[dict[str, object]] = []
    for path in hosts:
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        config_id = str(frame.iloc[0]["config_id"])
        record_path = project / "artifacts_hpca_xorflow/workloads" / config_id / "record.json"
        quality = json.loads(record_path.read_text()) if record_path.exists() else {}
        preflight_path = path.parent / "causal_preflight.csv"
        preflight = pd.read_csv(preflight_path) if preflight_path.exists() else pd.DataFrame()
        traffic = preflight.get("traffic_reduction", frame.get("traffic_reduction", pd.Series(dtype=float)))
        support_ratio = preflight.get("support_ratio_to_beicsr", frame.get("support_ratio_to_beicsr", pd.Series(dtype=float)))
        records.append({
            "config_id": config_id,
            "run_id": path.parent.name,
            "pairs": len(frame),
            "host_speedup_geomean": _geomean(frame["host_speedup"]),
            "traffic_reduction_mean": float(traffic.mean()),
            "support_ratio_mean": float(support_ratio.mean()),
            "serialized_speedup_geomean": _geomean(preflight.get("serialized_speedup", pd.Series(dtype=float))),
            "support_cache_fits": bool(frame["support_cache_fits"].all()),
            "fp32_test_accuracy": quality.get("fp32_test_accuracy"),
            "fp8_fp16_test_accuracy": quality.get("fp8_fp16_test_accuracy"),
            "accuracy_drop": quality.get("accuracy_drop"),
            "host_csv": str(path.relative_to(project)),
        })
    output = pd.DataFrame(records)
    output_path = root / "PAPER_SUITE_HOST_SUMMARY.csv"
    output.to_csv(output_path, index=False)
    lines = [
        "# HPCA XORFLOW Consolidated Host Results",
        "",
        "All values below are modeled aggregation+combination host estimates, not measured end-to-end accelerator speedups.",
        "",
        "| Configuration | Run | Pairs | Host speedup (geomean) | Serialized-memory speedup | Mean traffic reduction | Mean support ratio | FP8 quality |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in records:
        quality = row["fp8_fp16_test_accuracy"]
        quality_text = "" if quality is None else f"{float(quality):.4f}"
        lines.append(
            f"| {row['config_id']} | {row['run_id']} | {row['pairs']} | "
            f"{float(row['host_speedup_geomean']):.3f}× | {float(row['serialized_speedup_geomean']):.3f}× | {float(row['traffic_reduction_mean']):.1%} | "
            f"{float(row['support_ratio_mean']):.3f} | {quality_text} |"
        )
    lines += ["", f"Machine-readable table: `{output_path.name}`."]
    (root / "PAPER_SUITE_HOST_RESULTS.md").write_text("\n".join(lines) + "\n")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = run(args.project.resolve())
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
