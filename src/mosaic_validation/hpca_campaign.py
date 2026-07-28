"""Durable serial campaign executor for the HPCA XORFLOW paper suite.

Each campaign task has its own output directory and append-only ledger row.
The executor deliberately continues independent work after a task failure,
while dependency failures are visible as ``SKIPPED`` rather than hidden.
It is intended to be submitted as one GPU-1 job, so filesystem-visible task
dependencies cannot race a separate queued process.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml


UTC = dt.timezone.utc
FIELDS = ("task_id", "stage", "status", "depends_on", "estimated_minutes",
          "started_utc", "finished_utc", "wall_seconds", "log", "command", "reason")


def _iso() -> str:
    return dt.datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _deadline_hours(config: dict[str, Any]) -> float:
    deadline = dt.datetime.fromisoformat(str(config["deadline_utc"]).replace("Z", "+00:00"))
    return max((deadline - dt.datetime.now(UTC)).total_seconds() / 3600.0, 0.0)


def _write_dashboard(root: Path, config: dict[str, Any], rows: list[dict[str, str]]) -> None:
    csv_path = root / "campaign_ledger.csv"
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)
    (root / "campaign_ledger.json").write_text(json.dumps({"generated_utc": _iso(), "rows": rows}, indent=2) + "\n")
    latest = {str(row["task_id"]): row for row in rows}
    tasks = config["tasks"]
    complete = sum(float(task["weight"]) for task in tasks if latest.get(str(task["task_id"]), {}).get("status") == "SUCCEEDED")
    total = sum(float(task["weight"]) for task in tasks)
    percent = 100.0 * complete / max(total, 1.0)
    pending = [task for task in tasks if latest.get(str(task["task_id"]), {}).get("status") not in {"SUCCEEDED", "SKIPPED"}]
    remaining = sum(float(task["estimated_minutes"]) for task in pending)
    bar = "#" * int(percent // 5) + "-" * (20 - int(percent // 5))
    lines = [
        "# HPCA XORFLOW Complete Campaign",
        "",
        f"**Progress:** `[{bar}] {percent:.1f}%` (predeclared task weights)",
        f"**Deadline:** `{config['deadline_utc']}` — **hours remaining:** `{_deadline_hours(config):.2f}`",
        f"**Remaining serialized estimate:** `{remaining:.1f} minutes` on GPU1.",
        "",
        "| Task | Stage | Status | Estimate (min) | Log | Reason |",
        "|---|---|---|---:|---|---|",
    ]
    for task in tasks:
        row = latest.get(str(task["task_id"]), {})
        lines.append(
            f"| {task['task_id']} | {task['stage']} | {row.get('status', 'QUEUED')} | "
            f"{task['estimated_minutes']} | `{row.get('log', '')}` | {row.get('reason', '')} |"
        )
    (root / "CAMPAIGN.md").write_text("\n".join(lines) + "\n")


def run(project: Path, config: dict[str, Any], *, resume: bool) -> int:
    campaign = str(config["campaign_id"])
    root = project / "results_hpca_xorflow" / "complete_suite" / campaign
    logs = project / "artifacts_hpca_xorflow" / "complete_suite" / campaign
    root.mkdir(parents=True, exist_ok=True); logs.mkdir(parents=True, exist_ok=True)
    (root / "campaign_config.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
    csv_path = root / "campaign_ledger.csv"
    rows: list[dict[str, str]] = []
    if resume and csv_path.exists():
        with csv_path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    latest = {str(row["task_id"]): row for row in rows}
    statuses: dict[str, str] = {task: row["status"] for task, row in latest.items()}
    for task in config["tasks"]:
        task_id = str(task["task_id"])
        if resume and statuses.get(task_id) == "SUCCEEDED":
            continue
        dependencies = [str(value) for value in task.get("depends_on", [])]
        if any(statuses.get(value) != "SUCCEEDED" for value in dependencies):
            row = {"task_id": task_id, "stage": str(task["stage"]), "status": "SKIPPED", "depends_on": ",".join(dependencies), "estimated_minutes": str(task["estimated_minutes"]), "started_utc": _iso(), "finished_utc": _iso(), "wall_seconds": "0", "log": "", "command": str(task["command"]), "reason": "dependency did not succeed"}
            rows.append(row); statuses[task_id] = "SKIPPED"; _write_dashboard(root, config, rows); continue
        margin_minutes = float(config.get("deadline_margin_minutes", 30))
        if _deadline_hours(config) * 60 < float(task["estimated_minutes"]) + margin_minutes:
            row = {"task_id": task_id, "stage": str(task["stage"]), "status": "SKIPPED", "depends_on": ",".join(dependencies), "estimated_minutes": str(task["estimated_minutes"]), "started_utc": _iso(), "finished_utc": _iso(), "wall_seconds": "0", "log": "", "command": str(task["command"]), "reason": "deadline guard"}
            rows.append(row); statuses[task_id] = "SKIPPED"; _write_dashboard(root, config, rows); continue
        log = logs / f"{task_id}.log"; started = _iso(); timer = time.monotonic()
        try:
            with log.open("a") as handle:
                handle.write(f"START {started}\nCOMMAND: {task['command']}\n")
                handle.flush()
                completed = subprocess.run(["bash", "-lc", str(task["command"])], cwd=project, stdout=handle, stderr=subprocess.STDOUT, text=True, check=False, timeout=int(float(task["estimated_minutes"]) * 180))
            status = "SUCCEEDED" if completed.returncode == 0 else "FAILED"
            reason = "" if status == "SUCCEEDED" else f"exit {completed.returncode}"
        except subprocess.TimeoutExpired:
            status = "FAILED"; reason = f"timeout after {int(float(task['estimated_minutes']) * 180)}s"
        row = {"task_id": task_id, "stage": str(task["stage"]), "status": status, "depends_on": ",".join(dependencies), "estimated_minutes": str(task["estimated_minutes"]), "started_utc": started, "finished_utc": _iso(), "wall_seconds": f"{time.monotonic() - timer:.1f}", "log": str(log.relative_to(project)), "command": str(task["command"]), "reason": reason}
        rows.append(row); statuses[task_id] = status; _write_dashboard(root, config, rows)
    _write_dashboard(root, config, rows)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the durable GPU-1 HPCA experiment campaign.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/hpca_complete_campaign.yaml"))
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args(); project = args.project.resolve()
    path = args.config if args.config.is_absolute() else project / args.config
    raise SystemExit(run(project, yaml.safe_load(path.read_text()), resume=not args.no_resume))


if __name__ == "__main__":
    main()
