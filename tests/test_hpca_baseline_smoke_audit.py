"""Fail-closed audit shape test for the GPU1 baseline smoke."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd


def test_baseline_smoke_audit_accepts_complete_exact_rows(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.csv"
    causal = tmp_path / "causal.csv"
    host = tmp_path / "host.csv"
    output = tmp_path / "audit.json"
    pd.DataFrame([{"format": name, "exact_layout_pass": True, "exact_decode_pass": True, "total_traffic_bytes": index + 1} for index, name in enumerate(("DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST"))]).to_csv(baseline, index=False)
    pd.DataFrame([{"exact_decode_pass": True, "causal_deployable": True}]).to_csv(causal, index=False)
    pd.DataFrame([{"combination_scalesim_success": True, "support_cache_fits": True}]).to_csv(host, index=False)
    script = Path(__file__).parents[1] / "scripts/verify_hpca_baseline_smoke.py"
    subprocess.run([sys.executable, str(script), "--baselines", str(baseline), "--causal", str(causal), "--host", str(host), "--output", str(output)], check=True)
    assert '"status": "PASS"' in output.read_text()
