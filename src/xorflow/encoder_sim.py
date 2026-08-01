"""Finite-queue cycle model for the online support encoder.

The model exposes every bounded resource and returns achieved, rather than
peak, rates to the unified schedule.  It preserves the serializer bytes and
hashes exactly; candidate computation changes latency only, never the format.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
from typing import Any


COLUMNS = [
    "run_id", "layer", "queue_config", "records", "input_bits", "output_bits",
    "total_cycles", "achieved_input_bits_per_cycle", "achieved_output_bits_per_cycle",
    "mean_latency", "p50_latency", "p95_latency", "p99_latency", "max_latency",
    "producer_stall_cycles", "output_stall_cycles", "resource_stall_cycles",
    "mean_input_q", "max_input_q", "mean_output_q", "max_output_q",
    "max_staging_bytes", "critical_path_extension_cycles", "candidate_engines",
]


def _percentile(values: list[int], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = fraction * (len(ordered) - 1)
    lo = int(math.floor(position)); hi = int(math.ceil(position))
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (position - lo)


def _simulate_layer(
    records: list[dict[str, str]], *, input_q_depth: int, working_buffers: int,
    output_fifo_lines: int, candidate_engines: str, producer_width: int = 2048,
    pack_width: int = 64, memory_service_bits: int = 2048,
) -> dict[str, float | int | str]:
    # Candidate latency covers event discovery and length evaluation.  Shared
    # hardware evaluates the three event candidates sequentially; parallel
    # hardware evaluates them together.  A0/A2 anchors add one prototype pass.
    worker_free = [0] * working_buffers
    fifo_capacity = output_fifo_lines * 512
    fifo_bits = 0
    fifo_last_cycle = 0
    producer_time = 0
    producer_stalls = output_stalls = resource_stalls = 0
    latencies: list[int] = []
    q_samples: list[int] = []
    out_samples: list[int] = []
    arrivals: list[int] = []
    completion = 0
    total_input = total_output = 0

    for ordinal, record in enumerate(records):
        input_bits = int(record.get("input_support_bits") or 128 * 128)
        output_bits = int(record["padded_bytes"]) * 8
        total_input += input_bits; total_output += output_bits
        ingest = math.ceil(input_bits / producer_width)
        nominal_arrival = producer_time
        # Count records whose worker start is pending as the finite input queue.
        busy_until = sorted(worker_free)
        available = busy_until[0]
        queued = sum(1 for value in arrivals if value > nominal_arrival)
        if queued >= input_q_depth and available > nominal_arrival:
            producer_stalls += available - nominal_arrival
            nominal_arrival = available
        q_samples.append(min(queued, input_q_depth))
        producer_time = nominal_arrival + ingest

        worker = min(range(len(worker_free)), key=lambda index: (worker_free[index], index))
        start = max(producer_time, worker_free[worker])
        if start > producer_time:
            resource_stalls += start - producer_time
        base_pass = math.ceil(input_bits / producer_width)
        passes = 3 if candidate_engines == "shared" else 1
        if record["role"] == "anchor":
            passes += 1  # fixed-cohort majority/prototype generation
        compute = base_pass * passes + math.ceil(output_bits / pack_width) + 2
        ready = start + compute

        # Drain the bounded output FIFO until this record is ready.
        elapsed = max(0, ready - fifo_last_cycle)
        fifo_bits = max(0, fifo_bits - elapsed * memory_service_bits)
        fifo_last_cycle = ready
        # Packing is a streaming stage: all earlier words may drain while the
        # record is being produced.  Only the final pack-width beat is offered
        # atomically at completion, rather than incorrectly requiring the FIFO
        # to hold an entire large record.
        record_tail_bits = min(output_bits, pack_width)
        if fifo_bits + record_tail_bits > fifo_capacity:
            wait = math.ceil((fifo_bits + record_tail_bits - fifo_capacity) / memory_service_bits)
            output_stalls += wait
            ready += wait
            fifo_bits = max(0, fifo_bits - wait * memory_service_bits)
            fifo_last_cycle = ready
        fifo_bits += record_tail_bits
        out_samples.append(math.ceil(fifo_bits / 512))
        worker_free[worker] = ready
        arrivals.append(ready)
        latencies.append(ready - nominal_arrival)
        completion = max(completion, ready + math.ceil(fifo_bits / memory_service_bits))

    total_cycles = max(completion, 1)
    return {
        "records": len(records), "input_bits": total_input, "output_bits": total_output,
        "total_cycles": total_cycles, "achieved_input_bits_per_cycle": total_input / total_cycles,
        "achieved_output_bits_per_cycle": total_output / total_cycles,
        "mean_latency": statistics.fmean(latencies) if latencies else 0,
        "p50_latency": _percentile(latencies, .50), "p95_latency": _percentile(latencies, .95),
        "p99_latency": _percentile(latencies, .99), "max_latency": max(latencies, default=0),
        "producer_stall_cycles": producer_stalls, "output_stall_cycles": output_stalls,
        "resource_stall_cycles": resource_stalls,
        "mean_input_q": statistics.fmean(q_samples) if q_samples else 0,
        "max_input_q": max(q_samples, default=0),
        "mean_output_q": statistics.fmean(out_samples) if out_samples else 0,
        "max_output_q": max(out_samples, default=0),
        "max_staging_bytes": (input_q_depth + working_buffers) * 2048 + output_fifo_lines * 64,
        "critical_path_extension_cycles": max(0, total_cycles - producer_time),
        "candidate_engines": candidate_engines,
    }


def simulate(records_path: Path, output: Path) -> list[dict[str, Any]]:
    records = list(csv.DictReader(records_path.open()))
    by_layer: dict[tuple[str, int], list[dict[str, str]]] = {}
    for record in records:
        by_layer.setdefault((record["run_id"], int(record["layer"])), []).append(record)
    rows: list[dict[str, Any]] = []
    for input_q in (1, 2, 4, 8):
        for working in (1, 2, 4):
            for fifo in (2, 4, 8, 16):
                for engines in ("shared", "parallel"):
                    config = f"iq{input_q}_work{working}_of{fifo}_{engines}"
                    for (run_id, layer), local in sorted(by_layer.items()):
                        result = _simulate_layer(local, input_q_depth=input_q, working_buffers=working, output_fifo_lines=fifo, candidate_engines=engines)
                        rows.append({"run_id": run_id, "layer": layer, "queue_config": config, **result})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows = simulate(args.records, args.output)
    print(json.dumps({"rows": len(rows), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
