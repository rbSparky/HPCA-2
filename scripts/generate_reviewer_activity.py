#!/usr/bin/env python3
"""Generate and summarize VCD activity from emitted serialized streams.

The traces are driven through the same Verilator testbenches used by the
correctness checks.  This is deliberately a toggle/activity artifact, not a
power claim: mapping to cell power requires a characterized library and a
real workload-level clock/activity annotation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"
ART = ROOT / "artifacts_hpca_xorflow" / "complete_suite"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def summarize_vcd(path: Path) -> dict[str, object]:
    """Count scalar/vector value changes without depending on a VCD package."""
    ids: dict[str, str] = {}
    values: dict[str, str] = {}
    transitions = 0
    value_changes = 0
    times = 0
    header = True
    for raw in path.open(errors="replace"):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("$var"):
            parts = line.split()
            if len(parts) >= 5:
                ids[parts[3]] = parts[4]
            continue
        if line.startswith("#"):
            times += 1
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
        old = values.get(ident)
        if old is not None and old != value:
            transitions += 1
        values[ident] = value
        value_changes += 1
    return {
        "vcd": str(path.relative_to(ROOT)),
        "vcd_sha256": sha(path),
        "signals": len(ids),
        "value_changes": value_changes,
        "transitions": transitions,
        "time_markers": times,
        "toggle_coverage": 0.0 if not ids else len(values) / len(ids),
        "activity_status": "VCD_ACTIVITY_CAPTURED",
        "power_status": "NOT_CLAIMED_NO_CELL_ANNOTATION",
    }


def build_decoder(out: Path, stream: Path) -> None:
    build = ART / "decoder_cluster_rtl" / "vcd_obj_dir"
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "verilator", "--cc", "--exe", "--build", "--trace", "--Wno-fatal",
        "--top-module", "xorflow_decoder_cluster8_pipelined", "--Mdir", str(build),
        str(ROOT / "rtl/xorflow_decoder_pipelined.sv"),
        str(ROOT / "rtl/xorflow_decoder_cluster_pipelined.sv"),
        str(ROOT / "rtl/xorflow_decoder_cluster_physical_tb.cpp"), "-o", "decoder_cluster_vcd_tb",
    ], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(build / "decoder_cluster_vcd_tb"), "--vcd", str(out), "--stream", str(stream)],
                   cwd=ROOT, check=True, text=True, capture_output=True)


def build_encoder(out: Path) -> None:
    build = ART / "encoder_rtl" / "vcd_obj_dir"
    build.mkdir(parents=True, exist_ok=True)
    subprocess.run([
        "verilator", "--cc", "--exe", "--build", "--trace", "--Wno-fatal",
        "--top-module", "xorflow_encoder_stream_engine", "--Mdir", str(build),
        str(ROOT / "rtl/xorflow_encoder_pipelined.sv"),
        str(ROOT / "rtl/xorflow_encoder_stream_tb.cpp"), "-o", "encoder_engine_vcd_tb",
    ], cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(build / "encoder_engine_vcd_tb"), "--vcd", str(out)],
                   cwd=ROOT, check=True, text=True, capture_output=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stream",
        type=Path,
        default=V3 / "online_replay/streams/ogbn_arxiv_deepres8_w128_s17/reread/support_stream.bin",
    )
    parser.add_argument("--encoder-vcd", type=Path, default=V3 / "encoder/vcd_or_saif/encoder_engine_realstream.vcd")
    parser.add_argument("--decoder-vcd", type=Path, default=V3 / "decoder/vcd_or_saif/decoder_cluster_realstream.vcd")
    parser.add_argument("--summary", type=Path, default=V3 / "activity/vcd_summary.csv")
    args = parser.parse_args()
    build_encoder(args.encoder_vcd)
    build_decoder(args.decoder_vcd, args.stream)
    data = [summarize_vcd(args.encoder_vcd), summarize_vcd(args.decoder_vcd)]
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in data for key in row})
    with args.summary.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(data)
    for row in data:
        print(row)


if __name__ == "__main__":
    main()
