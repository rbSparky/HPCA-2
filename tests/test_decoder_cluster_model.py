from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from xorflow.decoder_sim import _conflict_metrics, simulate
from xorflow.online_replay import replay_trace


def test_conflict_accounting_known_banks() -> None:
    # Events in words 0, 2, 4, 6 all map to bank zero with two banks.
    events = np.asarray([0, 128, 256, 384], dtype=np.int64)
    conflicts, collisions, merged, cycles = _conflict_metrics(events, banks=2)
    assert conflicts == 3
    assert collisions == 0
    assert merged == 0
    assert cycles == 4


def test_decoder_cluster_exact_stream_replay(tmp_path: Path) -> None:
    rng = np.random.default_rng(7)
    supports = rng.random((4, 32, 128)) < 0.3
    trace = tmp_path / "trace.npz"
    np.savez_compressed(trace, packed=np.packbits(supports, axis=2), shape=np.asarray(supports.shape))
    replay = tmp_path / "replay"
    replay_trace(trace_path=trace, output=replay, run_id="tiny", dataset="tiny", model="tiny", seed=7, tile_rows=16, slice_width=96)
    records = next(replay.glob("support_records_*.csv"))
    result, conflicts = simulate(records, tmp_path / "decoder", stream_root=replay, banks=16, lanes=8, clusters=4)
    assert result["records"] == len(conflicts)
    assert result["total_cycles"] > 0
    assert all(row["exact_decode_pass"] for row in conflicts)
    assert result["lane_utilization"] <= 1.0


def test_more_banks_do_not_increase_reference_conflicts() -> None:
    events = np.arange(0, 4096, 37, dtype=np.int64)
    c8 = _conflict_metrics(events, banks=8)[0]
    c16 = _conflict_metrics(events, banks=16)[0]
    c32 = _conflict_metrics(events, banks=32)[0]
    assert c32 <= c16 <= c8
