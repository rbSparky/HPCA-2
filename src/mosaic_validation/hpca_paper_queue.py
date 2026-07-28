"""Execute the cached-trace paper-evidence queue with durable per-task outputs."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from .hpca_overnight import Ledger, _iso, _relative, _run, load_config


def _remaining_hours(config: dict[str, Any]) -> float:
    deadline = dt.datetime.fromisoformat(config["deadline_utc"].replace("Z", "+00:00"))
    return (deadline - dt.datetime.now(dt.timezone.utc)).total_seconds() / 3600.0


def _done(ledger: Ledger, task: dict[str, Any]) -> bool:
    return any(row["item_id"] == str(task["queue_id"]) and row["status"] == "SUCCEEDED" for row in ledger.rows)


def _run_task(project: Path, ledger: Ledger, task: dict[str, Any], tasks: dict[str, dict[str, Any]]) -> bool:
    task_id = str(task["queue_id"]); stage = str(task["stage"])
    if task.get("already_complete"):
        return True
    if task.get("status") == "PENDING_IMPLEMENTATION":
        return True
    if _done(ledger, task):
        return True
    dependency = str(task.get("depends_on", "none"))
    if dependency != "none":
        prerequisite = tasks.get(dependency)
        dependency_ok = prerequisite is not None and (bool(prerequisite.get("already_complete")) or _done(ledger, prerequisite))
        if not dependency_ok:
            ledger.add(stage=stage, item_id=task_id, category="dependency_guard", status="SKIPPED", reason=f"dependency {dependency} is not complete")
            return False
    estimate = float(task["estimated_minutes"])
    # Protect the hard deadline: never begin a task without its estimate plus
    # a 15-minute reporting margin.  It remains visibly queued in the index.
    if _remaining_hours(ledger.config) * 60.0 < estimate + 15.0:
        ledger.add(stage=stage, item_id=task_id, category="deadline_guard", status="SKIPPED", reason="insufficient remaining deadline budget")
        return False
    run_dir = project / "results_hpca_xorflow/paper_runs" / task_id
    log = project / "artifacts_hpca_xorflow/logs" / f"paper_{task_id}.log"
    run_dir.mkdir(parents=True, exist_ok=True); log.parent.mkdir(parents=True, exist_ok=True)
    preflight = run_dir / "causal_preflight.csv"; host = run_dir / "host_model.csv"
    command = [sys.executable, "-m", "mosaic_validation.hpca_xorflow_cli", "--configs", str(task["config_id"]), "--max-pairs", str(task["max_pairs"]), "--slice-width", str(task["slice_width"]), "--feature-cache-bytes", str(task["cache_bytes"]), "--edge-order", str(task["edge_order"]), "--output", str(preflight)]
    start = _iso()
    ledger.add(stage=stage, item_id=task_id, category=str(task.get("priority", "paper")), status="RUNNING", started_utc=start, artifact=_relative(project, preflight), log=_relative(project, log), command="causal cache simulation plus normalized host model", reason="admitted after dependency and deadline checks")
    ok, wall, reason = _run(command, project=project, log=log, timeout=max(4 * 3600, int(estimate * 180)))
    if ok:
        host_command = [sys.executable, "-m", "mosaic_validation.hpca_host", "--input", str(preflight), "--output", str(host)]
        ok, host_wall, reason = _run(host_command, project=project, log=log, timeout=2 * 3600); wall += host_wall
    ledger.add(stage=stage, item_id=task_id, category=str(task.get("priority", "paper")), status="SUCCEEDED" if ok else "FAILED", started_utc=start, finished_utc=_iso(), wall_seconds=f"{wall:.1f}", artifact=_relative(project, host if host.exists() else preflight), log=_relative(project, log), command="causal cache simulation plus normalized host model", reason=reason)
    return ok


def run(project: Path, config: dict[str, Any], *, only: set[str] | None = None) -> None:
    ledger = Ledger(project, config)
    tasks = {str(item["queue_id"]): item for item in config["queue"]}
    for task in config["queue"]:
        task_id = str(task["queue_id"])
        if only and task_id not in only:
            continue
        _run_task(project, ledger, task, tasks)
    manifest = project / "results_hpca_xorflow/paper_queue_manifest.json"
    manifest.write_text(json.dumps({"generated_utc": _iso(), "deadline_hours_remaining": _remaining_hours(config), "queue": config["queue"]}, indent=2) + "\n")
    ledger.add(stage="report", item_id="paper_queue_manifest", category="paper_queue", status="SUCCEEDED", artifact=_relative(project, manifest), reason="queue snapshot written; pending implementation tasks remain visible")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/hpca_paper_queue.yaml"))
    parser.add_argument("--only", nargs="*")
    args = parser.parse_args(); project = args.project.resolve()
    config_path = args.config if args.config.is_absolute() else project / args.config
    run(project, load_config(project, config_path), only=set(args.only) if args.only else None)


if __name__ == "__main__":
    main()
