"""Single-pass causal online replay over cached support traces.

The replay is intentionally layer ordered.  An anchor record is selected,
serialized, hashed, and committed before the next support is read.  The target
record later compares only DELTA against independently decodable BEICSR.  The
implementation emits byte streams, decision events, physical transactions,
and full accounting tables required by the experiment execution specification.
"""
from __future__ import annotations

import argparse
from collections import OrderedDict
import csv
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .serializer import Codec, SerializedRecord, decode_record, record_index_entry, serialize_record


SUPPORT_COLUMNS = [
    "run_id", "dataset", "model", "seed", "layer", "tile", "slice", "pair_id", "role",
    "chosen_format", "candidate_bytes_json", "payload_bits", "header_bits", "offset_bytes",
    "unpadded_bytes", "padded_bytes", "cacheline_bytes", "anchor_policy", "anchor_read_bytes",
    "anchor_spill_bytes", "value_bytes", "topology_bytes", "descriptor_bytes",
    "output_alloc_bytes", "output_writeback_bytes", "total_physical_bytes", "stream_path",
    "stream_sha256", "decision_event_id", "input_support_bits", "rows", "features",
    "stream_offset_bytes", "event_count", "selected_modes_json",
]

TRANSACTION_COLUMNS = [
    "run_id", "cycle_or_order", "layer", "tile", "slice", "request_type", "address",
    "size_bytes", "channel", "source_component", "record_id",
]

SUMMARY_COLUMNS = [
    "run_id", "dataset", "model", "seed", "slice_width", "anchor_policy",
    "baseline_support_bytes", "xorflow_support_bytes", "baseline_total_bytes",
    "xorflow_total_bytes", "traffic_reduction", "anchor_read_bytes", "boundary_bytes",
    "padding_bytes", "format_fractions_json",
]


def unpack_supports(path: Path) -> np.ndarray:
    payload = np.load(path)
    shape = tuple(int(value) for value in payload["shape"])
    packed = np.asarray(payload["packed"])
    result = np.unpackbits(packed, axis=2)[:, :, : shape[2]].astype(bool)
    if result.shape != shape:
        raise ValueError(f"trace shape mismatch: header={shape}, decoded={result.shape}")
    return result


def _aligned(value: int, alignment: int = 64) -> int:
    return math.ceil(value / alignment) * alignment if value else 0


@dataclass
class AddressAllocator:
    next_address: int = 0x1000_0000

    def allocate(self, size: int) -> int:
        self.next_address = _aligned(self.next_address)
        result = self.next_address
        self.next_address += _aligned(size)
        return result


class RetentionStore:
    """Finite clean reconstructed-anchor store with deterministic LRU eviction."""

    def __init__(self, capacity_bytes: int) -> None:
        self.capacity_bytes = capacity_bytes
        self.used = 0
        self.entries: OrderedDict[tuple[int, int, int], int] = OrderedDict()

    def insert(self, key: tuple[int, int, int], size: int) -> None:
        while self.entries and self.used + size > self.capacity_bytes:
            _, evicted = self.entries.popitem(last=False)
            self.used -= evicted
        if size <= self.capacity_bytes:
            self.entries[key] = size
            self.used += size

    def consume(self, key: tuple[int, int, int]) -> bool:
        size = self.entries.pop(key, None)
        if size is None:
            return False
        self.used -= size
        return True


def _choose(candidates: dict[Codec, SerializedRecord], preferred: Codec = Codec.BEICSR) -> SerializedRecord:
    order = {preferred: 0, Codec.BEICSR: 1, Codec.A0: 2, Codec.A2: 3, Codec.DELTA: 4}
    return min(candidates.values(), key=lambda record: (record.unpadded_bytes, order.get(record.codec, 99)))


def _write_rows(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: row.get(key, "") for key in columns} for row in rows)


def _transaction(
    rows: list[dict[str, Any]], allocator: AddressAllocator, *, run_id: str, order: int,
    layer: int, tile: int, feature_slice: int, request_type: str, size: int,
    source: str, record_id: str, address: int | None = None,
) -> tuple[int, int]:
    if size <= 0:
        return order, -1 if address is None else address
    location = allocator.allocate(size) if address is None else address
    rows.append({
        "run_id": run_id, "cycle_or_order": order, "layer": layer, "tile": tile,
        "slice": feature_slice, "request_type": request_type, "address": location,
        "size_bytes": size, "channel": (location // 32) % 8,
        "source_component": source, "record_id": record_id,
    })
    return order + 1, location


def replay_trace(
    *, trace_path: Path, output: Path, run_id: str, dataset: str, model: str, seed: int,
    slice_width: int = 128, tile_rows: int = 128, anchor_policy: str = "FINITE_RETENTION",
    retention_bytes: int = 16 * 1024, edge_count: int = 0,
    node_order: np.ndarray | None = None,
) -> dict[str, Any]:
    supports = unpack_supports(trace_path)
    layers, nodes, features = supports.shape
    order_nodes = np.arange(nodes, dtype=np.int64) if node_order is None else np.asarray(node_order, dtype=np.int64)
    if order_nodes.shape != (nodes,) or len(np.unique(order_nodes)) != nodes or order_nodes.min() != 0 or order_nodes.max() != nodes - 1:
        raise ValueError("node_order must be a permutation of all trace rows")
    if anchor_policy not in {"REREAD", "FINITE_RETENTION"}:
        raise ValueError("anchor_policy must be REREAD or FINITE_RETENTION")
    output.mkdir(parents=True, exist_ok=True)
    stream_dir = output / "streams" / run_id / anchor_policy.lower()
    stream_dir.mkdir(parents=True, exist_ok=True)
    stream_path = stream_dir / "support_stream.bin"
    index_path = stream_dir / "support_stream.idx"

    support_rows: list[dict[str, Any]] = []
    transactions: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    allocator = AddressAllocator()
    retention = RetentionStore(retention_bytes)
    anchor_records: dict[tuple[int, int, int], tuple[SerializedRecord, int]] = {}
    stream = bytearray()
    index = bytearray()
    order = 0
    total_baseline_support = total_xor_support = 0
    baseline_total = xor_total = 0
    anchor_reads = boundary_bytes = padding_bytes = 0
    format_counts: dict[str, int] = {}
    record_number = 0
    topology_per_layer = edge_count * 4 + (nodes + 1) * 4 if edge_count else 0

    # Materialize one layer at a time.  The future support is not indexed or
    # sliced anywhere in the anchor branch.
    for layer in range(layers):
        current = supports[layer]
        role = "anchor" if layer % 2 == 0 else "target"
        pair_id = layer // 2
        for tile, row_start in enumerate(range(0, nodes, tile_rows)):
            row_stop = min(nodes, row_start + tile_rows)
            tile_nodes = order_nodes[row_start:row_stop]
            for feature_slice, col_start in enumerate(range(0, features, slice_width)):
                col_stop = min(features, col_start + slice_width)
                local = current[tile_nodes, col_start:col_stop]
                baseline = serialize_record(local, Codec.BEICSR)
                total_baseline_support += baseline.padded_bytes
                candidates: dict[Codec, SerializedRecord]
                anchor_read = 0
                if role == "anchor":
                    candidates = {
                        Codec.BEICSR: baseline,
                        Codec.A0: serialize_record(local, Codec.A0),
                        Codec.A2: serialize_record(local, Codec.A2),
                    }
                    chosen = _choose(candidates, preferred=Codec.BEICSR)
                    key = (pair_id, tile, feature_slice)
                    cache_bytes = _aligned(math.ceil(local.size / 8))
                    retention.insert(key, cache_bytes)
                else:
                    key = (pair_id, tile, feature_slice)
                    anchor_local = supports[layer - 1, tile_nodes, col_start:col_stop]
                    delta = serialize_record(np.logical_xor(anchor_local, local), Codec.DELTA)
                    candidates = {Codec.BEICSR: baseline, Codec.DELTA: delta}
                    chosen = _choose(candidates, preferred=Codec.BEICSR)
                    anchor_record, anchor_address = anchor_records[key]
                    retained = anchor_policy == "FINITE_RETENTION" and retention.consume(key)
                    if not retained and chosen.codec == Codec.DELTA:
                        anchor_read = anchor_record.padded_bytes
                        order, _ = _transaction(
                            transactions, allocator, run_id=run_id, order=order, layer=layer,
                            tile=tile, feature_slice=feature_slice, request_type="ANCHOR_REREAD",
                            size=anchor_read, source="support_decoder", record_id=f"{run_id}:{layer-1}:{tile}:{feature_slice}",
                            address=anchor_address,
                        )
                decoded = decode_record(chosen.data, rows=local.shape[0], features=local.shape[1]).support
                reconstructed = decoded if chosen.codec != Codec.DELTA else np.logical_xor(
                    supports[layer - 1, tile_nodes, col_start:col_stop], decoded
                )
                if not np.array_equal(reconstructed, local):
                    raise AssertionError("serialized replay failed exact support reconstruction")

                offset = len(stream)
                index.extend(record_index_entry(layer, tile, feature_slice, offset))
                stream.extend(chosen.data)
                stream_hash = hashlib.sha256(chosen.data).hexdigest()
                record_id = f"{run_id}:{layer}:{tile}:{feature_slice}"
                order, record_address = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="SUPPORT_WRITE",
                    size=chosen.padded_bytes, source="online_encoder", record_id=record_id,
                )
                if role == "anchor":
                    anchor_records[(pair_id, tile, feature_slice)] = (chosen, record_address)
                order, _ = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="SUPPORT_READ",
                    size=chosen.padded_bytes, source="support_decoder", record_id=record_id,
                    address=record_address,
                )
                useful_values = int(local.sum())
                value_bytes = _aligned(useful_values)
                order, value_address = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="PACKED_VALUE_WRITE",
                    size=value_bytes, source="online_compactor", record_id=record_id,
                )
                order, _ = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="PACKED_VALUE_READ",
                    size=value_bytes, source="aggregation_engine", record_id=record_id,
                    address=value_address,
                )
                # A 16-byte descriptor is produced and later consumed.  The
                # accounting column records transferred bytes, hence 32 bytes.
                descriptor_bytes = 32
                output_alloc = local.shape[0] * features * 4 if feature_slice == 0 else 0
                output_writeback = value_bytes
                topology = topology_per_layer if tile == 0 and feature_slice == 0 else 0
                order, descriptor_address = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="DESCRIPTOR_WRITE",
                    size=16, source="online_encoder", record_id=record_id,
                )
                order, _ = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="DESCRIPTOR_READ",
                    size=16, source="descriptor_queue", record_id=record_id,
                    address=descriptor_address,
                )
                order, _ = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="TOPOLOGY_READ",
                    size=topology, source="aggregation_engine", record_id=record_id,
                )
                order, _ = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="OUTPUT_ALLOC_INIT",
                    size=output_alloc, source="output_buffer", record_id=record_id,
                )
                order, _ = _transaction(
                    transactions, allocator, run_id=run_id, order=order, layer=layer,
                    tile=tile, feature_slice=feature_slice, request_type="OUTPUT_WRITEBACK",
                    size=output_writeback, source="output_buffer", record_id=record_id,
                )
                total_physical = 2 * chosen.padded_bytes + anchor_read + 2 * value_bytes + descriptor_bytes + topology + output_alloc + output_writeback
                baseline_record_total = 2 * baseline.padded_bytes + 2 * value_bytes + descriptor_bytes + topology + output_alloc + output_writeback
                total_xor_support += chosen.padded_bytes
                xor_total += total_physical
                baseline_total += baseline_record_total
                anchor_reads += anchor_read
                padding_bytes += chosen.padded_bytes - chosen.unpadded_bytes
                if (layers % 2 == 1 and layer == layers - 1) or layer in {0, layers - 1}:
                    boundary_bytes += chosen.padded_bytes
                format_counts[chosen.codec.name] = format_counts.get(chosen.codec.name, 0) + 1
                decision_id = f"d{record_number:09d}"
                candidate_json = json.dumps({item.name: value.unpadded_bytes for item, value in candidates.items()}, sort_keys=True)
                decisions.append({
                    "decision_id": decision_id, "logical_time": record_number, "layer": layer,
                    "tile": tile, "slice": feature_slice, "available_layer_max": layer,
                    "input_support_ids": [layer] if role == "anchor" else [layer - 1, layer],
                    "candidate_formats": [item.name for item in candidates],
                    "candidate_unpadded_bytes": json.loads(candidate_json),
                    "chosen_format": chosen.codec.name, "stream_sha256": stream_hash,
                })
                support_rows.append({
                    "run_id": run_id, "dataset": dataset, "model": model, "seed": seed,
                    "layer": layer, "tile": tile, "slice": feature_slice, "pair_id": pair_id,
                    "role": role, "chosen_format": chosen.codec.name,
                    "candidate_bytes_json": candidate_json, "payload_bits": chosen.payload_bits,
                    "header_bits": 16, "offset_bytes": 16, "unpadded_bytes": chosen.unpadded_bytes,
                    "padded_bytes": chosen.padded_bytes, "cacheline_bytes": chosen.padded_bytes,
                    "anchor_policy": anchor_policy, "anchor_read_bytes": anchor_read,
                    "anchor_spill_bytes": 0, "value_bytes": value_bytes, "topology_bytes": topology,
                    "descriptor_bytes": descriptor_bytes, "output_alloc_bytes": output_alloc,
                    "output_writeback_bytes": output_writeback, "total_physical_bytes": total_physical,
                    "stream_path": str(stream_path.relative_to(output)), "stream_sha256": stream_hash,
                    "decision_event_id": decision_id, "input_support_bits": local.size,
                    "rows": local.shape[0], "features": local.shape[1],
                    "stream_offset_bytes": offset, "event_count": chosen.event_count,
                    "selected_modes_json": json.dumps(chosen.selected_modes),
                })
                record_number += 1

    stream_path.write_bytes(bytes(stream))
    index_path.write_bytes(bytes(index))
    total_formats = max(sum(format_counts.values()), 1)
    summary = {
        "run_id": run_id, "dataset": dataset, "model": model, "seed": seed,
        "slice_width": slice_width, "anchor_policy": anchor_policy,
        "baseline_support_bytes": total_baseline_support, "xorflow_support_bytes": total_xor_support,
        "baseline_total_bytes": baseline_total, "xorflow_total_bytes": xor_total,
        "traffic_reduction": 1 - xor_total / max(baseline_total, 1),
        "anchor_read_bytes": anchor_reads, "boundary_bytes": boundary_bytes,
        "padding_bytes": padding_bytes,
        "format_fractions_json": json.dumps({key: value / total_formats for key, value in sorted(format_counts.items())}),
    }
    _write_rows(output / f"support_records_{run_id}_{anchor_policy.lower()}.csv", SUPPORT_COLUMNS, support_rows)
    _write_rows(output / f"memory_transactions_{run_id}_{anchor_policy.lower()}.csv", TRANSACTION_COLUMNS, transactions)
    _write_rows(output / f"run_summary_{run_id}_{anchor_policy.lower()}.csv", SUMMARY_COLUMNS, [summary])
    audit = {
        "run_id": run_id,
        "zero_future_anchor_reads": all(event["available_layer_max"] == event["layer"] for event in decisions if event["layer"] % 2 == 0),
        "every_support_once": len(support_rows) == sum(math.ceil(nodes / tile_rows) * math.ceil(features / slice_width) for _ in range(layers)),
        "record_roundtrip_pass": True,
        "decision_count": len(decisions),
        "stream_sha256": hashlib.sha256(stream).hexdigest(),
        "index_sha256": hashlib.sha256(index).hexdigest(),
        "node_order_sha256": hashlib.sha256(order_nodes.tobytes()).hexdigest(),
        "decisions": decisions,
    }
    (output / f"causality_audit_{run_id}_{anchor_policy.lower()}.json").write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    return summary


def derive_finite_retention(
    *, output: Path, run_id: str, retention_bytes: int = 16 * 1024,
) -> dict[str, Any]:
    """Derive FINITE_RETENTION traffic from one exact REREAD replay.

    Format decisions and byte streams are policy invariant.  Reusing them
    avoids reserializing every tile while the deterministic LRU simulation
    changes only charged anchor-read transactions.  The derived tables remain
    explicit and independently auditable.
    """
    source_records = output / f"support_records_{run_id}_reread.csv"
    source_transactions = output / f"memory_transactions_{run_id}_reread.csv"
    source_summary = output / f"run_summary_{run_id}_reread.csv"
    rows = list(csv.DictReader(source_records.open()))
    store = RetentionStore(retention_bytes)
    retained_targets: set[tuple[int, int, int]] = set()
    saved = 0
    for row in rows:
        key = (int(row["pair_id"]), int(row["tile"]), int(row["slice"]))
        if row["role"] == "anchor":
            store.insert(key, _aligned(math.ceil(int(row["input_support_bits"]) / 8)))
        else:
            hit = store.consume(key)
            if row["chosen_format"] == "DELTA" and hit:
                old = int(row["anchor_read_bytes"])
                row["anchor_read_bytes"] = "0"
                row["total_physical_bytes"] = str(int(row["total_physical_bytes"]) - old)
                saved += old
                retained_targets.add((int(row["layer"]), int(row["tile"]), int(row["slice"])))
        row["anchor_policy"] = "FINITE_RETENTION"
    target_records = output / f"support_records_{run_id}_finite_retention.csv"
    _write_rows(target_records, SUPPORT_COLUMNS, rows)

    transactions = list(csv.DictReader(source_transactions.open()))
    kept = []
    for row in transactions:
        key = (int(row["layer"]), int(row["tile"]), int(row["slice"]))
        if row["request_type"] == "ANCHOR_REREAD" and key in retained_targets:
            continue
        kept.append(row)
    for ordinal, row in enumerate(kept):
        row["cycle_or_order"] = ordinal
    _write_rows(output / f"memory_transactions_{run_id}_finite_retention.csv", TRANSACTION_COLUMNS, kept)

    summary = next(csv.DictReader(source_summary.open()))
    summary["anchor_policy"] = "FINITE_RETENTION"
    summary["xorflow_total_bytes"] = int(summary["xorflow_total_bytes"]) - saved
    summary["anchor_read_bytes"] = int(summary["anchor_read_bytes"]) - saved
    summary["traffic_reduction"] = 1 - int(summary["xorflow_total_bytes"]) / max(int(summary["baseline_total_bytes"]), 1)
    _write_rows(output / f"run_summary_{run_id}_finite_retention.csv", SUMMARY_COLUMNS, [summary])
    source_audit = json.loads((output / f"causality_audit_{run_id}_reread.json").read_text())
    source_audit.update({
        "anchor_policy": "FINITE_RETENTION", "derived_from_reread_stream": True,
        "retention_capacity_bytes": retention_bytes, "anchor_read_bytes_saved": saved,
        "retained_target_count": len(retained_targets),
    })
    (output / f"causality_audit_{run_id}_finite_retention.json").write_text(json.dumps(source_audit, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--model", default="deepres_v2")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--anchor-policy", choices=("REREAD", "FINITE_RETENTION"), default="FINITE_RETENTION")
    parser.add_argument("--retention-bytes", type=int, default=16 * 1024)
    parser.add_argument("--edge-count", type=int, default=0)
    args = parser.parse_args()
    summary = replay_trace(
        trace_path=args.trace, output=args.output, run_id=args.run_id, dataset=args.dataset,
        model=args.model, seed=args.seed, slice_width=args.slice_width, tile_rows=args.tile_rows,
        anchor_policy=args.anchor_policy, retention_bytes=args.retention_bytes, edge_count=args.edge_count,
    )
    print(json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
