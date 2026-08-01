"""Audit contract test for the common format matrix."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_format_matrix_audit_accepts_complete_contract(tmp_path: Path) -> None:
    formats = [
        ("DENSE", True), ("CSR32", True), ("CSR_PACKED", True), ("BEICSR", True),
        ("INDEPENDENT_BEST", True), ("X0_CAUSAL_INDEPENDENT", True),
        ("X1_CAUSAL_AUTO", True), ("X2_CAUSAL_FORCE", True),
        ("O0_OFFLINE_MAJORITY", False), ("O1_FREE_SUPPORT", False),
    ]
    source = tmp_path / "matrix.csv"; output = tmp_path / "audit.json"
    pd.DataFrame([{
        "format": name, "deployable": deployable, "exact_layout_pass": True,
        "exact_decode_pass": True, "total_traffic_bytes": 1,
        "traffic_ratio_to_beicsr": 1.0, "selected_xorflow_tile_slices": 0,
    } for name, deployable in formats]).to_csv(source, index=False)
    script = Path(__file__).parents[1] / "scripts/verify_hpca_format_matrix.py"
    subprocess.run([sys.executable, str(script), "--input", str(source), "--output", str(output)], check=True)
    assert '"status": "PASS"' in output.read_text()
