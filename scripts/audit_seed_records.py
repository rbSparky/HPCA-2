import json
from pathlib import Path
import pandas as pd

root = Path('/home/rishabh/HPCA2/mosaic_delta_phase1')
workloads_dir = root / 'artifacts_hpca_xorflow/workloads'

print("=== DEEP AUDIT OF WORKLOAD RECORDS AND SEEDS ===")

records = []
for p in sorted(workloads_dir.glob('*/record.json')):
    try:
        data = json.loads(p.read_text())
        records.append({
            'config_id': p.parent.name,
            'dataset': data.get('dataset'),
            'seed': data.get('seed'),
            'width': data.get('width'),
            'layers': data.get('layers'),
            'model_kind': data.get('model_kind'),
            'fp32_test_accuracy': data.get('fp32_test_accuracy'),
            'fp8_fp16_test_accuracy': data.get('fp8_fp16_test_accuracy'),
            'fp8_test_micro_f1': data.get('fp8_fp16_test_micro_f1'),
            'best_epoch': data.get('best_epoch'),
            'created_utc': data.get('created_utc')
        })
    except Exception as e:
        print(f"Error reading {p}: {e}")

df = pd.DataFrame(records)
print(f"Total workload records found: {len(df)}\n")
print(df.to_string(index=False))
