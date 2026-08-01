#!/usr/bin/env python3
"""Append exact Review-4 consumer-anchor rereads to an emitted HBM trace.

The input trace already contains the producer-complete pair traffic.  This tool
resolves each consumer miss back to the committed anchor address in the online
transaction ledger and appends its exact padded record as 32-byte HBM reads.
Appending is deliberately conservative: the new reads cannot hide behind the
old stream.  Transient traces may be deleted after their manifest/tool hashes
have been retained.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


def _update_copy(source: Path, target, digest, limit: int) -> int:
    count = 0
    with source.open("rb") as handle:
        for line in handle:
            if limit and count >= limit: break
            target.write(line); digest.update(line); count += 1
    return count


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-trace", type=Path, required=True)
    p.add_argument("--transactions", type=Path, required=True)
    p.add_argument("--lifecycle", type=Path, required=True)
    p.add_argument("--config-id", required=True)
    p.add_argument("--pair-id", type=int, default=2)
    p.add_argument("--max-base-requests", type=int, default=0)
    p.add_argument("--max-consumer-requests", type=int, default=0)
    p.add_argument("--output-trace", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    args = p.parse_args()

    anchor_layer = args.pair_id * 2
    addresses: dict[tuple[int, int], int] = {}
    with args.transactions.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if int(row["layer"]) != anchor_layer: continue
            if row["request_type"] not in {"SUPPORT_WRITE", "SUPPORT_READ"}: continue
            addresses.setdefault((int(row["tile"]), int(row["slice"])), int(row["address"]))

    rereads: list[tuple[int, int]] = []
    records = misses = 0
    with args.lifecycle.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["run_id"] != args.config_id or int(row["layer_pair"]) != args.pair_id: continue
            if row["delta_target"].lower() not in {"true", "1"}: continue
            records += 1
            size = int(row["consumer_anchor_read_bytes"])
            if not size: continue
            misses += 1
            key = (int(row["tile_id"]), int(row["slice_id"]))
            if key not in addresses: raise KeyError(f"missing committed anchor address for {key}")
            rereads.append((addresses[key], size))

    args.output_trace.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with args.output_trace.open("wb", buffering=1 << 20) as target:
        base_requests = _update_copy(args.base_trace, target, digest, args.max_base_requests)
        consumer_requests = consumer_bytes = 0
        for address, size in rereads:
            for offset in range(0, size, 32):
                if args.max_consumer_requests and consumer_requests >= args.max_consumer_requests: break
                line = f"LD 0x{address + offset:x}\n".encode()
                target.write(line); digest.update(line); consumer_requests += 1
                consumer_bytes += min(32, size - offset)
            if args.max_consumer_requests and consumer_requests >= args.max_consumer_requests: break
    payload = {
        "config_id": args.config_id, "pair_id": args.pair_id,
        "base_trace": str(args.base_trace), "base_trace_sha256": hashlib.sha256(args.base_trace.read_bytes()).hexdigest() if args.base_trace.stat().st_size < 1 << 30 else "recorded_separately_large_file",
        "base_requests": base_requests, "base_request_limit": args.max_base_requests,
        "consumer_request_limit": args.max_consumer_requests,
        "delta_targets": records, "consumer_misses": misses,
        "consumer_anchor_bytes": consumer_bytes, "consumer_anchor_requests": consumer_requests,
        "combined_requests": base_requests + consumer_requests,
        "transaction_bytes": (base_requests + consumer_requests) * 32,
        "output_trace": str(args.output_trace), "trace_sha256": digest.hexdigest(),
        "ordering": "base_stream_then_consumer_rereads_conservative_serial",
        "all_consumer_addresses_resolved": True, "hbm_transaction_bytes": 32,
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__": main()
