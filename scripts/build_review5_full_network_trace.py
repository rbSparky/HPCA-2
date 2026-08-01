#!/usr/bin/env python3
"""Emit an exact all-layer XORFLOW HBM trace with consumer anchor rereads.

The layer-pair traces used in the earlier acceptance run intentionally sampled
one pair.  This helper retains every transaction in the cached finite-retention
ledger and appends each exact padded consumer-anchor reread for every pair.  It
does not invent timing: the resulting trace is fed to Ramulator2's fixed
32-byte HBM transaction front end.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--transactions", type=Path, required=True)
    p.add_argument("--lifecycle", type=Path, required=True)
    p.add_argument("--config-id", required=True)
    p.add_argument("--output-trace", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    args = p.parse_args()

    anchors: dict[tuple[int, int, int], int] = {}
    base_requests = reads = writes = base_bytes = 0
    digest = hashlib.sha256()
    rereads: list[tuple[int, int]] = []
    with args.transactions.open(newline="") as source:
        transaction_rows = list(csv.DictReader(source))
    for row in transaction_rows:
        layer = int(row["layer"])
        if layer % 2 == 0 and row["request_type"] in {"SUPPORT_WRITE", "SUPPORT_READ"}:
            anchors.setdefault((layer // 2, int(row["tile"]), int(row["slice"])), int(row["address"]))
    delta_targets = consumer_misses = 0
    with args.lifecycle.open(newline="") as source:
        for row in csv.DictReader(source):
            if row["run_id"] != args.config_id:
                continue
            # Accept either the unified event ledger or the compact augmented
            # per-record ledger.  The latter is sufficient for exact traffic
            # replay and avoids requiring a second huge event file in the
            # handoff.
            if "delta_target" in row:
                is_delta = row["delta_target"].lower() in {"true", "1"}
            else:
                is_delta = row.get("role") == "target" and row.get("chosen_format") == "DELTA"
            if not is_delta:
                continue
            delta_targets += 1
            size = int(row["consumer_anchor_read_bytes"])
            if not size:
                continue
            consumer_misses += 1
            pair = int(row.get("layer_pair", row.get("pair_id", int(row["layer"]) // 2)))
            tile = int(row.get("tile_id", row.get("tile")))
            sid = int(row.get("slice_id", row.get("slice")))
            key = (pair, tile, sid)
            if key not in anchors:
                raise KeyError(f"missing anchor address for pair/tile/slice={key}")
            rereads.append((anchors[key], size))

    args.output_trace.parent.mkdir(parents=True, exist_ok=True)
    with args.output_trace.open("wb", buffering=1 << 20) as target:
        for row in transaction_rows:
            kind = "ST" if ("WRITE" in row["request_type"] or row["request_type"] == "OUTPUT_ALLOC_INIT") else "LD"
            address = int(row["address"]); size = int(row["size_bytes"])
            base_bytes += size
            for offset in range(0, size, 32):
                target.write(f"{kind} 0x{address + offset:x}\n".encode())
                base_requests += 1; reads += kind == "LD"; writes += kind == "ST"
        consumer_bytes = 0; consumer_requests = 0
        for address, size in rereads:
            for offset in range(0, size, 32):
                target.write(f"LD 0x{address + offset:x}\n".encode())
                consumer_requests += 1; consumer_bytes += min(32, size - offset)
        target.flush()
    with args.output_trace.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    payload = {
        "config_id": args.config_id, "scope": "all_layers_full_network",
        "base_transactions": len(transaction_rows), "base_requests": base_requests,
        "base_read_requests": reads, "base_write_requests": writes,
        "base_transaction_bytes": base_bytes, "delta_targets": delta_targets,
        "consumer_misses": consumer_misses, "consumer_anchor_bytes": consumer_bytes,
        "consumer_anchor_requests": consumer_requests,
        "combined_requests": base_requests + consumer_requests,
        "combined_transaction_bytes": (base_requests + consumer_requests) * 32,
        "trace_sha256": digest.hexdigest(), "hbm_transaction_bytes": 32,
        "ordering": "all producer/target stream then exact consumer rereads (conservative)",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
