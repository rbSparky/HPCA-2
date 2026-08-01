#!/usr/bin/env python3
"""Small CUDA-event benchmark for XORFLOW support decode primitives.

The benchmark is deliberately independent of model training: it measures the
bitwise anchor/XOR, popcount and packed-value gather kernels on representative
tile sizes.  If CUDA is unavailable it writes a truthful failure record.
"""
from __future__ import annotations
import argparse, csv, json, statistics, time
from pathlib import Path
import torch

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', default='results_hpca_xorflow/cuda_microbench.csv')
    ap.add_argument('--log', default='artifacts_hpca_xorflow/logs/cuda_microbench.json')
    ap.add_argument('--repetitions', type=int, default=100)
    args = ap.parse_args()
    out, log = Path(args.output), Path(args.log); out.parent.mkdir(parents=True, exist_ok=True); log.parent.mkdir(parents=True, exist_ok=True)
    fields = ['kernel','tile_rows','slice_width','repetitions','median_us','p05_us','p95_us','throughput_gbps','event_rate_per_s','device','success','error']
    if not torch.cuda.is_available():
        row = {k:'' for k in fields}; row.update(success='false', error='CUDA unavailable', repetitions=args.repetitions)
        with out.open('w', newline='') as f: csv.DictWriter(f, fieldnames=fields).writeheader(); csv.DictWriter(f, fieldnames=fields).writerow(row)
        log.write_text(json.dumps({'success':False,'error':'CUDA unavailable'}, indent=2)+'\n'); return 0
    dev=torch.device('cuda'); device=torch.cuda.get_device_name(dev); rows=[]
    for n,c in ((128,128),(256,128),(128,256)):
        anchor=torch.randint(0,2,(n,c),device=dev,dtype=torch.uint8); masks=torch.randint(0,2,(n,c),device=dev,dtype=torch.uint8)
        values=torch.randn(n,c,device=dev,dtype=torch.float32); packed=torch.randint(0,2,(n,c),device=dev,dtype=torch.uint8)
        for name, fn, elems in [('xor_decode',lambda: torch.bitwise_xor(anchor,masks), n*c), ('popcount',lambda: torch.sum(torch.bitwise_xor(anchor,masks),dim=1), n*c), ('packed_gather',lambda: values.masked_select(packed.bool()), n*c)]:
            for _ in range(10): fn(); torch.cuda.synchronize()
            times=[]
            for _ in range(args.repetitions):
                st=torch.cuda.Event(enable_timing=True); en=torch.cuda.Event(enable_timing=True); st.record(); fn(); en.record(); en.synchronize(); times.append(float(st.elapsed_time(en))*1000)
            times.sort(); med=statistics.median(times); p05=times[max(0,int(.05*len(times))-1)]; p95=times[min(len(times)-1,int(.95*len(times)))]
            rows.append({'kernel':name,'tile_rows':n,'slice_width':c,'repetitions':args.repetitions,'median_us':med,'p05_us':p05,'p95_us':p95,'throughput_gbps':(elems*4/med/1000 if med else 0),'event_rate_per_s':(elems/(med/1e6) if med else 0),'device':device,'success':'true','error':''})
    with out.open('w',newline='') as f: w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    log.write_text(json.dumps({'success':True,'device':device,'rows':len(rows),'repetitions':args.repetitions},indent=2)+'\n'); return 0
if __name__=='__main__': raise SystemExit(main())
