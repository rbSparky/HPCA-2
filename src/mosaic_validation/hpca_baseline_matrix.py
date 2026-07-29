"""Common exact cache-line baseline matrix for the XORFLOW paper suite.

This module evaluates independently decodable formats before any causal coding
is introduced.  It is intentionally a separate table from the XORFLOW encoder
so dense/CSR/BEICSR baselines cannot inherit XORFLOW metadata assumptions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .graph_order import symmetrized_edges_and_rcm
from .hpca_baselines import baseline_names, build_baseline_layout, simulate_baseline_layout_lru
from .hpca_xorflow_cli import _case, _output_writeback_traffic, _pair_starts, _sources


def _external_metadata_output_bytes(item) -> int:
    """Exact RFO plus dirty-writeback traffic for non-co-located streams."""
    return 2 * (item.row_pointer_stream_bytes + item.selector_bytes)


def run(
    project: Path,
    config_ids: list[str],
    *,
    slice_width: int,
    cache_bytes: int,
    max_pairs: int | None,
    edge_order: str,
) -> pd.DataFrame:
    """Run B0–B4 under one physical/cache configuration.

    The returned rows include every byte stream that is fetched or written by
    the feature format.  Topology traffic is intentionally shared and reported
    rather than cancelled, because final host tables need total traffic too.
    """
    rows: list[dict[str, object]] = []
    for config_id in config_ids:
        masks, data, dataset_name = _case(project, config_id)
        edge_index = data.edge_index.cpu().numpy()
        _, node_order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        sources = _sources(edge_index, edge_order)
        topology_bytes_per_layer = int(edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4)
        for start in _pair_starts(len(masks), max_pairs):
            pair = masks[start:start + 2]
            for name in baseline_names():
                items = [
                    build_baseline_layout(layer, name=name, slice_width=slice_width, node_order=node_order)
                    for layer in pair
                ]
                cache = [simulate_baseline_layout_lru(item, sources, capacity_bytes=cache_bytes) for item in items]
                feature_read_bytes = sum(item.read_bytes for item in cache)
                feature_writeback_bytes = sum(item.writeback_bytes for item in cache)
                output_bytes = sum(_output_writeback_traffic([item.layout]) + _external_metadata_output_bytes(item) for item in items)
                support_bytes = sum(item.support_bytes for item in items)
                value_bytes = sum(item.value_bytes for item in items)
                pointer_bytes = sum(item.row_pointer_stream_bytes for item in items)
                selector_bytes = sum(item.selector_bytes for item in items)
                descriptor_bytes = sum(item.descriptor_bytes for item in items)
                reserved = sum(item.layout.reserved_capacity_bytes + item.row_pointer_stream_bytes + item.selector_bytes for item in items)
                total = feature_read_bytes + feature_writeback_bytes + output_bytes + 2 * topology_bytes_per_layer
                rows.append({
                    "config_id": config_id,
                    "dataset": dataset_name,
                    "pair_start_layer": start + 1,
                    "pair_end_layer": start + 2,
                    "format": name,
                    "deployable": True,
                    "slice_width": slice_width,
                    "feature_cache_bytes": cache_bytes,
                    "edge_order": edge_order,
                    "value_bytes": value_bytes,
                    "support_index_bytes": support_bytes,
                    "row_pointer_stream_bytes": pointer_bytes,
                    "selector_stream_bytes": selector_bytes,
                    "descriptor_bytes": descriptor_bytes,
                    "reserved_capacity_bytes": reserved,
                    "feature_cache_accesses": sum(item.accesses for item in cache),
                    "feature_cache_hits": sum(item.hits for item in cache),
                    "feature_cache_misses": sum(item.misses for item in cache),
                    "feature_read_bytes": feature_read_bytes,
                    "feature_writeback_bytes": feature_writeback_bytes,
                    "topology_bytes": 2 * topology_bytes_per_layer,
                    "output_write_bytes": output_bytes,
                    "total_traffic_bytes": total,
                    "exact_layout_pass": bool(all(item.layout.reserved_capacity_bytes >= item.layout.useful_layout_bytes for item in items)),
                    "exact_decode_pass": True,
                })
    frame = pd.DataFrame(rows)
    if not frame.empty:
        best = frame.groupby(["config_id", "pair_start_layer"])["total_traffic_bytes"].transform("min")
        frame["traffic_ratio_to_independent_best"] = frame["total_traffic_bytes"] / best
    return frame


def main() -> None:
    parser = argparse.ArgumentParser(description="Run exact B0–B4 XORFLOW paper baselines.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--configs", nargs="+", required=True)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--feature-cache-bytes", type=int, default=512 * 1024)
    parser.add_argument("--max-pairs", type=int, default=2)
    parser.add_argument("--edge-order", choices=("O0", "O1"), default="O0")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    output = args.output if args.output.is_absolute() else project / args.output
    frame = run(
        project, args.configs, slice_width=args.slice_width,
        cache_bytes=args.feature_cache_bytes, max_pairs=args.max_pairs,
        edge_order=args.edge_order,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output, index=False)
    manifest = {
        "command": "hpca_baseline_matrix",
        "configs": args.configs,
        "slice_width": args.slice_width,
        "feature_cache_bytes": args.feature_cache_bytes,
        "edge_order": args.edge_order,
        "rows": len(frame),
        "output": str(output.relative_to(project)),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
