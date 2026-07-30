import json
import numpy as np
import pandas as pd
from pathlib import Path

root = Path('.')
runs = root / 'results_hpca_xorflow/complete_suite/runs'
workloads = root / 'artifacts_hpca_xorflow/workloads'

rows = []
for d in sorted(runs.iterdir()):
    h = d / 'host_model.csv'
    p = d / 'causal_preflight.csv'
    if h.exists() and p.exists():
        dh = pd.read_csv(h)
        dp = pd.read_csv(p)
        if not dh.empty and not dp.empty:
            config_id = str(dh.iloc[0].get('config_id', ''))
            rec_p = workloads / config_id / 'record.json'
            acc, fp32, drop = None, None, None
            if rec_p.exists():
                rec = json.loads(rec_p.read_text())
                acc = rec.get('fp8_fp16_test_accuracy') or rec.get('fp8_fp16_test_micro_f1')
                fp32 = rec.get('fp32_test_accuracy') or rec.get('fp32_test_micro_f1')
                if acc is not None and fp32 is not None:
                    drop = fp32 - acc
            rows.append({
                'run': d.name,
                'speedup': round(float(dh.iloc[0]['host_speedup']), 4),
                'traffic': round(float(dp.iloc[0]['traffic_reduction']), 4),
                'support': round(float(dp.iloc[0]['support_ratio_to_beicsr']), 4),
                'beicsr_cy': int(dh.iloc[0]['beicsr_host_cycles']),
                'xorflow_cy': int(dh.iloc[0]['xorflow_host_cycles']),
                'fp8_acc': round(acc, 6) if acc is not None else None,
                'fp32_acc': round(fp32, 6) if fp32 is not None else None,
                'acc_drop': round(drop, 6) if drop is not None else None,
            })

df = pd.DataFrame(rows)
df.to_csv('results_hpca_xorflow/all_runs_master.csv', index=False)
print(f"Total runs: {len(df)}")
print(df.to_string(index=False))
