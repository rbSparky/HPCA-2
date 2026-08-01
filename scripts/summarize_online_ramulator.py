#!/usr/bin/env python3
"""Validate that Ramulator served every emitted online HBM request."""
from __future__ import annotations
import argparse,json
from pathlib import Path

def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--stats',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--drain-cycles',type=int,default=4096);a=p.parse_args()
 stats=json.loads(a.stats.read_text()); manifest=json.loads(a.manifest.read_text()); controllers=stats['memory_system']['controller']
 served=sum(int(c['num_read_reqs_served'])+int(c['num_write_reqs_served']) for c in controllers)
 forwarded=sum(int(c.get('num_read_reqs_forwarded',0)) for c in controllers)
 submitted=int(manifest['submitted_requests']); cycles=max(int(c['cycles']) for c in controllers)-a.drain_cycles
 payload={**manifest,'tool':'Ramulator2','dram_cycles':cycles,'served_requests':served,
  'forwarded_requests':forwarded,'accounted_requests':served+forwarded,
  'all_requests_drained':served+forwarded==submitted,'tool_run_success':served+forwarded==submitted,
  'controller_count':len(controllers),'drain_cycles':a.drain_cycles}
 a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n')
 if served+forwarded!=submitted: raise SystemExit(f'Ramulator accounted {served+forwarded} of {submitted}')
 print(json.dumps(payload,sort_keys=True))
if __name__=='__main__':main()
