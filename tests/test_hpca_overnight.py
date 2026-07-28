from __future__ import annotations

import json
from pathlib import Path

from mosaic_validation.hpca_overnight import Ledger, Workload, load_config, validity


def _record(path: Path, score: float) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"finite_loss": True, "fp8_fp16_test_micro_f1": score}))
    path.with_name("fp8_supports.npz").write_bytes(b"trace")


def test_borderline_is_report_only_and_index_is_written(tmp_path: Path) -> None:
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs/hpca_overnight.yaml").write_text("""deadline_utc: '2026-07-31T23:59:00Z'\nprogress_weights: {smoke: 20, quality: 15, primary: 25, controls: 15, tools: 15, report: 10}\nworkloads: []\n""")
    _record(tmp_path / "artifacts_hpca_xorflow/workloads/yelp/record.json", .434)
    config = load_config(tmp_path, None)
    status, value, _ = validity(tmp_path, Workload("yelp", "Yelp", "supplementary", "micro_f1", .45, .02))
    assert status == "BORDERLINE" and value == .434
    ledger = Ledger(tmp_path, config)
    ledger.add(stage="quality", item_id="yelp", category="supplementary", status="SUCCEEDED", validity=status, metric="micro_f1", value=value)
    assert "BORDERLINE" in (tmp_path / "results_hpca_xorflow/HPCA_RESULTS_INDEX.md").read_text()
