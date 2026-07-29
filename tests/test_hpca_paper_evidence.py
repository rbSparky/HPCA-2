"""Canonical evidence builder regression test."""
from __future__ import annotations

import pandas as pd

from scripts.build_hpca_paper_evidence import build


def test_evidence_builder_preserves_source_paths_and_unassessed_gates(tmp_path):
    run = tmp_path / "results_hpca_xorflow/complete_suite/runs/example"
    run.mkdir(parents=True)
    pd.DataFrame([{"config_id": "example", "host_speedup": 1.2, "beicsr_host_cycles": 12, "xorflow_host_cycles": 10, "combination_scalesim_utilization": 0.5, "model_scope": "test"}]).to_csv(run / "host_model.csv", index=False)
    md, evidence, gates = build(tmp_path)
    assert md.exists() and evidence.exists() and gates.exists()
    assert "runs/example/host_model.csv" in evidence.read_text()
    assert "UNASSESSED" in gates.read_text()
