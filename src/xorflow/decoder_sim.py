"""Integrated finite-queue decoder cluster and banked support-cache model."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any

import numpy as np

from .serializer import COHORT_ROWS, Codec, decode_record


TRACE_COLUMNS = [
    "run_id", "banks", "lanes", "clusters", "records", "input_bits", "support_bits",
    "total_cycles", "achieved_encoded_bits_per_cycle", "achieved_support_bits_per_cycle",
    "records_per_cycle", "tiles_per_cycle", "mean_latency", "p95_latency", "max_latency",
    "lane_utilization", "lane_imbalance", "distributor_stalls", "max_input_fifo",
    "bank_conflicts", "same_word_collisions", "merged_writes", "sram_port_utilization",
    "builder_cycles", "row_prefix_cycles", "downstream_backpressure_cycles",
    "max_support_ready_cycles", "critical_path_extension_cycles",
]

CONFLICT_COLUMNS = [
    "run_id", "record_id", "banks", "events", "bank_conflicts", "same_word_collisions",
    "merged_writes", "builder_cycles", "exact_decode_pass",
]


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    values = sorted(values); position = fraction * (len(values) - 1)
    lo = int(position); hi = min(lo + 1, len(values) - 1); alpha = position - lo
    return values[lo] * (1 - alpha) + values[hi] * alpha


def _record_bytes(row: dict[str, str], stream_root: Path, cache: dict[Path, bytes]) -> bytes:
    stream = stream_root / row["stream_path"]
    offset = int(row["stream_offset_bytes"])
    length = int(row["padded_bytes"])
    if stream not in cache:
        cache[stream] = stream.read_bytes()
    data = cache[stream][offset:offset + length]
    if len(data) != length:
        raise ValueError(f"truncated record at {stream}:{offset}")
    return data


def _conflict_metrics(events: np.ndarray, banks: int, issue_events: int = 8) -> tuple[int, int, int, int]:
    event_ids = np.asarray(events, dtype=np.int64)
    if event_ids.size == 0:
        return 0, 0, 0, 0
    bursts = math.ceil(len(event_ids) / issue_events)
    padded = np.full(bursts * issue_events, -1, dtype=np.int64); padded[:len(event_ids)] = event_ids
    words = (padded.reshape(bursts, issue_events) // 64)
    valid = words >= 0
    bank_ids = np.where(valid, words % banks, banks)
    sentinel = np.iinfo(np.int64).max
    word_sorted = np.sort(np.where(valid, words, sentinel), axis=1)
    sorted_valid = word_sorted != sentinel
    is_new_word = sorted_valid.copy()
    is_new_word[:, 1:] &= word_sorted[:, 1:] != word_sorted[:, :-1]
    unique_bank_ids = np.where(is_new_word, word_sorted % banks, banks)
    counts = (unique_bank_ids[:, :, None] == np.arange(banks)[None, None, :]).sum(axis=1)
    valid_count = valid.sum(axis=1)
    word_unique = is_new_word.sum(axis=1)
    bank_unique = (counts > 0).sum(axis=1)
    collisions = int((valid_count - word_unique).sum())
    conflicts = int((word_unique - bank_unique).sum())
    cycles = int(counts.max(axis=1).sum())
    return conflicts, collisions, collisions, cycles


def _builder_work(codec: Codec, support: np.ndarray, modes: list[str], banks: int, lanes: int = 8) -> tuple[int, int, int, int]:
    """Return exact scatter conflicts plus conservative dense-word writes.

    BEICSR and per-row DENSE payloads are bitmap word streams, not thousands of
    independent set events.  A2 first broadcasts each cohort prototype into
    its rows and then scatters only XOR residuals.  This distinction is
    essential to avoid charging a bitmap decoder as an event-list decoder.
    """
    rows, features = support.shape
    dense_words = 0
    if codec == Codec.BEICSR:
        return 0, 0, 0, math.ceil(rows * features / 64 / banks)
    if codec == Codec.DELTA:
        mode = modes[0] if modes else "IDS"
        if mode == "DENSE":
            # One read-XOR-write operation per support word.
            return 0, 0, 0, 2 * math.ceil(rows * features / 64 / banks)
        events = np.flatnonzero(support.reshape(-1))
        issue_events = lanes * (8 if mode == "GAP8" else max(1, 64 // math.ceil(math.log2(rows * features))))
    elif codec == Codec.A0:
        event_parts = []
        for row, mode in enumerate(modes):
            if mode == "DENSE":
                dense_words += math.ceil(features / 64)
            else:
                event_parts.append(row * features + np.flatnonzero(support[row]))
        events = np.concatenate(event_parts) if event_parts else np.empty(0, dtype=np.int64)
    else:
        residual_parts = []
        for start in range(0, rows, COHORT_ROWS):
            cohort = support[start:start + COHORT_ROWS]
            prototype = cohort.sum(axis=0, dtype=np.int16) > (len(cohort) / 2)
            dense_words += len(cohort) * math.ceil(features / 64)
            for local_row, row in enumerate(cohort):
                residual_parts.append((start + local_row) * features + np.flatnonzero(np.logical_xor(row, prototype)))
        events = np.concatenate(residual_parts) if residual_parts else np.empty(0, dtype=np.int64)
    if codec != Codec.DELTA:
        issue_events = lanes * 4
    conflicts, collisions, merged, scatter = _conflict_metrics(events, banks, issue_events=issue_events)
    return conflicts, collisions, merged, scatter + math.ceil(dense_words / banks)


def simulate(
    records_path: Path, output_dir: Path, *, stream_root: Path, banks: int = 16,
    lanes: int = 8, clusters: int = 4, input_fifo_depth: int = 4,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = list(csv.DictReader(records_path.open()))
    if not rows:
        raise ValueError("empty support-record table")
    lane_free = [0] * (lanes * clusters)
    builder_free = [0] * clusters
    prefix_free = [0] * clusters
    lane_busy = [0] * (lanes * clusters)
    latencies: list[int] = []
    conflicts_out: list[dict[str, Any]] = []
    total_input = total_support = total_conflicts = total_collisions = total_merged = 0
    builder_total = prefix_total = distributor_stalls = downstream = 0
    arrival = 0; max_fifo = 0; max_ready = 0
    stream_cache: dict[Path, bytes] = {}
    for ordinal, row in enumerate(rows):
        data = _record_bytes(row, stream_root, stream_cache)
        r = int(row["rows"]); c = int(row["features"])
        decoded = decode_record(data, rows=r, features=c)
        codec = Codec[row["chosen_format"]]
        # DELTA records scatter only toggles; other records reconstruct their
        # complete support state (dense records are handled as word writes).
        events = np.flatnonzero(decoded.support.reshape(-1))
        exact = decoded.consumed_bytes == len(data)
        modes = json.loads(row.get("selected_modes_json") or "[]")
        conflict, collision, merged, builder = _builder_work(codec, decoded.support, modes, banks, lanes=lanes)
        parse_cycles = math.ceil(len(data) * 8 / 64)
        prefix = math.ceil(r / lanes)
        lane = min(range(len(lane_free)), key=lambda index: (lane_free[index], index))
        queued = sum(1 for value in lane_free if value > arrival)
        max_fifo = max(max_fifo, min(queued, input_fifo_depth * lanes * clusters))
        start = max(arrival, lane_free[lane])
        if queued >= input_fifo_depth * lanes * clusters and start > arrival:
            distributor_stalls += start - arrival
            arrival = start
        parse_ready = start + parse_cycles
        lane_free[lane] = parse_ready; lane_busy[lane] += parse_cycles
        cluster = lane // lanes
        builder_start = max(parse_ready, builder_free[cluster])
        builder_ready = builder_start + builder
        builder_free[cluster] = builder_ready
        prefix_start = max(builder_ready, prefix_free[cluster])
        ready = prefix_start + prefix
        prefix_free[cluster] = ready
        latencies.append(ready - arrival); max_ready = max(max_ready, ready - arrival)
        arrival += 1
        total_input += len(data) * 8; total_support += r * c
        total_conflicts += conflict; total_collisions += collision; total_merged += merged
        builder_total += builder; prefix_total += prefix
        record_id = f"{row['run_id']}:{row['layer']}:{row['tile']}:{row['slice']}"
        conflicts_out.append({
            "run_id": row["run_id"], "record_id": record_id, "banks": banks,
            "events": int(row.get("event_count") or len(events)), "bank_conflicts": conflict,
            "same_word_collisions": collision, "merged_writes": merged,
            "builder_cycles": builder, "exact_decode_pass": exact,
        })
    total_cycles = max(max(prefix_free), 1)
    mean_busy = statistics.fmean(lane_busy)
    result = {
        "run_id": rows[0]["run_id"], "banks": banks, "lanes": lanes, "clusters": clusters,
        "records": len(rows), "input_bits": total_input, "support_bits": total_support,
        "total_cycles": total_cycles, "achieved_encoded_bits_per_cycle": total_input / total_cycles,
        "achieved_support_bits_per_cycle": total_support / total_cycles,
        "records_per_cycle": len(rows) / total_cycles, "tiles_per_cycle": len(rows) / total_cycles,
        "mean_latency": statistics.fmean(latencies), "p95_latency": _percentile(latencies, .95),
        "max_latency": max(latencies), "lane_utilization": sum(lane_busy) / (total_cycles * len(lane_busy)),
        "lane_imbalance": max(lane_busy) / max(mean_busy, 1), "distributor_stalls": distributor_stalls,
        "max_input_fifo": max_fifo, "bank_conflicts": total_conflicts,
        "same_word_collisions": total_collisions, "merged_writes": total_merged,
        "sram_port_utilization": builder_total / max(total_cycles * clusters, 1),
        "builder_cycles": builder_total, "row_prefix_cycles": prefix_total,
        "downstream_backpressure_cycles": downstream, "max_support_ready_cycles": max_ready,
        "critical_path_extension_cycles": max(0, total_cycles - len(rows)),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    return result, conflicts_out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--stream-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--banks", type=int, default=16)
    parser.add_argument("--lanes", type=int, default=8)
    parser.add_argument("--clusters", type=int, default=4)
    args = parser.parse_args()
    result, conflicts = simulate(args.records, args.output_dir, stream_root=args.stream_root, banks=args.banks, lanes=args.lanes, clusters=args.clusters)
    trace_path = args.output_dir / f"decoder_cluster_trace_b{args.banks}.csv"
    with trace_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRACE_COLUMNS); writer.writeheader(); writer.writerow(result)
    conflict_path = args.output_dir / f"conflicts_b{args.banks}.csv"
    with conflict_path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CONFLICT_COLUMNS); writer.writeheader(); writer.writerows(conflicts)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
