#!/usr/bin/env python3
"""Build the canonical, path-linked XORFLOW paper evidence ledger.

The ledger is intentionally long-form: every reported scalar retains its exact
CSV source and SHA-256. Missing paper requirements are emitted as
``UNASSESSED`` gate rows instead of being hidden by an attractive partial plot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(project: Path, path: Path) -> str:
    return str(path.resolve().relative_to(project.resolve()))


def _quality(project: Path, config_id: str) -> tuple[str, float | None, str]:
    record = project / "artifacts_hpca_xorflow/workloads" / config_id / "record.json"
    if not record.exists():
        return "UNKNOWN", None, ""
    payload = json.loads(record.read_text())
    metric = str(payload.get("quality_metric", "accuracy"))
    for key in (f"fp8_fp16_test_{metric}", f"fp32_test_{metric}"):
        if payload.get(key) is not None:
            return metric, float(payload[key]), _relative(project, record)
    return metric, None, _relative(project, record)


def _rows_from_csv(project: Path, path: Path) -> list[dict[str, object]]:
    try:
        frame = pd.read_csv(path)
    except Exception as exc:
        return [{"section": "invalid_csv", "config_id": "", "validity": "UNASSESSED", "format": "", "metric": "parse_error", "value": str(exc), "unit": "", "scope": "", "source_path": _relative(project, path), "source_sha256": _sha(path)}]
    source = _relative(project, path); digest = _sha(path)
    result: list[dict[str, object]] = []
    for _, row in frame.iterrows():
        config_id = str(row.get("config_id", ""))
        metric_name, metric_value, _ = _quality(project, config_id)
        validity = "UNKNOWN" if metric_value is None else "RECORDED"
        common = {
            "config_id": config_id, "validity": validity,
            "format": str(row.get("format", "")), "source_path": source,
            "source_sha256": digest,
        }
        if path.name == "host_model.csv":
            for metric in ("host_speedup", "beicsr_host_cycles", "xorflow_host_cycles", "combination_scalesim_utilization"):
                if metric in row:
                    result.append({**common, "section": "host", "metric": metric, "value": row[metric], "unit": "ratio" if "speedup" in metric or "utilization" in metric else "cycles", "scope": str(row.get("model_scope", ""))})
        elif path.name == "causal_preflight.csv" or path.name == "causal_x1.csv":
            for metric in ("support_ratio_to_beicsr", "traffic_reduction", "serialized_speedup", "double_buffered_speedup", "xorflow_total_bytes", "beicsr_total_bytes"):
                if metric in row:
                    unit = "ratio" if metric != "traffic_reduction" else "fraction"
                    if metric.endswith("bytes"):
                        unit = "bytes"
                    result.append({**common, "section": "causal_preflight", "metric": metric, "value": row[metric], "unit": unit, "scope": "causal two-layer"})
        elif "format" in row and "total_traffic_bytes" in row:
            for metric in ("total_traffic_bytes", "traffic_ratio_to_beicsr", "traffic_reduction_vs_beicsr", "support_index_bytes", "feature_cache_misses"):
                if metric in row:
                    unit = "bytes" if "bytes" in metric else ("ratio" if "ratio" in metric or "reduction" in metric else "count")
                    result.append({**common, "section": "format_matrix", "metric": metric, "value": row[metric], "unit": unit, "scope": "common physical/cache model"})
        elif path.parent.name == "ramulator":
            for metric in ("dram_cycles", "speedup_vs_beicsr", "requests", "served_requests"):
                if metric in row:
                    result.append({**common, "section": "ramulator", "metric": metric, "value": row[metric], "unit": "ratio" if "speedup" in metric else ("cycles" if "cycles" in metric else "count"), "scope": "full emitted trace"})
    return result


def _gate_rows(project: Path, root: Path, evidence: pd.DataFrame) -> pd.DataFrame:
    required = {"ogbn_arxiv_deepres8_w128_s17", "reddit_deepres8_w128_s7_native"}
    observed = set(evidence.loc[evidence.section == "format_matrix", "config_id"].astype(str))
    has_full = required.issubset(observed)
    exact = evidence.loc[evidence.section.isin(["format_matrix", "causal_preflight"])]
    exact_sources = bool(len(exact))
    return pd.DataFrame([
        {"gate_id": "common_format_matrix", "status": "PASS" if has_full else "UNASSESSED", "description": "All required primary configurations have common format rows.", "evidence": "format_matrix"},
        {"gate_id": "exact_format_outputs", "status": "PASS" if exact_sources else "UNASSESSED", "description": "At least one exact common-format source has been audited; final gate requires every primary row.", "evidence": "format_matrix/causal_preflight"},
        {"gate_id": "reproducibility", "status": "UNASSESSED", "description": "Principal matrix rerun hash comparison is required before final decision.", "evidence": "reproduction/"},
        {"gate_id": "ppa_energy", "status": "UNASSESSED", "description": "CACTI/OpenROAD final subsystem PPA and energy table pending.", "evidence": "ppa/"},
    ])


def build(project: Path) -> tuple[Path, Path, Path]:
    root = project / "results_hpca_xorflow/complete_suite"
    sources = sorted({
        *root.glob("runs/*/host_model.csv"),
        *root.glob("runs/*/causal_preflight.csv"),
        *root.glob("baselines/**/*.csv"),
        *root.glob("timing/**/*.csv"),
        *root.glob("paper_suite_*/ramulator/*.csv"),
    })
    records = [entry for path in sources for entry in _rows_from_csv(project, path)]
    columns = ("section", "config_id", "validity", "format", "metric", "value", "unit", "scope", "source_path", "source_sha256")
    evidence = pd.DataFrame(records, columns=columns)
    evidence_csv = root / "HPCA_PAPER_EVIDENCE.csv"; evidence.to_csv(evidence_csv, index=False)
    gates = _gate_rows(project, root, evidence)
    gates_csv = root / "HPCA_PAPER_GATES.csv"; gates.to_csv(gates_csv, index=False)
    try:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=project, text=True).strip()
    except Exception:
        commit = "unknown"
    manifest = {
        "generated_utc": datetime.now(timezone.utc).isoformat(), "git_commit": commit,
        "source_files": [{"path": _relative(project, path), "sha256": _sha(path)} for path in sources],
        "evidence_rows": len(evidence), "gates": gates.to_dict("records"),
    }
    manifest_path = root / "HPCA_PAPER_MANIFEST.json"; manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    md = [
        "# XORFLOW Paper Evidence",
        "",
        "This is the canonical, path-linked evidence inventory. It intentionally distinguishes completed evidence from unassessed paper requirements; no oracle is a deployable result.",
        "",
        "## Gate inventory",
        "",
        "| Gate | Status | Evidence |",
        "|---|---|---|",
    ]
    md += [f"| {row.gate_id} | {row.status} | {row.evidence} |" for row in gates.itertuples(index=False)]
    md += ["", "## Source inventory", "", "| Section | Rows | Source files |", "|---|---:|---:|"]
    for section, group in evidence.groupby("section", dropna=False):
        md.append(f"| {section} | {len(group)} | {group.source_path.nunique()} |")
    md += ["", f"Machine-readable ledger: `{evidence_csv.name}`.", f"Gate table: `{gates_csv.name}`.", f"Manifest: `{manifest_path.name}`."]
    md_path = root / "HPCA_PAPER_EVIDENCE.md"; md_path.write_text("\n".join(md) + "\n")
    return md_path, evidence_csv, gates_csv


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args(); paths = build(args.project.resolve())
    print("\n".join(str(path) for path in paths))


if __name__ == "__main__":
    main()
