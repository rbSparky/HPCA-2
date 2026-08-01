from __future__ import annotations

import csv
from pathlib import Path

from mosaic_validation.hpca_campaign import run
from mosaic_validation.hpca_xorflow_cli import _workload_dataset


def test_campaign_records_success_and_dependency_skip(tmp_path: Path) -> None:
    config = {
        "campaign_id": "unit_campaign",
        "deadline_utc": "2100-01-01T00:00:00Z",
        "deadline_margin_minutes": 1,
        "tasks": [
            {"task_id": "good", "stage": "smoke", "estimated_minutes": 1, "weight": 1, "command": "true"},
            {"task_id": "bad", "stage": "smoke", "estimated_minutes": 1, "weight": 1, "command": "false"},
            {"task_id": "blocked", "stage": "analysis", "estimated_minutes": 1, "weight": 1, "depends_on": ["bad"], "command": "true"},
        ],
    }
    assert run(tmp_path, config, resume=False) == 0
    ledger = tmp_path / "results_hpca_xorflow/complete_suite/unit_campaign/campaign_ledger.csv"
    with ledger.open(newline="") as handle:
        rows = {row["task_id"]: row for row in csv.DictReader(handle)}
    assert rows["good"]["status"] == "SUCCEEDED"
    assert rows["bad"]["status"] == "FAILED"
    assert rows["blocked"]["status"] == "SKIPPED"


def test_trained_workload_dataset_mapping_is_model_agnostic() -> None:
    assert _workload_dataset("ogbn_arxiv_graphsage8_w128_s7") == ("ogbn-arxiv", "OGBN-Arxiv")
    assert _workload_dataset("citeseer_deepres8_w128_s7") == ("CiteSeer", "CiteSeer")
