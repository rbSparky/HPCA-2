"""Quality-audit contract test."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def test_quality_audit_distinguishes_hard_valid_and_borderline(tmp_path: Path) -> None:
    root = tmp_path / "artifacts_hpca_xorflow/workloads"
    for config, metric, value in (("ogbn_arxiv_demo", "accuracy", 0.70), ("yelp_demo", "micro_f1", 0.44)):
        directory = root / config; directory.mkdir(parents=True)
        (directory / "record.json").write_text(json.dumps({"finite_loss": True, f"fp8_fp16_test_{metric}": value}))
        np.savez(directory / "fp8_supports.npz", shape=np.array([1, 1, 1]), packed=np.array([0], dtype=np.uint8))
    output = tmp_path / "quality.csv"
    script = Path(__file__).parents[1] / "scripts/audit_hpca_quality.py"
    subprocess.run([sys.executable, str(script), "--project", str(tmp_path), "--configs", "ogbn_arxiv_demo", "yelp_demo", "--output", str(output)], check=True)
    statuses = pd.read_csv(output).set_index("config_id").status.to_dict()
    assert statuses == {"ogbn_arxiv_demo": "HARD_VALID", "yelp_demo": "BORDERLINE"}
