from __future__ import annotations

import csv, json, subprocess, sys
from pathlib import Path


def test_exact_hbm_transaction_splitting(tmp_path: Path) -> None:
    source=tmp_path/"tx.csv"
    columns=["request_type","address","size_bytes"]
    with source.open("w",newline="") as h:
        w=csv.DictWriter(h,fieldnames=columns); w.writeheader(); w.writerows([
            {"request_type":"SUPPORT_READ","address":4096,"size_bytes":64},
            {"request_type":"OUTPUT_WRITEBACK","address":8192,"size_bytes":96},])
    trace=tmp_path/"trace"; manifest=tmp_path/"manifest.json"
    subprocess.run([sys.executable,"scripts/emit_online_hbm_trace.py","--transactions",str(source),"--trace",str(trace),"--manifest",str(manifest)],check=True)
    assert trace.read_text().splitlines()==["LD 0x1000","LD 0x1020","ST 0x2000","ST 0x2020","ST 0x2040"]
    payload=json.loads(manifest.read_text()); assert payload["submitted_requests"]==5
    assert payload["transaction_bytes"]==160
