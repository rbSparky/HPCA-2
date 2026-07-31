"""Exact edge-driven feature-cache traffic for causal online records."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.hpca_xorflow_cli import _case, _output_writeback_traffic, _sources
from mosaic_validation.memory_subsystem import (
    build_mixed_sliced_layout,
    build_sliced_layout,
    simulate_layout_source_lru,
    validate_nonoverlap,
)
from .online_replay import unpack_supports


COLUMNS = [
    "run_id", "dataset", "model", "seed", "layer", "slice_width", "feature_cache_bytes",
    "edge_order", "baseline_format", "baseline_feature_read_bytes", "baseline_writeback_bytes",
    "baseline_output_bytes", "baseline_topology_bytes", "baseline_total_bytes",
    "xorflow_feature_read_bytes", "xorflow_writeback_bytes", "xorflow_output_bytes",
    "xorflow_metadata_bytes", "xorflow_anchor_read_bytes", "xorflow_topology_bytes",
    "xorflow_total_bytes", "traffic_reduction", "baseline_cache_hits", "baseline_cache_misses",
    "xorflow_cache_hits", "xorflow_cache_misses", "exact_layout_pass",
]


def compute(
    *, project: Path, config_id: str, records_path: Path, output: Path,
    slice_width: int = 128, tile_rows: int = 128, cache_bytes: int = 512 * 1024,
    edge_order: str = "O0",
) -> list[dict[str, Any]]:
    trace = project / "artifacts_hpca_xorflow" / "workloads" / config_id / "fp8_supports.npz"
    if not trace.exists(): trace = project / "artifacts_final8" / "masks" / f"{config_id}_fp8_supports.npz"
    supports = unpack_supports(trace)
    _, data, dataset = _case(project, config_id)
    if dataset == "Data": dataset = config_id.split("_", 1)[0].title()
    edge_index = data.edge_index.cpu().numpy()
    _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    sources = _sources(edge_index, edge_order)
    records = list(csv.DictReader(records_path.open()))
    run_id = records[0]["run_id"]
    seed = int(records[0]["seed"])
    model = records[0]["model"]
    by_layer: dict[int, list[dict[str, str]]] = {}
    for record in records:
        by_layer.setdefault(int(record["layer"]), []).append(record)
    topology = int(edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4)
    rows: list[dict[str, Any]] = []
    for layer, mask in enumerate(supports):
        slices = math.ceil(mask.shape[1] / slice_width)
        formats = np.full((mask.shape[0], slices), "BEICSR", dtype=object)
        metadata = anchor_reads = 0
        for record in by_layer[layer]:
            tile = int(record["tile"]); sid = int(record["slice"])
            tile_nodes = order[tile * tile_rows:min(len(order), (tile + 1) * tile_rows)]
            if record["chosen_format"] != "BEICSR":
                formats[tile_nodes, sid] = "XORFLOW"
                metadata += int(record["padded_bytes"])
            anchor_reads += int(record["anchor_read_bytes"])
        baseline_layout = build_sliced_layout(mask, slice_width=slice_width, format_name="BEICSR", node_order=order)
        xor_layout = build_mixed_sliced_layout(mask, slice_width=slice_width, formats=formats, node_order=order)
        if not validate_nonoverlap(baseline_layout) or not validate_nonoverlap(xor_layout):
            raise AssertionError("physical causal layout overlap")
        baseline_cache = simulate_layout_source_lru(baseline_layout, sources, capacity_bytes=cache_bytes)
        xor_cache = simulate_layout_source_lru(xor_layout, sources, capacity_bytes=cache_bytes)
        baseline_output = _output_writeback_traffic([baseline_layout])
        xor_output = _output_writeback_traffic([xor_layout]) + 2 * metadata
        baseline_total = baseline_cache.read_bytes + baseline_cache.writeback_bytes + topology + baseline_output
        xor_total = xor_cache.read_bytes + xor_cache.writeback_bytes + topology + xor_output + metadata + anchor_reads
        rows.append({
            "run_id": run_id, "dataset": dataset, "model": model, "seed": seed, "layer": layer,
            "slice_width": slice_width, "feature_cache_bytes": cache_bytes, "edge_order": edge_order,
            "baseline_format": "BEICSR", "baseline_feature_read_bytes": baseline_cache.read_bytes,
            "baseline_writeback_bytes": baseline_cache.writeback_bytes, "baseline_output_bytes": baseline_output,
            "baseline_topology_bytes": topology, "baseline_total_bytes": baseline_total,
            "xorflow_feature_read_bytes": xor_cache.read_bytes, "xorflow_writeback_bytes": xor_cache.writeback_bytes,
            "xorflow_output_bytes": xor_output, "xorflow_metadata_bytes": metadata,
            "xorflow_anchor_read_bytes": anchor_reads, "xorflow_topology_bytes": topology,
            "xorflow_total_bytes": xor_total, "traffic_reduction": 1 - xor_total / max(baseline_total, 1),
            "baseline_cache_hits": baseline_cache.hits, "baseline_cache_misses": baseline_cache.misses,
            "xorflow_cache_hits": xor_cache.hits, "xorflow_cache_misses": xor_cache.misses,
            "exact_layout_pass": True,
        })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS); writer.writeheader(); writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--feature-cache-bytes", type=int, default=512 * 1024)
    parser.add_argument("--edge-order", choices=("O0", "O1"), default="O0")
    args = parser.parse_args()
    rows = compute(project=args.project.resolve(), config_id=args.config_id, records_path=args.records, output=args.output, slice_width=args.slice_width, tile_rows=args.tile_rows, cache_bytes=args.feature_cache_bytes, edge_order=args.edge_order)
    print(json.dumps({"rows": len(rows), "traffic_reduction": 1 - sum(row["xorflow_total_bytes"] for row in rows) / sum(row["baseline_total_bytes"] for row in rows)}, sort_keys=True))


if __name__ == "__main__":
    main()
