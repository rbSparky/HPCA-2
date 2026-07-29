#!/usr/bin/env python3
"""Render the live, deadline-aware paper-suite progress dashboard.

Task state is deliberate and versioned in a small YAML file: generated output
never guesses that an experiment completed merely because a similarly named
directory exists.  This keeps scientific completion distinct from a stale or
partial artifact.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import yaml


VALID = {"pending", "in_progress", "complete", "blocked"}


def _status_label(status: str) -> str:
    return {"pending": "PENDING", "in_progress": "IN PROGRESS", "complete": "COMPLETE", "blocked": "BLOCKED"}[status]


def render(project: Path, config_path: Path) -> tuple[Path, Path]:
    config = yaml.safe_load(config_path.read_text())
    tasks = config["tasks"]
    for task in tasks:
        if task["status"] not in VALID:
            raise ValueError(f"invalid task status for {task['id']}: {task['status']}")
    total = sum(float(task["weight"]) for task in tasks)
    complete = sum(float(task["weight"]) for task in tasks if task["status"] == "complete")
    progress = 100.0 * complete / total if total else 0.0
    deadline = datetime.fromisoformat(config["deadline_ist"])
    now = datetime.now(timezone.utc)
    remaining_hours = max((deadline.astimezone(timezone.utc) - now).total_seconds(), 0.0) / 3600.0
    bar_width = 24
    filled = round(bar_width * progress / 100.0)
    root = project / "results_hpca_xorflow/complete_suite"
    root.mkdir(parents=True, exist_ok=True)
    csv_path = root / "HPCA_PAPER_PROGRESS.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("id", "block", "weight", "status", "owner", "description", "evidence", "evidence_exists"))
        writer.writeheader()
        for task in tasks:
            evidence = project / task["evidence"]
            writer.writerow({**task, "evidence_exists": evidence.exists()})
    md_path = root / "HPCA_PAPER_PROGRESS.md"
    lines = [
        "# XORFLOW Paper-Suite Live Progress",
        "",
        f"**Progress:** `[{('#' * filled) + ('-' * (bar_width - filled))}] {progress:.1f}%` (weighted, completed evidence only)",
        f"**Hard deadline:** `{config['deadline_ist']}` — **hours remaining:** `{remaining_hours:.2f}`",
        "**Compute policy:** GPU1-only cluster queue; local machine handles validation, PPA, energy, and reports.",
        "**Interpretation:** an existing path is not itself completion; each task is marked complete only after its stated scientific check and artifacts are reviewed.",
        "",
        "| ID | Block | Status | Owner | Weight | Evidence | Description |",
        "|---|---|---|---|---:|---|---|",
    ]
    for task in tasks:
        marker = "present" if (project / task["evidence"]).exists() else "pending"
        lines.append(
            f"| {task['id']} | {task['block']} | {_status_label(task['status'])} | {task['owner']} | {task['weight']}% | `{task['evidence']}` ({marker}) | {task['description']} |"
        )
    lines += ["", f"Machine-readable state: `{csv_path.name}`. Plan: [`plan.md`](../../../plan.md)."]
    md_path.write_text("\n".join(lines) + "\n")
    return md_path, csv_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/hpca_paper_ready_tracking.yaml"))
    args = parser.parse_args()
    project = args.project.resolve()
    config = args.config if args.config.is_absolute() else project / args.config
    md_path, csv_path = render(project, config)
    print(f"PROGRESS={md_path}\nCSV={csv_path}")


if __name__ == "__main__":
    main()
