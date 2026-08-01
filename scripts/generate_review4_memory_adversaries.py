#!/usr/bin/env python3
"""Generate deterministic HBM row-conflict and write-heavy validation traces."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path


def emit(path: Path, count: int, kind: str) -> dict[str, object]:
    h=hashlib.sha256(); reads=writes=0
    with path.open('wb') as out:
        for i in range(count):
            if kind=='row_conflict':
                op='LD'; address=0x40000000 + (i % 2) * 0x20000 + ((i//2)%16)*64
            else:
                op='ST' if i % 5 else 'LD'; address=0x60000000 + (i % 65536)*64
            line=f'{op} 0x{address:x}\n'.encode(); out.write(line); h.update(line)
            reads += op=='LD'; writes += op=='ST'
    return {'kind':kind,'requests':count,'reads':reads,'writes':writes,'trace_sha256':h.hexdigest(),'trace':str(path)}


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--output-dir',type=Path,required=True); p.add_argument('--requests',type=int,default=250000); a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True); rows=[]
    for kind in ('row_conflict','write_heavy'):
        rows.append(emit(a.output_dir/f'{kind}_{a.requests}.trace',a.requests,kind))
    (a.output_dir/'adversarial_manifest.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
    print(json.dumps(rows,sort_keys=True))
if __name__=='__main__': main()
