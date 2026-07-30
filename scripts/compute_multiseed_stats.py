import json
import numpy as np
import pandas as pd
from pathlib import Path

root = Path('/home/rishabh/HPCA2/mosaic_delta_phase1')
runs_dirs = [
    root / 'results_hpca_xorflow/complete_suite/runs',
    root / 'results_hpca_xorflow/runs'
]
workloads_dir = root / 'artifacts_hpca_xorflow/workloads'

# Match run names by dataset
def get_dataset_tag(name):
    n = name.lower()
    if 'reddit' in n and ('bw' not in n and 'cache' not in n and 'order' not in n and 'slice' not in n and 'support' not in n and 'tile' not in n and 'window' not in n):
        return 'Reddit'
    if 'arxiv' in n and ('bw' not in n and 'cache' not in n and 'order' not in n and 'slice' not in n and 'support' not in n and 'tile' not in n and 'window' not in n and 'depth' not in n and 'width' not in n and 'decoder' not in n and 'single' not in n and 'gin' not in n and 'graphsage' not in n):
        return 'OGBN-Arxiv'
    if 'flickr' in n and ('cache' not in n and 'order' not in n and 'slice' not in n and 'gin' not in n and 'graphsage' not in n):
        return 'Flickr'
    if 'yelp' in n and ('cache' not in n and 'order' not in n and 'slice' not in n):
        return 'Yelp (Borderline)'
    if 'citeseer' in n:
        return 'CiteSeer'
    if 'cora' in n:
        return 'Cora'
    if 'pubmed' in n and 'gin' not in n and 'graphsage' not in n:
        return 'PubMed'
    if 'chameleon' in n:
        return 'Chameleon (Adversarial)'
    return None

data_map = {}

for r_dir in runs_dirs:
    if not r_dir.exists(): continue
    for case_dir in r_dir.iterdir():
        if not case_dir.is_dir(): continue
        ds = get_dataset_tag(case_dir.name)
        if not ds: continue
        
        host_csv = case_dir / 'host_model.csv'
        preflight_csv = case_dir / 'causal_preflight.csv'
        if not host_csv.exists() or not preflight_csv.exists():
            continue
            
        dh = pd.read_csv(host_csv)
        dp = pd.read_csv(preflight_csv)
        if dh.empty or dp.empty: continue
        
        config_id = str(dh.iloc[0].get('config_id', ''))
        rec_p = workloads_dir / config_id / 'record.json'
        acc = None
        drop = None
        if rec_p.exists():
            rec = json.loads(rec_p.read_text())
            fp8_acc = rec.get('fp8_fp16_test_accuracy') or rec.get('fp32_test_accuracy')
            fp32_acc = rec.get('fp32_test_accuracy')
            if fp8_acc is not None:
                acc = float(fp8_acc)
            if fp8_acc is not None and fp32_acc is not None:
                drop = float(fp32_acc) - float(fp8_acc)
                
        entry = {
            'run_id': case_dir.name,
            'speedup': float(dh.iloc[0]['host_speedup']),
            'traffic_red': float(dp.iloc[0]['traffic_reduction']),
            'support_ratio': float(dp.iloc[0]['support_ratio_to_beicsr']),
            'acc': acc,
            'drop': drop
        }
        data_map.setdefault(ds, {})[case_dir.name] = entry

summary = []
for ds, cases in data_map.items():
    entries = list(cases.values())
    sp = [e['speedup'] for e in entries]
    tr = [e['traffic_red'] for e in entries]
    su = [e['support_ratio'] for e in entries]
    ac = [e['acc'] for e in entries if e['acc'] is not None]
    dr = [e['drop'] for e in entries if e['drop'] is not None]
    
    summary.append({
        'Dataset': ds,
        'Num Seeds': len(entries),
        'Speedup Mean': np.mean(sp),
        'Speedup Std': np.std(sp) if len(sp) > 1 else 0.0,
        'Traffic Red Mean': np.mean(tr),
        'Traffic Red Std': np.std(tr) if len(tr) > 1 else 0.0,
        'Support Ratio Mean': np.mean(su),
        'Support Ratio Std': np.std(su) if len(su) > 1 else 0.0,
        'Acc Mean': np.mean(ac) if len(ac) else 0.0,
        'Acc Std': np.std(ac) if len(ac) > 1 else 0.0,
        'Acc Drop Mean': np.mean(dr) if len(dr) else 0.0,
    })

df_res = pd.DataFrame(summary)
print("=== MULTI-SEED AGGREGATED STATISTICS ACROSS DATASETS ===")
print(df_res.to_string(index=False))
