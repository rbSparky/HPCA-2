#!/usr/bin/env python3
"""Run a compact independent DRAMsim3 timing cross-check and record provenance."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--binary',default='tools/vendor/DRAMsim3/build/dramsim3main'); p.add_argument('--config',default='tools/vendor/DRAMsim3/configs/DDR4_8Gb_x8_3200.ini'); p.add_argument('--output',default='artifacts_hpca_xorflow/dramsim3/smoke.json'); a=p.parse_args()
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); trace=out.with_suffix('.trace'); trace.write_text('\n'.join(str(64*i) for i in range(64))+'\n')
    try:
        r=subprocess.run([a.binary,a.config,'-c','10000','-t',str(trace)],capture_output=True,text=True,timeout=120)
        ok=r.returncode==0; err=(r.stderr or '')[-1000:]
    except Exception as e: ok=False; r=None; err=str(e)
    out.write_text(json.dumps({'tool':'DRAMsim3','memory_model':'DDR4_8Gb_x8_3200','roofline_only':False,'trace':str(trace),'submitted_lines':64,'tool_run_success':ok,'returncode':None if r is None else r.returncode,'error':err},indent=2)+'\n')
    return 0
if __name__=='__main__': raise SystemExit(main())
