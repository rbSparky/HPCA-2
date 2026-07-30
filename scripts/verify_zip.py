import zipfile
from pathlib import Path

z = Path('/home/rishabh/HPCA2/mosaic_delta_phase1/XORFLOW_HPCA_HANDOFF_20260730T092127Z.zip')
print(f"Zip size: {z.stat().st_size / 1024 / 1024:.2f} MB")

with zipfile.ZipFile(z) as zf:
    ns = sorted(zf.namelist())
    # top-level dirs under XORFLOW_HANDOFF/
    tops = {}
    for n in ns:
        parts = n.split('/')
        if len(parts) >= 2:
            key = parts[1]
            tops[key] = tops.get(key, 0) + 1

    print(f"\nTotal entries: {len(ns)}")
    print("\nTop-level structure (XORFLOW_HANDOFF/):")
    for k, cnt in sorted(tops.items()):
        print(f"  {k:<40s}  {cnt:>4d} items")

    # Spot-check key files
    key_files = [
        'XORFLOW_HANDOFF/MAIN_RESULTS_AND_EVIDENCE.md',
        'XORFLOW_HANDOFF/results_hpca_xorflow/MAIN_RESULTS_AND_EVIDENCE.md',
        'XORFLOW_HANDOFF/results_hpca_xorflow/all_runs_master.csv',
        'XORFLOW_HANDOFF/results_hpca_xorflow/HPCA_PAPER_READY_RESULTS.md',
        'XORFLOW_HANDOFF/results_hpca_xorflow/complete_suite/HPCA_PAPER_EVIDENCE.md',
        'XORFLOW_HANDOFF/src/mosaic_validation/causal_xorflow.py',
        'XORFLOW_HANDOFF/scripts/compute_true_seed_matrix.py',
        'XORFLOW_HANDOFF/configs/hpca_paper_ready_tracking.yaml',
    ]
    print("\nKey file presence check:")
    for kf in key_files:
        present = kf in zf.namelist()
        status = "✅" if present else "❌ MISSING"
        print(f"  {status}  {kf.replace('XORFLOW_HANDOFF/', '')}")
