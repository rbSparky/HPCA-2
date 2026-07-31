"""Regression checks for the reviewer-audit RTL remediation artifacts."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_encoder_engine_is_not_pass_through() -> None:
    source = (ROOT / "rtl" / "xorflow_encoder_pipelined.sv").read_text()
    assert "module xorflow_encoder_tile_engine" in source
    assert "support_word ^ anchor_word" in source
    assert "packed_event_ids" in source
    assert "local_count" in source


def test_decoder_cluster_is_hierarchical_and_routed() -> None:
    source = (ROOT / "rtl" / "xorflow_decoder_cluster_pipelined.sv").read_text()
    assert "module xorflow_decoder_cluster8_debug" in source
    assert "module xorflow_decoder_cluster8_pipelined" in source
    # The physical top intentionally does not expose the wide decoded buses.
    physical = source.split("module xorflow_decoder_cluster8_pipelined", 1)[1]
    assert "output wire [895:0] event_ids" not in physical
    summary_path = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3" / "decoder" / "decoder_cluster_openroad_summary.json"
    summary = json.loads(summary_path.read_text())
    assert summary["status"] == "PASS_ROUTED_OPENROAD_ORFS"
    assert summary["route_drc_errors"] == 0


def test_engine_and_cluster_cosim_pass() -> None:
    for rel in (
        "results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_engine_cosim.log",
        "results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_cosim.log",
    ):
        assert "PASS" in (ROOT / rel).read_text()
