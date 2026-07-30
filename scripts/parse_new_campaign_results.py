import json
import glob
import os
import pandas as pd
from pathlib import Path

root = Path('/home/rishabh/HPCA2/mosaic_delta_phase1')
runs_dir = root / 'results_hpca_xorflow/complete_suite/runs'
workloads_dir = root / 'artifacts_hpca_xorflow/workloads'

print("=== DISCOVERING ALL COMPLETED RUNS ===")

subdirs = sorted([d for d in runs_dir.iterdir() if d.is_dir()])
rows = []

for case_dir in subdirs:
    host_csv = case_dir / 'host_model.csv'
    preflight_csv = case_dir / 'causal_preflight.csv'
    
    if not host_csv.exists() or not preflight_csv.exists():
        continue
        
    df_host = pd.read_csv(host_csv)
    df_pref = pd.read_csv(preflight_csv)
    
    if df_host.empty or df_pref.empty:
        continue
        
    config_id = str(df_host.iloc[0].get('config_id', ''))
    record_json = workloads_dir / config_id / 'record.json'
    accuracy = None
    if record_json.exists():
        rec = json.loads(record_json.read_text())
        accuracy = rec.get('fp8_fp16_test_accuracy') or rec.get('fp32_test_accuracy')
        
    rows.append({
        'run_id': case_dir.name,
        'config_id': config_id,
        'host_speedup': float(df_host.iloc[0]['host_speedup']),
        'traffic_reduction': float(df_pref.iloc[0]['traffic_reduction']),
        'support_ratio': float(df_pref.iloc[0]['support_ratio_to_beicsr']),
        'beicsr_cycles': int(df_host.iloc[0]['beicsr_host_cycles']),
        'xorflow_cycles': int(df_host.iloc[0]['xorflow_host_cycles']),
        'accuracy': accuracy
    })

df = pd.DataFrame(rows)
print(f"Total valid run cases found: {len(df)}\n")
print(df[['run_id', 'host_speedup', 'traffic_reduction', 'support_ratio', 'accuracy']].to_string(index=False))
