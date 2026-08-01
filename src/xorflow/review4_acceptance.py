"""Review-4 split producer/consumer anchor accounting and lifecycle traces."""
from __future__ import annotations

import argparse
import csv
import json
import math
from collections import OrderedDict
from pathlib import Path
from typing import Any

import pandas as pd


CAPACITIES = (16 * 1024, 256 * 1024, 1024 * 1024, 4 * 1024 * 1024)
PRIMARY = (
    "flickr_deepres8_w128_s7",
    "ogbn_arxiv_deepres8_w128_s7", "ogbn_arxiv_deepres8_w128_s17", "ogbn_arxiv_deepres8_w128_s27",
    "reddit_deepres8_w128_s7_native", "reddit_deepres8_w128_s17_native", "reddit_deepres8_w128_s27_native",
    "yelp_deepres8_w128_s7_balanced_fallback", "ogbn_arxiv_deepres16_w128_s7", "chameleon_gcnii16",
)


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def _key(row: dict[str, str]) -> tuple[int, int, int]:
    return int(row["pair_id"]), int(row["tile"]), int(row["slice"])


def _id(run_id: str, role: str, key: tuple[int, int, int]) -> str:
    pair, tile, feature_slice = key
    return f"{run_id}:p{pair:03d}:t{tile:06d}:s{feature_slice:03d}:{role}"


def _decoder_rate(root: Path, config: str) -> float:
    path = root / "decoder" / config / "decoder_cluster_trace_b16.csv"
    frame = pd.read_csv(path)
    return float(frame.loc[frame.banks == 16, "achieved_encoded_bits_per_cycle"].iloc[0])


def classify(rows: list[dict[str, str]], capacity: int, rate: float) -> list[dict[str, Any]]:
    anchors = {_key(row): row for row in rows if row["role"] == "anchor"}
    store: OrderedDict[tuple[int, int, int], int] = OrderedDict()
    live = 0
    output: list[dict[str, Any]] = []
    for row in sorted(rows, key=lambda r: (int(r["layer"]), int(r["tile"]), int(r["slice"]))):
        key = _key(row)
        if row["role"] == "anchor":
            entry = math.ceil(int(row["input_support_bits"]) / 8)
            if entry <= capacity:
                while store and live + entry > capacity:
                    _, evicted = store.popitem(last=False); live -= evicted
                store[key] = entry; live += entry
            continue
        anchor = anchors[key]
        is_delta = row["chosen_format"] == "DELTA"
        decoded_bytes = math.ceil(int(anchor["input_support_bits"]) / 8)
        producer_bytes = int(row.get("anchor_read_bytes") or 0) if is_delta else 0
        producer_decode = (
            math.ceil(producer_bytes * 8 / max(rate, 1.0)) + math.ceil(int(anchor["input_support_bits"]) / 2048)
            if producer_bytes else 0
        )
        if not is_delta:
            source = "NOT_REQUIRED_INDEPENDENT_TARGET"; hit = False; consumer_bytes = consumer_decode = 0
        elif key in store:
            source = "CONSUMER_RESIDENT_DECODED"; hit = True; consumer_bytes = consumer_decode = 0
            store.move_to_end(key)
        else:
            source = "MEMORY_REREAD"; hit = False
            consumer_bytes = int(anchor["padded_bytes"])
            consumer_decode = math.ceil(consumer_bytes * 8 / max(rate, 1.0)) + math.ceil(int(anchor["input_support_bits"]) / 2048)
        output.append({
            "run_id": row["run_id"], "dataset": row["dataset"], "seed": int(row["seed"]),
            "layer_pair": int(row["pair_id"]), "tile_id": int(row["tile"]), "slice_id": int(row["slice"]),
            "anchor_record_id": _id(row["run_id"], "anchor", key), "target_record_id": _id(row["run_id"], "target", key),
            "target_format": row["chosen_format"], "consumer_policy": f"decoded_lru_{capacity}",
            "consumer_anchor_source": source, "producer_anchor_buffer_hit": bool(is_delta and producer_bytes == 0),
            "consumer_anchor_buffer_hit": hit, "producer_anchor_read_bytes": producer_bytes,
            "producer_anchor_decode_cycles": producer_decode, "consumer_anchor_read_bytes": consumer_bytes,
            "consumer_anchor_decode_cycles": consumer_decode, "consumer_anchor_buffer_bytes": decoded_bytes if is_delta else 0,
            "consumer_anchor_memory_wait_cycles": math.ceil(consumer_bytes / 32) + (50 if consumer_bytes else 0),
            "consumer_anchor_decoder_wait_cycles": consumer_decode, "consumer_anchor_bank_conflict_cycles": 0,
            "anchor_padded_committed_bytes": int(anchor["padded_bytes"]), "delta_target": is_delta,
        })
    return output


def prepare(project: Path, output: Path, configs: tuple[str, ...], evidence_root: Path | None = None) -> None:
    old = evidence_root.resolve() if evidence_root is not None else project / "results_hpca_xorflow/reviewer_spec_v3"
    per_record: list[dict[str, Any]] = []; summaries: list[dict[str, Any]] = []
    for config in configs:
        source = old / "online_replay" / f"support_records_{config}_finite_retention.csv"
        rows = _read(source); rate = _decoder_rate(old, config)
        policy_rows: dict[int, list[dict[str, Any]]] = {}
        for capacity in CAPACITIES:
            values = classify(rows, capacity, rate); policy_rows[capacity] = values
            delta = [x for x in values if x["delta_target"]]
            counts: dict[str, int] = {}
            for item in delta: counts[item["consumer_anchor_source"]] = counts.get(item["consumer_anchor_source"], 0) + 1
            summaries.append({
                "run_id": config, "capacity_bytes": capacity, "entry_granularity": "decoded_tile_slice_bitmap",
                "replacement_policy": "LRU", "insertion_point": "consumer_anchor_decode_done",
                "release_point": "eviction_or_layer_pair_done", "read_ports": 1, "write_ports": 1,
                "bank_mapping": "record_id_mod_16", "delta_targets": len(delta),
                "resident_decoded": counts.get("CONSUMER_RESIDENT_DECODED", 0), "resident_compressed": 0,
                "concurrent_stream": 0, "memory_reread": counts.get("MEMORY_REREAD", 0),
                "unclassified": len(delta) - sum(counts.values()),
                "consumer_hit_rate": counts.get("CONSUMER_RESIDENT_DECODED", 0) / max(len(delta), 1),
                "consumer_anchor_read_bytes": sum(x["consumer_anchor_read_bytes"] for x in delta),
                "consumer_anchor_decode_cycles": sum(x["consumer_anchor_decode_cycles"] for x in delta),
            })
        principal = policy_rows[16 * 1024]
        per_record.extend(principal)
        augmented = {x["target_record_id"]: x for x in principal}
        for row in rows:
            if row["role"] == "target":
                item = augmented[_id(config, "target", _key(row))]
                row["consumer_anchor_read_bytes"] = str(item["consumer_anchor_read_bytes"])
                row["consumer_anchor_decode_cycles"] = str(item["consumer_anchor_decode_cycles"])
                row["consumer_anchor_source"] = str(item["consumer_anchor_source"])
            else:
                row["consumer_anchor_read_bytes"] = "0"; row["consumer_anchor_decode_cycles"] = "0"
                row["consumer_anchor_source"] = "ANCHOR_RECORD"
        _write(output / "augmented_records" / f"{config}.csv", rows)
    _write(output / "results/anchor_lifecycle_per_record.csv", per_record)
    _write(output / "results/anchor_lifecycle_summary.csv", summaries)


def finalize(output: Path, configs: tuple[str, ...]) -> None:
    records = pd.read_csv(output / "results/anchor_lifecycle_per_record.csv")
    events: list[dict[str, Any]] = []
    for config in configs:
        trace = pd.read_csv(output / "results/final_schedule" / config / "causal_tile_event_trace.csv")
        trace = trace[trace.variant == "XORFLOW_ONLINE"].set_index(["layer", "tile", "slice"])
        local = records[records.run_id == config]
        for item in local.itertuples(index=False):
            anchor_layer = int(item.layer_pair) * 2
            target_layer = anchor_layer + 1
            a = trace.loc[(anchor_layer, int(item.tile_id), int(item.slice_id))]
            t = trace.loc[(target_layer, int(item.tile_id), int(item.slice_id))]
            consumer_extra = int(item.consumer_anchor_memory_wait_cycles + item.consumer_anchor_decode_cycles)
            events.append({
                "run_id": item.run_id, "dataset": item.dataset, "seed": item.seed, "layer_pair": item.layer_pair,
                "tile_id": item.tile_id, "slice_id": item.slice_id, "anchor_record_id": item.anchor_record_id,
                "target_record_id": item.target_record_id, "consumer_anchor_source": item.consumer_anchor_source,
                "anchor_created": int(a.producer_start), "anchor_encode_start": int(a.producer_start),
                "anchor_encode_done": int(a.producer_done), "anchor_write_issue": int(a.writeback_start),
                "anchor_write_complete": int(a.writeback_done), "producer_anchor_buffer_insert": int(a.producer_done),
                "producer_anchor_buffer_hit_or_miss": "HIT" if item.producer_anchor_buffer_hit else "MISS",
                "producer_anchor_eviction": -1,
                "producer_anchor_reread_issue": int(t.producer_anchor_memory_start) if item.producer_anchor_read_bytes else -1,
                "producer_anchor_reread_complete": int(t.producer_anchor_memory_done) if item.producer_anchor_read_bytes else -1,
                "producer_anchor_decode_start": int(t.producer_anchor_decode_start) if item.producer_anchor_decode_cycles else -1,
                "producer_anchor_decode_done": int(t.producer_anchor_decode_done) if item.producer_anchor_decode_cycles else -1,
                "target_xor_start": int(t.producer_start), "target_xor_done": int(t.producer_done),
                "target_encode_start": int(t.producer_start), "target_encode_done": int(t.producer_done),
                "target_write_issue": int(t.writeback_start), "target_write_complete": int(t.writeback_done),
                "producer_anchor_release": int(t.writeback_done),
                "consumer_target_read_issue": int(t.memory_start), "consumer_target_read_complete": int(t.memory_done),
                "consumer_target_descriptor_ready": int(t.memory_done),
                "consumer_target_payload_ready": int(t.memory_done),
                "consumer_anchor_buffer_hit_or_miss": "HIT" if item.consumer_anchor_buffer_hit else ("MISS" if item.delta_target else "NOT_REQUIRED"),
                "consumer_anchor_read_issue": int(t.memory_start) if item.consumer_anchor_read_bytes else -1,
                "consumer_anchor_read_complete": int(t.memory_done) if item.consumer_anchor_read_bytes else -1,
                "consumer_anchor_decode_start": int(t.decode_start) if item.consumer_anchor_decode_cycles else -1,
                "consumer_anchor_decode_done": int(t.decode_start) + int(item.consumer_anchor_decode_cycles) if item.consumer_anchor_decode_cycles else -1,
                "target_delta_decode_start": int(t.decode_start), "target_delta_decode_done": int(t.decode_done),
                "target_reconstruction_start": int(t.decode_start), "target_reconstruction_done": int(t.decode_done),
                "support_cache_write_start": int(t.decode_done), "support_cache_write_done": int(t.aggregation_start),
                "sparse_value_access_ready": int(t.aggregation_start), "aggregation_start": int(t.aggregation_start),
                "aggregation_done": int(t.aggregation_done), "dependency_pass": int(t.aggregation_start) >= int(t.decode_done),
                "producer_dependency_pass": int(t.producer_start) >= int(t.producer_anchor_decode_done) >= int(t.producer_anchor_memory_done),
                "consumer_extra_cycles_charged": consumer_extra,
            })
    _write(output / "events/unified_record_trace.csv", events)


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("mode", choices=("prepare", "finalize"))
    parser.add_argument("--project", type=Path, default=Path.cwd()); parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path)
    parser.add_argument("--configs", nargs="*", default=list(PRIMARY)); args = parser.parse_args()
    if args.mode == "prepare": prepare(args.project.resolve(), args.output.resolve(), tuple(args.configs), args.evidence_root)
    else: finalize(args.output.resolve(), tuple(args.configs))


if __name__ == "__main__": main()
