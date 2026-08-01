"""Regression tests for the reviewer appendix's accounting contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "generate_appendix_suite", ROOT / "scripts" / "generate_appendix_suite.py"
)
assert SPEC and SPEC.loader
APPENDIX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(APPENDIX)


def test_retention_hit_rate_excludes_fallback_targets() -> None:
    rows = pd.DataFrame([
        {"layer": 0, "tile": 0, "slice": 0, "pair_id": 0, "role": "anchor",
         "chosen_format": "A2", "input_support_bits": 128, "padded_bytes": 64,
         "anchor_source_bytes": 64},
        {"layer": 1, "tile": 0, "slice": 0, "pair_id": 0, "role": "target",
         "chosen_format": "BEICSR", "input_support_bits": 128, "padded_bytes": 64,
         "anchor_source_bytes": 64},
        {"layer": 2, "tile": 0, "slice": 0, "pair_id": 1, "role": "anchor",
         "chosen_format": "A2", "input_support_bits": 128, "padded_bytes": 64,
         "anchor_source_bytes": 64},
        {"layer": 3, "tile": 0, "slice": 0, "pair_id": 1, "role": "target",
         "chosen_format": "DELTA", "input_support_bits": 128, "padded_bytes": 64,
         "anchor_source_bytes": 64},
    ])
    result = APPENDIX._retention(rows, 64)
    assert result["fallback_targets"] == 1
    assert result["delta_targets"] == 1
    assert result["delta_anchor_hits"] == 1
    assert result["delta_anchor_hit_rate"] == 1.0


def test_generated_appendix_is_complete_and_explicit_about_missing_cells() -> None:
    output = ROOT / "results_hpca_xorflow" / "appendix"
    for number in range(1, 13):
        assert list((output / "figures").glob(f"A{number}_*.png"))
        assert list((output / "figures").glob(f"A{number}_*.pdf"))
    retention = pd.read_csv(output / "tables" / "A6_anchor_retention_capacity.csv")
    assert set(retention.capacity_kib) == {16, 64, 256, 1024, 4096, 16384}
    assert retention.loc[retention.capacity_kib != 16, "corrected_speedup"].isna().all()
    assert (retention.delta_anchor_hits + retention.delta_anchor_recoveries == retention.delta_targets).all()
    parity = pd.read_csv(output / "tables" / "A5_event_recurrence_parity.csv")
    assert parity["pass"].all()
    assert parity.relative_error.max() == 0.0

