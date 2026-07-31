#!/usr/bin/env python3
"""Annotate several full-stream activity windows on the routed decoder.

The routed database and OpenROAD power flow are unchanged.  Only the VCD
window is replaced between runs, so each result is a real cell-level
annotation of the same serialized stream at a deterministic offset.  The
output is an activity/power scaling table; it is not an end-to-end energy
measurement.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"
ART = ROOT / "artifacts_hpca_xorflow" / "complete_suite" / "decoder_activity"
FLOW = Path.home() / "src" / "OpenROAD-flow-scripts" / "flow"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def build_tb() -> Path:
    build = ART / "verilator_obj_dir"
    exe = build / "decoder_cluster_activity_tb"
    subprocess.run([
        "verilator", "--cc", "--exe", "--build", "--trace", "--Wno-fatal",
        "--top-module", "xorflow_decoder_cluster8_pipelined", "--Mdir", str(build),
        str(ROOT / "rtl/xorflow_decoder_pipelined.sv"),
        str(ROOT / "rtl/xorflow_decoder_cluster_pipelined.sv"),
        str(ROOT / "rtl/xorflow_decoder_cluster_physical_tb.cpp"),
        "-o", exe.name,
    ], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return exe


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--stream", type=Path, default=V3 / "online_replay/streams/ogbn_arxiv_deepres8_w128_s17/reread/support_stream.bin")
    p.add_argument("--window-words", type=int, default=4096)
    p.add_argument("--output", type=Path, default=V3 / "activity/fullstream_power_scaling.csv")
    args = p.parse_args()
    total_words = args.stream.stat().st_size // 8
    max_start = max(0, total_words - args.window_words)
    offsets = sorted({round(max_start * q / 4) for q in range(5)})
    exe = build_tb()
    tcl = ROOT / "scripts" / "openroad_vcd_power.tcl"
    if not FLOW.is_dir():
        raise SystemExit(f"OpenROAD flow directory unavailable: {FLOW}")
    rows: list[dict[str, object]] = []
    with tempfile.TemporaryDirectory(prefix="xorflow-power-") as td:
        for idx, offset in enumerate(offsets):
            vcd = Path(td) / f"window_{idx:02d}.vcd"
            run = subprocess.run([
                str(exe), "--vcd", str(vcd), "--stream", str(args.stream),
                "--offset-words", str(offset), "--max-words", str(args.window_words),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            shutil.copy2(ROOT / "scripts" / "openroad_vcd_power.tcl", FLOW / "xorflow_vcd_power_tmp.tcl")
            shutil.copy2(vcd, FLOW / "xorflow_decoder_realstream_tmp.vcd")
            result = subprocess.run([
                str(FLOW / "util/docker_shell"), "openroad", "-no_init", "-exit", "/work/xorflow_vcd_power_tmp.tcl",
            ], cwd=FLOW, capture_output=True, text=True, check=False)
            text = result.stdout + "\n" + result.stderr
            annotated = re.findall(r"Annotated (\d+) pin activities", text)
            totals = re.findall(r"Total\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+100\.0%", text)
            total = totals[-1] if totals else ("", "", "", "")
            rows.append({
                "stream": str(args.stream.relative_to(ROOT)),
                "stream_sha256": sha(args.stream),
                "total_stream_words": total_words,
                "window_index": idx,
                "offset_words": offset,
                "window_words": min(args.window_words, total_words - offset),
                "annotated_pins": int(annotated[-1]) if annotated else 0,
                "internal_power_w": total[0],
                "switching_power_w": total[1],
                "leakage_power_w": total[2],
                "total_power_w": total[3],
                "tool_run_success": bool(result.returncode == 0 and annotated and totals),
                "error": "" if result.returncode == 0 else text[-1000:],
                "tb_status": run.stdout.strip(),
            })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0])
    with args.output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(f"windows={len(rows)} successful={sum(bool(r['tool_run_success']) for r in rows)} output={args.output}")


if __name__ == "__main__":
    main()
