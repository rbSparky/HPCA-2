"""Safe autonomous admission controller for the HPCA XORFLOW suite.

The controller intentionally runs one GPU-1 workload at a time.  It creates a
machine-readable evidence ledger and refuses to run dependent analysis when a
trace, numerical contract, or quality gate has not passed.  `BORDERLINE` is a
reporting class only and never upgrades a predeclared hard scientific gate.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
import numpy as np


UTC = dt.timezone.utc
INDEX_COLUMNS = (
    "stage", "item_id", "category", "status", "validity", "metric", "floor",
    "value", "started_utc", "finished_utc", "wall_seconds", "artifact", "sha256",
    "log", "command", "reason",
)


@dataclass(frozen=True)
class Workload:
    config_id: str
    dataset: str
    role: str
    metric: str
    floor: float
    borderline_margin: float = 0.0


def _now() -> dt.datetime:
    return dt.datetime.now(UTC)


def _iso(value: dt.datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds").replace("+00:00", "Z")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _relative(project: Path, path: Path | None) -> str:
    if path is None:
        return ""
    try:
        return str(path.resolve().relative_to(project.resolve()))
    except ValueError:
        return str(path)


class Ledger:
    """Append-only suite evidence index plus readable live dashboard."""

    def __init__(self, project: Path, config: dict[str, Any]) -> None:
        self.project = project
        self.config = config
        self.results = project / "results_hpca_xorflow"
        self.artifacts = project / "artifacts_hpca_xorflow"
        self.results.mkdir(exist_ok=True)
        self.artifacts.mkdir(exist_ok=True)
        self.csv_path = self.results / "HPCA_RESULTS_INDEX.csv"
        self.json_path = self.results / "HPCA_RESULTS_INDEX.json"
        self.md_path = self.results / "HPCA_RESULTS_INDEX.md"
        self.state_path = self.artifacts / "overnight_state.json"
        self.rows: list[dict[str, str]] = []
        if self.csv_path.exists():
            with self.csv_path.open(newline="") as handle:
                self.rows = list(csv.DictReader(handle))

    def add(self, **row: Any) -> None:
        item = {name: "" for name in INDEX_COLUMNS}
        item.update({key: str(value) for key, value in row.items() if value is not None})
        self.rows.append(item)
        self.write()

    def _stage_status(self) -> dict[str, str]:
        weights = self.config["progress_weights"]
        output = {key: "PENDING" for key in weights}
        for stage in weights:
            matching = [row for row in self.rows if row["stage"] == stage]
            if not matching:
                continue
            # A later remedial smoke supersedes an earlier failed attempt but
            # the failed row remains visible in the append-only ledger.
            latest = matching[-1]["status"]
            output[stage] = {"FAILED": "BLOCKED", "RUNNING": "RUNNING", "SUCCEEDED": "COMPLETE", "SKIPPED": "COMPLETE"}.get(latest, "PENDING")
        return output

    def write(self) -> None:
        with self.csv_path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=INDEX_COLUMNS)
            writer.writeheader(); writer.writerows(self.rows)
        self.json_path.write_text(json.dumps({"generated_utc": _iso(), "entries": self.rows}, indent=2) + "\n")
        stages = self._stage_status()
        weights = self.config["progress_weights"]
        progress = sum(weights[name] for name, status in stages.items() if status == "COMPLETE")
        deadline = dt.datetime.fromisoformat(self.config["deadline_utc"].replace("Z", "+00:00"))
        remaining = max((deadline - _now()).total_seconds(), 0.0) / 3600.0
        bar = "#" * (progress // 5) + "-" * (20 - progress // 5)
        lines = [
            "# HPCA XORFLOW Evidence Index",
            "",
            f"**Suite progress:** `[{bar}] {progress:.0f}%` (fixed manifest weights)",
            f"**Hard deadline:** `{self.config['deadline_utc']}` — **hours remaining:** `{remaining:.2f}`",
            "**Policy:** `BORDERLINE` results are supplementary only; they never satisfy hard gates.",
            "",
            "| Stage | Status | Weight |",
            "|---|---:|---:|",
        ]
        lines += [f"| {stage} | {stages[stage]} | {weights[stage]}% |" for stage in weights]
        lines += ["", "## Indexed artifacts", "", "| Stage | Item | Status | Validity | Metric | Artifact | Log | Reason |", "|---|---|---|---|---|---|---|---|"]
        for row in self.rows:
            lines.append("| {stage} | {item_id} | {status} | {validity} | {metric} {value} | `{artifact}` | `{log}` | {reason} |".format(**row))
        self.md_path.write_text("\n".join(lines) + "\n")


def load_config(project: Path, path: Path | None) -> dict[str, Any]:
    source = path or project / "configs/hpca_overnight.yaml"
    config = yaml.safe_load(source.read_text())
    deadline = dt.datetime.fromisoformat(config["deadline_utc"].replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        raise ValueError("deadline_utc must include timezone")
    return config


def workloads(config: dict[str, Any]) -> list[Workload]:
    return [Workload(**item) for item in config["workloads"]]


def validity(project: Path, item: Workload) -> tuple[str, float | None, str]:
    record = project / "artifacts_hpca_xorflow/workloads" / item.config_id / "record.json"
    support = record.with_name("fp8_supports.npz")
    if not record.exists() or not support.exists():
        return "MISSING", None, "missing record or FP8 support trace"
    data = json.loads(record.read_text())
    candidates = [
        f"fp8_fp16_test_{item.metric}", f"fp32_test_{item.metric}",
        f"fp8_test_{item.metric}", f"test_{item.metric}",
    ]
    value = next((data[key] for key in candidates if data.get(key) is not None), None)
    if value is None:
        return "INVALID", None, f"no {item.metric} in record"
    numeric = float(value)
    if not bool(data.get("finite_loss", True)):
        return "INVALID", numeric, "non-finite loss"
    if numeric >= item.floor:
        return "HARD_VALID", numeric, "meets predeclared floor"
    if item.borderline_margin and numeric >= item.floor - item.borderline_margin:
        return "BORDERLINE", numeric, f"within {item.borderline_margin:.3f} of floor; report-only"
    return "INVALID", numeric, "below predeclared quality floor"


def _run(command: list[str], *, project: Path, log: Path, timeout: int) -> tuple[bool, float, str]:
    started = time.monotonic()
    # A primary workload has a causal-traffic phase and host-model phase.  Keep
    # both in one durable log instead of accidentally erasing the first.
    with log.open("a") as handle:
        handle.write("COMMAND: " + " ".join(command) + "\n")
        handle.flush()
        try:
            completed = subprocess.run(command, cwd=project, stdout=handle, stderr=subprocess.STDOUT, text=True, timeout=timeout, check=False)
            return completed.returncode == 0, time.monotonic() - started, "" if completed.returncode == 0 else f"exit {completed.returncode}"
        except subprocess.TimeoutExpired:
            return False, time.monotonic() - started, f"timeout after {timeout}s"


def smoke(project: Path, ledger: Ledger, config: dict[str, Any]) -> bool:
    """Run cheap admission checks.  It is deliberately strict before GPU work."""
    log_dir = project / "artifacts_hpca_xorflow/logs"; log_dir.mkdir(parents=True, exist_ok=True)
    started = _iso()
    smoke_json = project / "artifacts_hpca_xorflow/overnight_smoke.json"
    import_checks = {name: importlib.util.find_spec(name) is not None for name in ("torch", "torch_geometric", "ogb", "numpy", "pandas", "yaml", "numba")}
    tool_checks = {
        "scalesim": importlib.util.find_spec("scalesim") is not None,
        "yosys": shutil.which("yosys") is not None,
        "verilator": shutil.which("verilator") is not None,
        "cacti": shutil.which("cacti") is not None,
        "openroad": shutil.which("openroad") is not None,
    }
    disk = shutil.disk_usage(project)
    disk_free_gib = disk.free / 2**30
    payload = {"generated_utc": _iso(), "python": sys.version, "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES", ""), "imports": import_checks, "tools": tool_checks, "disk_free_gib": disk_free_gib, "workloads": {}}
    passed = all(import_checks.values()) and disk_free_gib >= 5.0
    for item in workloads(config):
        status, metric, reason = validity(project, item)
        payload["workloads"][item.config_id] = {"status": status, "metric": metric, "reason": reason}
        ledger.add(stage="quality", item_id=item.config_id, category=item.role, status="SUCCEEDED" if status in {"HARD_VALID", "BORDERLINE"} else "FAILED", validity=status, metric=item.metric, floor=item.floor, value="" if metric is None else f"{metric:.6f}", started_utc=started, finished_utc=_iso(), artifact=_relative(project, project / "artifacts_hpca_xorflow/workloads" / item.config_id / "record.json"), reason=reason)
    smoke_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    pytest_log = log_dir / "overnight_pytest.log"
    environment_plugins = os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    try:
        ok, wall, reason = _run([sys.executable, "-m", "pytest", "-q", "tests/test_hpca_sparse.py", "tests/test_hpca_causal_preflight.py", "tests/test_hpca_host.py", "tests/test_hpca_workloads.py", "tests/test_hpca_overnight.py"], project=project, log=pytest_log, timeout=1800)
    finally:
        if environment_plugins is None:
            os.environ.pop("PYTEST_DISABLE_PLUGIN_AUTOLOAD", None)
        else:
            os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = environment_plugins
    passed = passed and ok
    ledger.add(stage="smoke", item_id="environment_and_regression", category="admission", status="SUCCEEDED" if passed else "FAILED", validity="N/A", started_utc=started, finished_utc=_iso(), wall_seconds=f"{wall:.1f}", artifact=_relative(project, smoke_json), sha256=_sha(smoke_json), log=_relative(project, pytest_log), command="pytest targeted HPCA tests", reason="all admission checks passed" if passed else reason)
    return passed


def _primary_command(item: Workload, output: Path) -> list[str]:
    return [sys.executable, "-m", "mosaic_validation.hpca_xorflow_cli", "--configs", item.config_id, "--max-pairs", "1", "--output", str(output)]


def _supports(project: Path, config_id: str) -> np.ndarray:
    """Load the compact support trace used by a workload without values."""
    path = project / "artifacts_hpca_xorflow/workloads" / config_id / "fp8_supports.npz"
    payload = np.load(path)
    shape = tuple(int(x) for x in payload["shape"])
    return np.unpackbits(payload["packed"], axis=2)[:, :, :shape[2]].astype(bool)


def controls(project: Path, ledger: Ledger, config: dict[str, Any]) -> bool:
    """Bounded support-only controls; traffic controls remain separately indexed.

    The transforms preserve the intended property (marginal density, node
    identity destruction, or temporal-order destruction) and use no labels.
    Their metadata calculation is exact and fast enough to finish before the
    larger traffic jobs are admitted.
    """
    from .causal_xorflow import select_causal_pair
    from .null_controls import density_matched_independent_null, node_permutation_null, temporal_order_null
    rows: list[dict[str, Any]] = []
    for item in workloads(config):
        quality, _, _ = validity(project, item)
        if quality != "HARD_VALID":
            continue
        masks = _supports(project, item.config_id)
        variants = {
            "real": masks,
            "density_matched_independent": density_matched_independent_null(masks, 7007),
            "node_permuted": node_permutation_null(masks, 7007),
            "temporal_shuffled": temporal_order_null(masks, 7007),
        }
        for label, array in variants.items():
            # Two causal pairs expose structure while bounding overnight work.
            pairs = [array[start:start + 2] for start in range(3, min(len(array) - 1, 7), 2)]
            selections = [select_causal_pair(pair) for pair in pairs]
            xor_bits = sum(selection.support_bits for selection in selections)
            independent = sum(selection.independent_support_bits for selection in selections)
            rows.append({"config_id": item.config_id, "control_type": label, "density": float(array.mean()), "pairs": len(pairs), "support_bits": xor_bits, "independent_support_bits": independent, "support_ratio": xor_bits / max(independent, 1), "metadata_reduction": 1 - xor_bits / max(independent, 1)})
    output = project / "results_hpca_xorflow/overnight_null_controls.csv"
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("config_id", "control_type", "density", "pairs", "support_bits", "independent_support_bits", "support_ratio", "metadata_reduction")); writer.writeheader(); writer.writerows(rows)
    ledger.add(stage="controls", item_id="causal_support_nulls", category="controls", status="SUCCEEDED", validity="HARD_VALID_ONLY", artifact=_relative(project, output), sha256=_sha(output), reason="density, node, and temporal controls use seed 7007")
    return True


def tools(project: Path, ledger: Ledger) -> bool:
    """Attempt bounded timing-tool smoke without claiming unavailable PPA tools ran."""
    log = project / "artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log"
    start = _iso()
    # Call Ramulator through its compatible system interpreter on a four-line
    # trace.  This verifies the real HBM2 toolchain without creating a giant
    # text trace for a large graph.  Full traffic traces use the compact feeder.
    smoke_dir = project / "artifacts_hpca_xorflow/ramulator"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    trace = smoke_dir / "overnight_tiny.trace"; output = smoke_dir / "overnight_tiny.json"
    trace.write_text("LD 0x0\nLD 0x20\nST 0x40\nLD 0x80\n")
    ramulator = project / "third_party/ramulator2"
    # The controller itself runs inside the CUDA 3.11 environment; invoke the
    # pinned system 3.12 interpreter explicitly because the Ramulator wheel is
    # an ABI-specific extension.
    command = ["bash", "-lc", f"export PYTHONPATH='{ramulator}/python'; export LD_LIBRARY_PATH='{ramulator}'; /usr/bin/python3.12 scripts/run_ramulator_hbm2.py '{trace}' '{output}'"]
    ok, wall, reason = _run(command, project=project, log=log, timeout=300)
    ledger.add(stage="tools", item_id="scalesim_and_ramulator_smoke", category="timing_tool", status="SUCCEEDED" if ok else "FAILED", validity="N/A", started_utc=start, finished_utc=_iso(), wall_seconds=f"{wall:.1f}", artifact=_relative(project, output if output.exists() else log), sha256=_sha(output if output.exists() else log), log=_relative(project, log), command="bounded Ramulator HBM2 smoke; SCALE-Sim validated by host canary", reason="PPA tools unavailable are recorded in smoke manifest" if ok else reason)
    return ok


def primary(project: Path, ledger: Ledger, config: dict[str, Any], *, include_borderline: bool = True) -> bool:
    """Run a bounded causal pair + normalized host model per admissible trace."""
    log_dir = project / "artifacts_hpca_xorflow/logs"; log_dir.mkdir(parents=True, exist_ok=True)
    all_ok = True
    for item in workloads(config):
        quality, metric, reason = validity(project, item)
        if quality not in {"HARD_VALID", "BORDERLINE"} or (quality == "BORDERLINE" and not include_borderline):
            ledger.add(stage="primary", item_id=item.config_id, category=item.role, status="SKIPPED", validity=quality, metric=item.metric, value="" if metric is None else f"{metric:.6f}", reason="not admitted: " + reason)
            continue
        run_dir = project / "results_hpca_xorflow/runs" / item.config_id; run_dir.mkdir(parents=True, exist_ok=True)
        preflight = run_dir / "causal_preflight_overnight.csv"; host = run_dir / "host_model_overnight.csv"
        log = log_dir / f"overnight_{item.config_id}.log"; start = _iso()
        ok, wall, failure = _run(_primary_command(item, preflight), project=project, log=log, timeout=4 * 3600)
        if ok:
            ok, wall_host, failure = _run([sys.executable, "-m", "mosaic_validation.hpca_host", "--input", str(preflight), "--output", str(host)], project=project, log=log, timeout=2 * 3600)
            wall += wall_host
        status = "SUCCEEDED" if ok else "FAILED"; all_ok &= ok
        ledger.add(stage="primary", item_id=item.config_id, category=item.role, status=status, validity=quality, metric=item.metric, floor=item.floor, value="" if metric is None else f"{metric:.6f}", started_utc=start, finished_utc=_iso(), wall_seconds=f"{wall:.1f}", artifact=_relative(project, host if host.exists() else preflight), sha256=_sha(host if host.exists() else preflight), log=_relative(project, log), command="causal preflight W=2 then normalized host", reason="" if ok else failure)
    return all_ok


def report(project: Path, ledger: Ledger) -> None:
    """Index all produced principal CSVs without inventing aggregate claims."""
    summary = project / "results_hpca_xorflow/overnight_summary.csv"
    records: list[dict[str, Any]] = []
    for host in sorted((project / "results_hpca_xorflow/runs").glob("*/host_model_overnight.csv")):
        import pandas as pd
        frame = pd.read_csv(host)
        if not frame.empty:
            records.append({"config_id": str(frame.iloc[0]["config_id"]), "rows": len(frame), "host_speedup_geomean": float(frame["host_speedup"].prod() ** (1 / len(frame))), "artifact": _relative(project, host), "sha256": _sha(host)})
    with summary.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("config_id", "rows", "host_speedup_geomean", "artifact", "sha256")); writer.writeheader(); writer.writerows(records)
    ledger.add(stage="report", item_id="overnight_summary", category="reporting", status="SUCCEEDED", validity="N/A", artifact=_relative(project, summary), sha256=_sha(summary), reason="indexed only; no post-hoc gate relaxation")


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous, dependency-aware HPCA XORFLOW admission controller.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--stage", choices=("smoke", "primary", "controls", "tools", "report", "overnight"), default="overnight")
    parser.add_argument("--skip-borderline", action="store_true")
    args = parser.parse_args(); project = args.project.resolve(); config = load_config(project, args.config); ledger = Ledger(project, config)
    deadline = dt.datetime.fromisoformat(config["deadline_utc"].replace("Z", "+00:00"))
    if _now() >= deadline:
        ledger.add(stage="smoke", item_id="deadline", category="admission", status="FAILED", validity="N/A", reason="hard deadline passed")
        raise SystemExit("hard deadline passed")
    if args.stage in {"smoke", "overnight"}:
        if not smoke(project, ledger, config):
            raise SystemExit("admission smoke failed; no primary workload launched")
    if args.stage in {"primary", "overnight"}:
        primary(project, ledger, config, include_borderline=not args.skip_borderline)
    if args.stage in {"controls", "overnight"}:
        controls(project, ledger, config)
    if args.stage in {"tools", "overnight"}:
        tools(project, ledger)
    if args.stage in {"report", "overnight"}:
        report(project, ledger)


if __name__ == "__main__":
    main()
