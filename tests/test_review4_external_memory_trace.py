from __future__ import annotations

import csv, json, subprocess, sys
from pathlib import Path


def test_consumer_reread_is_exact_padded_committed_record(tmp_path: Path) -> None:
    base=tmp_path/'base.trace'; base.write_text('LD 0x20\nST 0x40\n')
    tx=tmp_path/'tx.csv'
    with tx.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=['layer','tile','slice','request_type','address']); w.writeheader()
        w.writerow({'layer':4,'tile':3,'slice':0,'request_type':'SUPPORT_WRITE','address':4096})
    life=tmp_path/'life.csv'
    fields=['run_id','layer_pair','tile_id','slice_id','delta_target','consumer_anchor_read_bytes']
    with life.open('w',newline='') as h:
        w=csv.DictWriter(h,fieldnames=fields); w.writeheader()
        w.writerow({'run_id':'r','layer_pair':2,'tile_id':3,'slice_id':0,'delta_target':True,'consumer_anchor_read_bytes':64})
    out=tmp_path/'combined.trace'; manifest=tmp_path/'manifest.json'
    subprocess.run([sys.executable,'scripts/build_review4_external_memory_trace.py','--base-trace',str(base),'--transactions',str(tx),'--lifecycle',str(life),'--config-id','r','--output-trace',str(out),'--manifest',str(manifest)],check=True)
    assert out.read_text().splitlines()==['LD 0x20','ST 0x40','LD 0x1000','LD 0x1020']
    payload=json.loads(manifest.read_text())
    assert payload['consumer_anchor_bytes']==64 and payload['combined_requests']==4
    assert payload['all_consumer_addresses_resolved']
