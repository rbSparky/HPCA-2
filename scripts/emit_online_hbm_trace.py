#!/usr/bin/env python3
"""Convert exact online replay transfers to 32-byte HBM LD/ST requests."""
from __future__ import annotations

import argparse, csv, hashlib, json
from pathlib import Path


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--transactions",type=Path,required=True)
    p.add_argument("--trace",type=Path,required=True); p.add_argument("--manifest",type=Path,required=True)
    p.add_argument("--max-requests",type=int,default=0); p.add_argument("--layers",type=int,nargs="*")
    a=p.parse_args(); a.trace.parent.mkdir(parents=True,exist_ok=True); h=hashlib.sha256(); requests=reads=writes=bytes_total=0
    with a.transactions.open() as source, a.trace.open("wb", buffering=1024*1024) as target:
        for row in csv.DictReader(source):
            if a.layers and int(row["layer"]) not in set(a.layers): continue
            kind = "ST" if ("WRITE" in row["request_type"] or row["request_type"] == "OUTPUT_ALLOC_INIT") else "LD"
            address=int(row["address"]); size=int(row["size_bytes"]); bytes_total += size
            for offset in range(0,size,32):
                if a.max_requests and requests >= a.max_requests: break
                line=f"{kind} 0x{address+offset:x}\n".encode(); target.write(line); h.update(line); requests += 1
                if kind=="LD": reads += 1
                else: writes += 1
            if a.max_requests and requests >= a.max_requests: break
    payload={"source":str(a.transactions),"trace":str(a.trace),"transaction_bytes":bytes_total,
        "hbm_request_bytes":32,"submitted_requests":requests,"read_requests":reads,"write_requests":writes,
        "trace_sha256":h.hexdigest(),"max_requests":a.max_requests,"layers":a.layers or []}
    a.manifest.parent.mkdir(parents=True,exist_ok=True); a.manifest.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")
    print(json.dumps(payload,sort_keys=True))

if __name__=="__main__": main()
