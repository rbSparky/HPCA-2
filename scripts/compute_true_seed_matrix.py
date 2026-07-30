import json
import numpy as np
import pandas as pd
from pathlib import Path
from mosaic_validation.causal_xorflow import causal_pair_statistics

root = Path('/home/rishabh/HPCA2/mosaic_delta_phase1')
workloads_dir = root / 'artifacts_hpca_xorflow/workloads'

cases_by_dataset = {
    'Reddit': [
        'reddit_deepres8_w128_s7_native',
        'reddit_deepres8_w128_s17_native',
        'reddit_deepres8_w128_s27_native'
    ],
    'OGBN-Arxiv': [
        'ogbn_arxiv_deepres8_w128_s7',
        'ogbn_arxiv_deepres8_w128_s17',
        'ogbn_arxiv_deepres8_w128_s27'
    ],
    'Flickr': [
        'flickr_deepres8_w128_s7',
        'flickr_deepres8_w128_s17',
        'flickr_deepres8_w128_s27'
    ]
}

print("=== EXACT MULTI-SEED HARNESS EVALUATION ===")

dataset_summaries = []

for ds, config_ids in cases_by_dataset.items():
    print(f"\nEvaluating Dataset: {ds}")
    seed_records = []
    
    for config_id in config_ids:
        rec_path = workloads_dir / config_id / 'record.json'
        if not rec_path.exists():
            print(f"Skipping missing record: {config_id}")
            continue
            
        rec = json.loads(rec_path.read_text())
        seed = rec.get('seed')
        fp32_acc = rec.get('fp32_test_accuracy') or rec.get('fp32_test_micro_f1')
        fp8_acc = rec.get('fp8_fp16_test_accuracy') or rec.get('fp8_fp16_test_micro_f1')
        
        # Load support masks
        supports_path = workloads_dir / config_id / 'fp8_supports.npz'
        if not supports_path.exists():
            print(f"Missing supports file for {config_id}")
            continue
            
        archive = np.load(supports_path)
        shape = archive['shape']
        layers, rows, features = map(int, shape)
        packed = archive['packed']
        unpacked = np.unpackbits(packed, axis=2)[:, :, :features].astype(bool)
        
        # Pair l4 -> l5 (0-indexed indices 3 and 4)
        m4 = unpacked[3]
        m5 = unpacked[4]
        
        pair_stack = np.stack([m4, m5])
        stats = causal_pair_statistics(pair_stack, cohort_size=32)
        
        support_ratio = float(stats['support_ratio_to_beicsr'])
        traffic_red = 1.0 - support_ratio
        
        print(f"  Seed {seed:2d} ({config_id:32s}): Support Ratio = {support_ratio:.3f} | Metadata Red = {traffic_red:.1%} | FP8 Acc = {fp8_acc:.4f} (FP32 = {fp32_acc:.4f})")
        
        seed_records.append({
            'seed': seed,
            'traffic_red': traffic_red,
            'support_ratio': support_ratio,
            'fp8_acc': fp8_acc,
            'fp32_acc': fp32_acc,
            'drop': (fp32_acc - fp8_acc) if (fp32_acc is not None and fp8_acc is not None) else 0.0
        })
        
    if seed_records:
        tr = [r['traffic_red'] for r in seed_records]
        sr = [r['support_ratio'] for r in seed_records]
        ac = [r['fp8_acc'] for r in seed_records if r['fp8_acc'] is not None]
        dr = [r['drop'] for r in seed_records]
        
        dataset_summaries.append({
            'Dataset': ds,
            'Seeds Tested': len(seed_records),
            'Support Ratio Mean': np.mean(sr),
            'Support Ratio Std': np.std(sr),
            'Metadata Red Mean': np.mean(tr),
            'Metadata Red Std': np.std(tr),
            'FP8 Acc Mean': np.mean(ac),
            'FP8 Acc Std': np.std(ac),
            'FP32 Acc Mean': np.mean([r['fp32_acc'] for r in seed_records if r['fp32_acc'] is not None]),
            'Acc Drop Mean': np.mean(dr),
            'Acc Drop Std': np.std(dr)
        })

df_sum = pd.DataFrame(dataset_summaries)
print("\n" + "="*80)
print("=== FINAL ACCURATE MULTI-SEED DATASET SUMMARY ===")
print("="*80)
print(df_sum.to_string(index=False))
