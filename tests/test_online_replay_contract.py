from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

from xorflow.online_replay import derive_finite_retention, replay_trace


def _trace(path: Path, supports: np.ndarray) -> None:
    np.savez_compressed(path, packed=np.packbits(supports, axis=2), shape=np.asarray(supports.shape))


def test_online_anchor_decision_is_future_independent(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    supports = rng.random((3, 19, 96)) < 0.35
    first = tmp_path / "a.npz"
    second = tmp_path / "b.npz"
    _trace(first, supports)
    mutated = supports.copy()
    mutated[1:] = rng.random(mutated[1:].shape) < 0.8
    _trace(second, mutated)
    out_a = tmp_path / "out_a"
    out_b = tmp_path / "out_b"
    replay_trace(trace_path=first, output=out_a, run_id="a", dataset="tiny", model="tiny", seed=7, slice_width=64, tile_rows=8)
    replay_trace(trace_path=second, output=out_b, run_id="b", dataset="tiny", model="tiny", seed=7, slice_width=64, tile_rows=8)
    a = json.loads(next(out_a.glob("causality_audit_*.json")).read_text())
    b = json.loads(next(out_b.glob("causality_audit_*.json")).read_text())
    a_anchor = [(d["layer"], d["tile"], d["slice"], d["chosen_format"], d["stream_sha256"]) for d in a["decisions"] if d["layer"] == 0]
    b_anchor = [(d["layer"], d["tile"], d["slice"], d["chosen_format"], d["stream_sha256"]) for d in b["decisions"] if d["layer"] == 0]
    assert a_anchor == b_anchor


def test_every_support_committed_once_and_boundary_charged(tmp_path: Path) -> None:
    rng = np.random.default_rng(9)
    supports = rng.random((5, 17, 128)) < 0.5
    trace = tmp_path / "trace.npz"
    _trace(trace, supports)
    out = tmp_path / "out"
    summary = replay_trace(trace_path=trace, output=out, run_id="tiny", dataset="tiny", model="tiny", seed=7, slice_width=96, tile_rows=8, edge_count=20)
    rows = list(csv.DictReader(next(out.glob("support_records_*.csv")).open()))
    expected = 5 * 3 * 2
    assert len(rows) == expected
    assert summary["boundary_bytes"] > 0
    assert all(int(row["total_physical_bytes"]) > 0 for row in rows)
    audit = json.loads(next(out.glob("causality_audit_*.json")).read_text())
    assert audit["zero_future_anchor_reads"]
    assert audit["every_support_once"]
    transactions = list(csv.DictReader(next(out.glob("memory_transactions_*.csv")).open()))
    assert sum(int(row["size_bytes"]) for row in transactions) == int(summary["xorflow_total_bytes"])
    assert {
        "SUPPORT_WRITE", "SUPPORT_READ", "PACKED_VALUE_WRITE", "PACKED_VALUE_READ",
        "DESCRIPTOR_WRITE", "DESCRIPTOR_READ", "TOPOLOGY_READ",
        "OUTPUT_ALLOC_INIT", "OUTPUT_WRITEBACK",
    }.issubset({row["request_type"] for row in transactions})


def test_reread_charges_no_less_anchor_traffic(tmp_path: Path) -> None:
    rng = np.random.default_rng(13)
    supports = rng.random((4, 64, 128)) < 0.25
    trace = tmp_path / "trace.npz"
    _trace(trace, supports)
    finite = replay_trace(trace_path=trace, output=tmp_path / "finite", run_id="finite", dataset="tiny", model="tiny", seed=7, anchor_policy="FINITE_RETENTION", retention_bytes=16384)
    reread = replay_trace(trace_path=trace, output=tmp_path / "reread", run_id="reread", dataset="tiny", model="tiny", seed=7, anchor_policy="REREAD")
    assert reread["anchor_read_bytes"] >= finite["anchor_read_bytes"]


def test_derived_finite_policy_matches_direct_replay(tmp_path: Path) -> None:
    rng = np.random.default_rng(23)
    supports = rng.random((4, 64, 128)) < 0.2
    trace = tmp_path / "trace.npz"; _trace(trace, supports)
    shared = tmp_path / "shared"
    replay_trace(trace_path=trace, output=shared, run_id="same", dataset="tiny", model="tiny", seed=7, anchor_policy="REREAD")
    derived = derive_finite_retention(output=shared, run_id="same", retention_bytes=16384)
    direct = replay_trace(trace_path=trace, output=tmp_path / "direct", run_id="direct", dataset="tiny", model="tiny", seed=7, anchor_policy="FINITE_RETENTION", retention_bytes=16384)
    for field in ("baseline_support_bytes", "xorflow_support_bytes", "baseline_total_bytes", "xorflow_total_bytes", "anchor_read_bytes"):
        assert int(derived[field]) == int(direct[field])
    transactions = list(csv.DictReader((shared / "memory_transactions_same_finite_retention.csv").open()))
    assert sum(int(row["size_bytes"]) for row in transactions) == int(derived["xorflow_total_bytes"])
