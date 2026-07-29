#!/usr/bin/env python3
"""Run and consolidate the reproducible XORFLOW local PPA evidence.

This is deliberately a *subsystem* PPA flow.  CACTI models the SRAM macros;
OpenROAD places/routes one timing-closed decoder lane in Nangate45; Yosys
synthesizes both the lane and the 32-lane hierarchical bank.  SRAMs are not
silently folded into logic area.  The script therefore reports placed lane
area, a clearly labelled linear 32-lane estimate, and leaves host-percentage
claims unassessed until a defensible common-host floorplan exists.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


UTC = dt.timezone.utc


def _field(pattern: str, text: str) -> float | None:
    match = re.search(pattern, text, flags=re.MULTILINE | re.IGNORECASE)
    return float(match.group(1)) if match else None


def _write_cache_cfg(path: Path, capacity: int) -> None:
    """Write a legal 45-nm SRAM config from CACTI's verified full template.

    CACTI accepts a configuration while returning zero for some malformed
    inputs.  Starting from its upstream ``cache.cfg`` retains all mandatory
    temperature, cell-type, and optimization fields rather than relying on a
    brittle hand-written subset.
    """
    template = Path.home() / "src/cacti-hp7/cache.cfg"
    if not template.exists():
        raise FileNotFoundError(f"verified CACTI source template missing: {template}")
    text = template.read_text()
    replacements = {
        r"(?m)^-size \(bytes\).*$": f"-size (bytes) {capacity}",
        r"(?m)^-block size \(bytes\).*$": "-block size (bytes) 64",
        r"(?m)^-associativity.*$": "-associativity 1",
        r"(?m)^-technology \(u\).*$": "-technology (u) 0.045",
        r"(?m)^-output/input bus width.*$": "-output/input bus width 64",
        r"(?m)^-cache type.*$": '-cache type "ram"',
    }
    for pattern, replacement in replacements.items():
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"could not update required CACTI field: {pattern}")
    path.write_text(text)


def _run(command: list[str], *, cwd: Path, log: Path, timeout: int) -> tuple[bool, str]:
    try:
        complete = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=timeout, check=False)
        log.write_text(complete.stdout)
        return complete.returncode == 0, "" if complete.returncode == 0 else f"exit {complete.returncode}"
    except subprocess.TimeoutExpired as exc:
        log.write_text((exc.stdout or "") if isinstance(exc.stdout, str) else "")
        return False, f"timeout after {timeout}s"
    except OSError as exc:
        log.write_text(str(exc) + "\n")
        return False, f"tool launch error: {exc}"


def _copy_if_exists(source: Path, destination: Path) -> None:
    if source.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect reproducible CACTI/Yosys/OpenROAD XORFLOW PPA.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--run-tag", default=dt.datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    parser.add_argument("--rerun-openroad", action="store_true", help="run ORFS rather than importing its verified result")
    args = parser.parse_args(); project = args.project.resolve()
    results = project / "results_hpca_xorflow/complete_suite/ppa" / args.run_tag
    artifacts = project / "artifacts_hpca_xorflow/complete_suite/ppa" / args.run_tag
    results.mkdir(parents=True, exist_ok=True); artifacts.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    cacti = project / "scripts/cacti7_docker.sh"
    for bytes_ in (8 * 1024, 16 * 1024, 32 * 1024, 64 * 1024):
        cfg = artifacts / "cacti" / f"support_cache_{bytes_}.cfg"; cfg.parent.mkdir(parents=True, exist_ok=True)
        _write_cache_cfg(cfg, bytes_)
        log = artifacts / "cacti" / f"support_cache_{bytes_}.log"
        ok, error = _run([str(cacti), "-infile", str(cfg)], cwd=project, log=log, timeout=300)
        text = log.read_text(errors="replace")
        rows.append({
            "component": "support_cache_sram", "instance_count": 1, "capacity_bytes": bytes_,
            "tool": "CACTI7_DOCKER", "technology_um": 0.045, "status": "PASS" if ok else "TOOL_FAILURE",
            "access_time_ns": _field(r"Access time \(ns\):\s*([0-9.eE+-]+)", text),
            "cycle_time_ns": _field(r"Cycle time \(ns\):\s*([0-9.eE+-]+)", text),
            "area_mm2": sum(value for value in (
                _field(r"Data array: Area \(mm2\):\s*([0-9.eE+-]+)", text),
                _field(r"Tag array: Area \(mm2\):\s*([0-9.eE+-]+)", text),
            ) if value is not None) or None,
            "dynamic_read_nj": _field(r"Total dynamic read energy per access \(nJ\):\s*([0-9.eE+-]+)", text),
            "leakage_mw": _field(r"Total leakage power of a bank \(mW\):\s*([0-9.eE+-]+)", text),
            "provenance": str(log.relative_to(project)), "error": error,
        })

    synth = project / "scripts/synth_pipelined_decoder.sh"
    synth_log = artifacts / "rtl" / "yosys_synthesis.log"; synth_log.parent.mkdir(parents=True, exist_ok=True)
    synth_ok, synth_error = _run([str(synth)], cwd=project, log=synth_log, timeout=300)
    for top in ("xorflow_decoder_lane_pipelined", "xorflow_decoder_bank_pipelined"):
        source = project / "artifacts_safezone/decoder" / f"{top}_synthesis.log"
        destination = artifacts / "rtl" / source.name; _copy_if_exists(source, destination)
        text = destination.read_text(errors="replace") if destination.exists() else ""
        cells = _field(r"Number of cells:\s*([0-9]+)", text)
        rows.append({
            "component": top, "instance_count": 1, "capacity_bytes": 0, "tool": "YOSYS",
            "technology_um": 0.045, "status": "PASS" if synth_ok and destination.exists() else "TOOL_FAILURE",
            "access_time_ns": None, "cycle_time_ns": None, "area_mm2": None,
            "dynamic_read_nj": None, "leakage_mw": None, "cell_count": cells,
            "provenance": str(destination.relative_to(project)), "error": synth_error,
        })

    orfs = Path.home() / "src/OpenROAD-flow-scripts/flow"
    route_log = artifacts / "openroad" / "run.log"; route_log.parent.mkdir(parents=True, exist_ok=True)
    if args.rerun_openroad:
        command = [str(project / "scripts/run_openroad_xorflow_pipelined.sh")]
        openroad_ok, openroad_error = _run(command, cwd=project, log=route_log, timeout=1800)
    else:
        openroad_ok = (project / "artifacts_safezone/openroad/xorflow_decoder_pipelined/6_finish.rpt").exists()
        openroad_error = "imported verified ORFS result; use --rerun-openroad for a fresh route"
        route_log.write_text(openroad_error + "\n")
    source_dir = project / "artifacts_safezone/openroad/xorflow_decoder_pipelined"
    for filename in ("6_finish.rpt", "6_report.log", "5_route_drc.rpt", "6_final.gds", "6_final.def"):
        _copy_if_exists(source_dir / filename, artifacts / "openroad" / filename)
    finish = (artifacts / "openroad/6_finish.rpt").read_text(errors="replace") if (artifacts / "openroad/6_finish.rpt").exists() else ""
    report = (artifacts / "openroad/6_report.log").read_text(errors="replace") if (artifacts / "openroad/6_report.log").exists() else ""
    area_um2 = _field(r"Design area\s+([0-9.eE+-]+)\s+um\^2", finish + "\n" + report)
    worst_slack = _field(r"worst slack max\s+([0-9.eE+-]+)", finish)
    fmax_mhz = _field(r"fmax\s*=\s*([0-9.eE+-]+)", finish)
    power_w = _field(r"Total power\s*:\s*([0-9.eE+-]+)\s*W", report)
    drc_text = (artifacts / "openroad/5_route_drc.rpt").read_text(errors="replace") if (artifacts / "openroad/5_route_drc.rpt").exists() else ""
    drc_count = len(re.findall(r"^\s*violation", drc_text, flags=re.IGNORECASE | re.MULTILINE))
    rows.extend((
        {"component": "decoder_lane_placed", "instance_count": 1, "capacity_bytes": 0, "tool": "OPENROAD_ORFS_NANGATE45", "technology_um": 0.045, "status": "PASS" if openroad_ok and area_um2 is not None else "TOOL_FAILURE", "access_time_ns": None, "cycle_time_ns": 1.0, "area_mm2": area_um2 / 1e6 if area_um2 is not None else None, "dynamic_read_nj": None, "leakage_mw": None, "worst_slack_ns": worst_slack, "fmax_mhz": fmax_mhz, "power_w": power_w, "drc_count": drc_count, "provenance": str((artifacts / "openroad/6_finish.rpt").relative_to(project)), "error": openroad_error},
        {"component": "decoder_32lane_linear_estimate", "instance_count": 32, "capacity_bytes": 0, "tool": "OPENROAD_ORFS_NANGATE45", "technology_um": 0.045, "status": "ESTIMATE_FROM_PLACED_LANE" if area_um2 is not None else "UNASSESSED", "access_time_ns": None, "cycle_time_ns": 1.0, "area_mm2": (32 * area_um2 / 1e6) if area_um2 is not None else None, "dynamic_read_nj": None, "leakage_mw": None, "worst_slack_ns": worst_slack, "fmax_mhz": fmax_mhz, "power_w": (32 * power_w) if power_w is not None else None, "drc_count": drc_count, "provenance": "linear extrapolation from decoder_lane_placed; bank integration is synthesized separately", "error": "not a routed bank-level macro"},
    ))
    fieldnames = sorted({key for row in rows for key in row})
    with (results / "ppa_summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames); writer.writeheader(); writer.writerows(rows)
    payload = {"generated_utc": dt.datetime.now(UTC).isoformat(), "run_tag": args.run_tag,
               "openroad_flow": str(orfs), "openroad_imported": not args.rerun_openroad,
               "rows": len(rows), "summary_sha256": hashlib.sha256((results / "ppa_summary.csv").read_bytes()).hexdigest()}
    (results / "ppa_manifest.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    lines = ["# XORFLOW subsystem PPA", "", "This table reports absolute subsystem PPA only. SRAMs are CACTI macros; the routed result is one decoder lane. The 32-lane line is a labelled linear estimate, not a bank-level routed macro. Host-area and host-power percentage gates remain **UNASSESSED**.", "", "| Component | Status | Area (mm²) | Access/cycle (ns) | Fmax (MHz) | Provenance |", "|---|---|---:|---:|---:|---|"]
    for row in rows:
        lines.append(f"| {row['component']} | {row['status']} | {row.get('area_mm2') or ''} | {row.get('access_time_ns') or row.get('cycle_time_ns') or ''} | {row.get('fmax_mhz') or ''} | `{row['provenance']}` |")
    (results / "PPA_RESULTS.md").write_text("\n".join(lines) + "\n")
    print(results)


if __name__ == "__main__":
    main()
