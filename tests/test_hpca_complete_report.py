from __future__ import annotations

from pathlib import Path

import pandas as pd

from scripts.report_hpca_complete_suite import run


def test_complete_report_aggregates_isolated_host_runs(tmp_path: Path) -> None:
    host = tmp_path / "results_hpca_xorflow/complete_suite/paper_suite_test/runs/example/host_model.csv"
    host.parent.mkdir(parents=True)
    pd.DataFrame([{
        "config_id": "example", "host_speedup": 1.2,
        "traffic_reduction": 0.25, "support_ratio_to_beicsr": 0.6,
        "support_cache_fits": True,
    }]).to_csv(host, index=False)
    result = run(tmp_path)
    assert result.iloc[0]["config_id"] == "example"
    assert (tmp_path / "results_hpca_xorflow/complete_suite/PAPER_SUITE_HOST_RESULTS.md").exists()
