#!/usr/bin/env python3
"""Consolidate dependency-complete reviewer outputs and build paper tables."""
from __future__ import annotations
import argparse,csv,hashlib,json,math
from pathlib import Path

def combine(paths:list[Path],dest:Path)->int:
 dest.parent.mkdir(parents=True,exist_ok=True); count=0; header=None
 with dest.open('w',newline='') as out:
  writer=None
  for path in paths:
   # Consolidated outputs may match the source glob on a rerun.  Ignore
   # empty/fieldless placeholders rather than producing a misleading partial
   # manifest or raising while rebuilding the same report.
   if not path.is_file() or path.stat().st_size == 0 or path.resolve() == dest.resolve():
    continue
   with path.open() as src:
    reader=csv.DictReader(src)
    if reader.fieldnames is None:
     continue
    if header is None: header=reader.fieldnames; writer=csv.DictWriter(out,fieldnames=header);writer.writeheader()
    elif reader.fieldnames!=header: raise ValueError(f'schema mismatch: {path}')
    for row in reader: writer.writerow(row);count+=1
 return count

def one(path:Path)->dict[str,str]: return next(csv.DictReader(path.open()))
def sha(path:Path)->str:
 h=hashlib.sha256()
 with path.open('rb') as f:
  for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
 return h.hexdigest()

def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path('results_hpca_xorflow/reviewer_spec_v3'));a=p.parse_args();r=a.root
 specs={
  'serializer/roundtrip_all_real.csv':r.glob('serializer/roundtrip_*.csv'),
  'characterization/adjacent_support.csv':r.glob('characterization/adjacent_support_*.csv'),
  'online_replay/support_records.csv':r.glob('online_replay/support_records_*_finite_retention.csv'),
  'online_replay/memory_transactions.csv':r.glob('online_replay/memory_transactions_*_finite_retention.csv'),
  'online_replay/run_summary.csv':r.glob('online_replay/run_summary_*_finite_retention.csv'),
  'ablation/baseline_selection.csv':r.glob('ablation/*/baseline_selection_*.csv'),
  'ablation/component_ablation.csv':r.glob('ablation/*/component_ablation_*.csv'),
  'ablation/format_selection.csv':r.glob('ablation/*/format_selection_*.csv'),
  'encoder/encoder_trace.csv':r.glob('encoder/encoder_trace_*.csv'),
  'decoder/decoder_cluster_trace.csv':r.glob('decoder/*/decoder_cluster_trace_b*.csv'),
  'decoder/conflicts.csv':r.glob('decoder/*/conflicts_b*.csv'),
 'schedule/system_cycles.csv':r.glob('schedule/*/system_cycles.csv'),
 'schedule/analytical_vs_event.csv':r.glob('schedule/*/analytical_vs_event.csv'),
  'schedule/causal_event_schedule.csv':r.glob('schedule/*/causal_event_schedule.csv'),
  'schedule/causal_resource_audit.csv':r.glob('schedule/*/causal_resource_audit.csv'),
  'schedule/causal_recurrence_check.csv':r.glob('schedule/*/causal_recurrence_check.csv'),
  'schedule/causal_tile_event_trace.csv':r.glob('schedule/*/causal_tile_event_trace.csv'),
}
 manifest=[]
 for rel,it in specs.items():
  paths=sorted(it); count=combine(paths,r/rel) if paths else 0
  manifest.append({'artifact':rel,'source_files':len(paths),'rows':count,'sha256':sha(r/rel) if paths else '','status':'complete' if paths else 'missing'})
 summaries={x['run_id']:x for x in map(one,sorted(r.glob('online_replay/run_summary_*_finite_retention.csv')))}
 schedules={}
 for path in r.glob('schedule/*/system_cycles.csv'):
  rows=list(csv.DictReader(path.open())); schedules[path.parent.name]={x['variant']:x for x in rows}
 physical={}
 for path in r.glob('physical_traffic/physical_traffic_*.csv'):
  rows=list(csv.DictReader(path.open())); b=sum(int(x['baseline_total_bytes']) for x in rows);q=sum(int(x['xorflow_total_bytes']) for x in rows);physical[path.stem.replace('physical_traffic_','')]=(b,q)
 table=[]
 for cfg,x in sorted(summaries.items()):
  b,q=physical.get(cfg,(0,0)); sched=schedules.get(cfg,{})
  table.append({'config_id':cfg,'support_reduction':1-int(x['xorflow_support_bytes'])/int(x['baseline_support_bytes']),
   'exact_edge_traffic_reduction':1-q/b if b else '',
   'event_speedup':float(sched.get('XORFLOW_ONLINE',{}).get('speedup_vs_selected_baseline',0)) if sched else '',
   'anchor_read_bytes':x['anchor_read_bytes'],'format_fractions_json':x['format_fractions_json']})
 out=r/'report'/'paper_summary.csv';out.parent.mkdir(parents=True,exist_ok=True)
 if table:
  with out.open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=list(table[0]));w.writeheader();w.writerows(table)
 lines=['# Reviewer-Spec Results','', '| Workload | Support reduction | Exact edge-traffic reduction | Event-driven speedup |','|---|---:|---:|---:|']
 for x in table:
  f=lambda v: 'pending' if v=='' else f'{float(v):.3f}'
  lines.append(f"| {x['config_id']} | {f(x['support_reduction'])} | {f(x['exact_edge_traffic_reduction'])} | {f(x['event_speedup'])} |")
 (r/'report'/'PAPER_TABLES.md').write_text('\n'.join(lines)+'\n')
 (r/'ARTIFACT_MANIFEST.csv').parent.mkdir(parents=True,exist_ok=True)
 with (r/'ARTIFACT_MANIFEST.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=list(manifest[0]));w.writeheader();w.writerows(manifest)
 print(json.dumps({'artifacts':len(manifest),'workloads':len(table),'missing':[x['artifact'] for x in manifest if x['status']=='missing']},sort_keys=True))
if __name__=='__main__':main()
