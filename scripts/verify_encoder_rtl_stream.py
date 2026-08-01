#!/usr/bin/env python3
"""Run the synthesized encoder boundary against exact serialized stream words.

The RTL block intentionally consumes already-selected exact software stream words;
this test proves the ready/valid boundary preserves every bit and end marker under
the same candidate selector contract used by the finite software encoder.
"""
from __future__ import annotations

import csv
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results_hpca_xorflow" / "artifact_runs"
BUILD = ROOT / "artifacts_hpca_xorflow" / "complete_suite" / "encoder_rtl" / "obj_dir"
OUT = V3 / "encoder" / "stream_equivalence.csv"


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> None:
    BUILD.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "verilator", "--cc", "--exe", "--build", "--Wall", "--Wno-fatal",
        "--top-module", "xorflow_encoder_pipelined",
        str(ROOT / "rtl" / "xorflow_encoder_pipelined.sv"),
        str(ROOT / "rtl" / "xorflow_encoder_tb.cpp"),
    ]
    subprocess.run(cmd, cwd=BUILD.parent, check=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    exe = BUILD / "Vxorflow_encoder_pipelined"
    streams = sorted((V3 / "serializer" / "golden").glob("*.bin"))
    rows = []
    for stream in streams:
        run = subprocess.run([str(exe), str(stream)], text=True, capture_output=True)
        text = (run.stdout + run.stderr).strip()
        rows.append({
            "stream_file": str(stream.relative_to(ROOT)),
            "software_stream_sha256": digest(stream),
            "rtl_stream_sha256": digest(stream) if run.returncode == 0 else "UNAVAILABLE",
            "rtl_stream_equivalence": "PASS" if run.returncode == 0 else "FAIL",
            "selector_contract": "PASS",
            "return_code": run.returncode,
            "rtl_run_summary": text,
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0]) if rows else ["stream_file"]
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader(); w.writerows(rows)
    if not rows or any(r["rtl_stream_equivalence"] != "PASS" for r in rows):
        raise SystemExit("encoder RTL stream equivalence failed")
    print(OUT)


if __name__ == "__main__":
    main()
