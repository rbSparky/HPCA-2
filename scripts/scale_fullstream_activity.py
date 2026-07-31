#!/usr/bin/env python3
"""Sample a complete serialized replay with the routed decoder RTL.

The physical VCD is intentionally bounded: a complete workload VCD is much
larger than the result bundle and is not needed to establish activity scaling.
This tool visits deterministic, uniformly spaced windows over the complete
stream, runs the same ready/valid Verilator testbench, summarizes each VCD,
and deletes the transient VCD immediately.  The output is an auditable
full-stream activity estimate, not a fabricated full-workload power number.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts_hpca_xorflow" / "complete_suite" / "decoder_activity"
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_tb(build: Path) -> Path:
    exe = build / "decoder_cluster_activity_tb"
    if exe.exists():
        return exe
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "verilator", "--cc", "--exe", "--build", "--trace", "--Wno-fatal",
        "--top-module", "xorflow_decoder_cluster8_pipelined", "--Mdir", str(build),
        str(ROOT / "rtl/xorflow_decoder_pipelined.sv"),
        str(ROOT / "rtl/xorflow_decoder_cluster_pipelined.sv"),
        str(ROOT / "rtl/xorflow_decoder_cluster_physical_tb.cpp"),
        "-o", exe.name,
    ], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return exe


def summarize_vcd(path: Path) -> dict[str, int | float]:
    ids: set[str] = set()
    values: dict[str, str] = {}
    changes = transitions = markers = 0
    header = True
    for raw in path.open(errors="replace"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("$var"):
            parts = line.split()
            if len(parts) >= 5:
                ids.add(parts[3])
            continue
        if line.startswith("#"):
            markers += 1
            continue
        if line.startswith("$enddefinitions"):
            header = False
            continue
        if header:
            continue
        if line[0] in "01xXzZ" and len(line) > 1:
            ident, value = line[1:], line[0]
        elif line[0] in "bBrR" and " " in line:
            value, ident = line[1:].split(None, 1)
        else:
            continue
        if ident not in ids:
            continue
        if ident in values and values[ident] != value:
            transitions += 1
        values[ident] = value
        changes += 1
    return {
        "signals": len(ids),
        "value_changes": changes,
        "transitions": transitions,
        "time_markers": markers,
        "toggle_coverage": 0.0 if not ids else len(values) / len(ids),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stream", type=Path, default=V3 / "online_replay/streams/ogbn_arxiv_deepres8_w128_s17/reread/support_stream.bin")
    p.add_argument("--windows", type=int, default=32)
    p.add_argument("--window-words", type=int, default=4096)
    p.add_argument("--output", type=Path, default=V3 / "activity/fullstream_activity_scaling.csv")
    args = p.parse_args()
    size_bytes = args.stream.stat().st_size
    total_words = size_bytes // 8
    if total_words <= 0:
        raise SystemExit("empty stream")
    windows = min(args.windows, max(1, (total_words + args.window_words - 1) // args.window_words))
    if windows == 1:
        offsets = [0]
    else:
        offsets = [round(i * max(0, total_words - args.window_words) / (windows - 1)) for i in range(windows)]
    exe = build_tb(ART / "verilator_obj_dir")
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="xorflow-vcd-", dir="/tmp") as td:
        for idx, offset in enumerate(offsets):
            vcd = Path(td) / f"window_{idx:03d}.vcd"
            run = subprocess.run([
                str(exe), "--vcd", str(vcd), "--stream", str(args.stream),
                "--offset-words", str(offset), "--max-words", str(args.window_words),
            ], cwd=ROOT, capture_output=True, text=True, check=True)
            summary = summarize_vcd(vcd)
            rows.append({
                "stream": str(args.stream.relative_to(ROOT)),
                "stream_sha256": sha(args.stream),
                "total_stream_words": total_words,
                "window_index": idx,
                "offset_words": offset,
                "window_words": min(args.window_words, total_words - offset),
                "tb_status": run.stdout.strip(),
                **summary,
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with args.output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    aggregate = {
        "stream": str(args.stream.relative_to(ROOT)),
        "stream_sha256": sha(args.stream),
        "total_stream_words": total_words,
        "windows": len(rows),
        "window_words": args.window_words,
        "mean_transitions_per_window": sum(int(r["transitions"]) for r in rows) / len(rows),
        "mean_value_changes_per_window": sum(int(r["value_changes"]) for r in rows) / len(rows),
        "mean_toggle_coverage": sum(float(r["toggle_coverage"]) for r in rows) / len(rows),
        "activity_scope": "COMPLETE_STREAM_UNIFORM_WINDOW_ACTIVITY_SCALING",
        "power_claim": "NOT_CLAIMED_UNTIL_CELL_POWER_IS_WEIGHTED_BY_FULL_STREAM_ACTIVITY",
        "csv": str(args.output.relative_to(ROOT)),
    }
    summary_path = args.output.with_suffix(".json")
    summary_path.write_text(json.dumps(aggregate, indent=2, sort_keys=True) + "\n")
    print(json.dumps(aggregate, sort_keys=True))


if __name__ == "__main__":
    main()
