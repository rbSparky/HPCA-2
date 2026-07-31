#!/usr/bin/env python3
"""CACTI-7 audit for the banked 16-KiB reconstructed-support cache."""
from __future__ import annotations
import argparse,csv,re,subprocess,tempfile
from pathlib import Path

def value(text:str,label:str)->float:
 m=re.search(label+r'\s*:?\s*([0-9.eE+-]+)',text)
 if not m: raise ValueError(f'missing CACTI field {label}')
 return float(m.group(1))
def main()->None:
 p=argparse.ArgumentParser();p.add_argument('--template',type=Path,default=Path.home()/'src/cacti-hp7/cache.cfg');p.add_argument('--output-dir',type=Path,required=True);a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True);base=a.template.read_text();rows=[]
 for banks in (8,16,32):
  cfg=re.sub(r'^-size \(bytes\) \d+', '-size (bytes) 16384',base,flags=re.M)
  cfg=re.sub(r'^-block size \(bytes\) \d+', '-block size (bytes) 8',cfg,flags=re.M)
  cfg=re.sub(r'^-associativity \d+', '-associativity 1',cfg,flags=re.M)
  cfg=re.sub(r'^-UCA bank count \d+', f'-UCA bank count {banks}',cfg,flags=re.M)
  cfg=re.sub(r'^-technology \(u\) [0-9.]+', '-technology (u) 0.045',cfg,flags=re.M)
  cfg=re.sub(r'^-output/input bus width \d+', '-output/input bus width 64',cfg,flags=re.M)
  with tempfile.NamedTemporaryFile('w',suffix='.cfg') as f:
   f.write(cfg);f.flush();run=subprocess.run(['cacti','-infile',f.name],text=True,capture_output=True,check=True)
  log=a.output_dir/f'cacti_support_cache_b{banks}.txt';log.write_text(run.stdout)
  rows.append({'capacity_bytes':16384,'banks':banks,'technology_nm':45,'access_time_ns':value(run.stdout,r'Access time \(ns\)'),
   'cycle_time_ns':value(run.stdout,r'Cycle time \(ns\)'), 'dynamic_read_energy_nj':value(run.stdout,r'Total dynamic read energy per access \(nJ\)'),
   'data_array_area_mm2':value(run.stdout,r'Data array: Area \(mm2\)'), 'tool_success':True,'raw_log':str(log)})
 with (a.output_dir/'support_cache_cacti.csv').open('w',newline='') as h:w=csv.DictWriter(h,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
if __name__=='__main__':main()
