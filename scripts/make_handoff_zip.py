#!/usr/bin/env python3
"""
Create a clean handoff zip for the XORFLOW HPCA project.
Includes: src/, scripts/, configs/, tests/, tools/, rtl/, docs/,
          results_hpca_xorflow/ (excl. large npz/pt), key markdown files.
Excludes: .git, __pycache__, *.npz, *.pt, *.zip, artifacts_*, checkpoints_*,
          results_phase*/_final8/safezone, vendor dirs, data/.
"""

import os
import zipfile
from pathlib import Path
from datetime import datetime

root = Path('/home/rishabh/HPCA2/mosaic_delta_phase1')
timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
out_zip = root / f'XORFLOW_HPCA_HANDOFF_{timestamp}.zip'

INCLUDE_DIRS = [
    'src',
    'scripts',
    'configs',
    'tests',
    'tools',
    'rtl',
    'docs',
    'results_hpca_xorflow',
]

INCLUDE_ROOT_FILES = [
    'MAIN_RESULTS_AND_EVIDENCE.md',  # alias below
    '.gitignore',
    'pyproject.toml',
    'README.md',
    'AGENTS.md',
    'HANDOFF_HPCA_PROGRESS.md',
    'plan.md',
    'dramsim3.json',
]

# Extensions to always skip (large binary/data files)
SKIP_EXTENSIONS = {
    '.npz', '.pt', '.pth', '.zip', '.gz', '.tar',
    '.npy', '.bin', '.ckpt', '.pkl', '.pickle',
    '.pyc', '.pyo', '.so', '.o', '.a',
    '.db', '.sqlite', '.h5', '.hdf5',
}

# Directory name fragments to always skip
SKIP_DIR_FRAGMENTS = {
    '__pycache__', '.git', '.pytest_cache',
    'vendor', 'node_modules',
    'artifacts_phase', 'artifacts_final', 'artifacts_phase3',
    'artifacts_safezone', 'artifacts_rescue',
    'checkpoints_', 'results_phase', 'results_final', 'results_rescue',
    'results_safezone', 'results_phase3', 'data',
    '.xorflow_jobs',
}

def should_skip_dir(dirpath: Path) -> bool:
    name = dirpath.name
    for frag in SKIP_DIR_FRAGMENTS:
        if name.startswith(frag) or name == frag:
            return True
    return False

def should_skip_file(filepath: Path) -> bool:
    if filepath.suffix.lower() in SKIP_EXTENSIONS:
        return True
    # Skip huge files > 5 MB
    try:
        if filepath.stat().st_size > 5 * 1024 * 1024:
            print(f"  [SKIP large] {filepath.relative_to(root)} ({filepath.stat().st_size/1024/1024:.1f} MB)")
            return True
    except Exception:
        pass
    return False

added = 0
skipped = 0

with zipfile.ZipFile(out_zip, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:

    # 1. Add root-level markdown and config files
    for fname in INCLUDE_ROOT_FILES:
        fpath = root / fname
        if fpath.exists() and not should_skip_file(fpath):
            arcname = f'XORFLOW_HANDOFF/{fname}'
            zf.write(fpath, arcname)
            added += 1
            print(f"  [root] {fname}")

    # 2. Special: add MAIN_RESULTS_AND_EVIDENCE.md at root level for visibility
    main_results = root / 'results_hpca_xorflow' / 'MAIN_RESULTS_AND_EVIDENCE.md'
    if main_results.exists():
        zf.write(main_results, 'XORFLOW_HANDOFF/MAIN_RESULTS_AND_EVIDENCE.md')
        added += 1
        print(f"  [root copy] MAIN_RESULTS_AND_EVIDENCE.md")

    # 3. Add included directories recursively
    for dir_name in INCLUDE_DIRS:
        dir_path = root / dir_name
        if not dir_path.exists():
            print(f"  [MISSING DIR] {dir_name}")
            continue

        for dirpath, dirnames, filenames in os.walk(dir_path):
            dp = Path(dirpath)

            # Prune directories in-place
            dirnames[:] = [
                d for d in dirnames
                if not should_skip_dir(dp / d)
                and not (dp / d).name.startswith('.')
            ]

            for fname in sorted(filenames):
                fpath = dp / fname
                if should_skip_file(fpath):
                    skipped += 1
                    continue
                rel = fpath.relative_to(root)
                arcname = f'XORFLOW_HANDOFF/{rel}'
                zf.write(fpath, arcname)
                added += 1

zip_size_mb = out_zip.stat().st_size / 1024 / 1024
print(f"\n✅ Handoff zip created: {out_zip.name}")
print(f"   Files added  : {added}")
print(f"   Files skipped: {skipped}")
print(f"   Zip size     : {zip_size_mb:.2f} MB")
