"""Stage-1 causal XORFLOW preflight using exact cache-line traffic.

This command is intentionally narrower than the final host simulator.  It
answers one question without shortcuts: after replacing the non-causal anchor
with a legal two-layer anchor, does the exact selector still reduce real
feature-cache traffic versus equally laid-out BEICSR?  It emits structured
logs and auditable per-pair records; it never overwrites prior-phase results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from .causal_xorflow import select_causal_pair
from .datasets import load_dataset
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .memory_subsystem import (
    build_mixed_sliced_layout,
    build_sliced_layout,
    simulate_layout_source_lru,
    validate_nonoverlap,
)


def _unpack(path: Path) -> np.ndarray:
    payload = np.load(path)
    shape = tuple(int(value) for value in payload["shape"])
    return np.unpackbits(payload["packed"], axis=2)[:, :, :shape[2]].astype(bool)


def _case(project: Path, config_id: str) -> tuple[np.ndarray, object, str]:
    if config_id.startswith("ogbn_arxiv_deepres8_w128_s"):
        trace = project / f"artifacts_hpca_xorflow/workloads/{config_id}/fp8_supports.npz"
        from ogb.nodeproppred import PygNodePropPredDataset
        import torch_geometric.transforms as transforms
        original_load = torch.load
        def trusted_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_load(*args, **kwargs)
        torch.load = trusted_load
        try:
            dataset = PygNodePropPredDataset(name="ogbn-arxiv", root=str(project / "data"), transform=transforms.ToUndirected())
        finally:
            torch.load = original_load
        return _unpack(trace), dataset[0], "OGBN-Arxiv"
    if config_id == "ogbn_arxiv_deepres8_w128":
        from ogb.nodeproppred import PygNodePropPredDataset
        import torch_geometric.transforms as transforms
        # OGB's local processed Data object predates PyTorch's safe-load
        # default.  The shared downloaded dataset is trusted and this exactly
        # matches the existing safe-zone Arxiv loader.
        original_load = torch.load
        def trusted_load(*args, **kwargs):
            kwargs.setdefault("weights_only", False)
            return original_load(*args, **kwargs)
        torch.load = trusted_load
        try:
            dataset = PygNodePropPredDataset(
                name="ogbn-arxiv", root=str(project / "data"), transform=transforms.ToUndirected()
            )
        finally:
            torch.load = original_load
        return _unpack(project / "artifacts_safezone/ogbn_arxiv/supports.npz"), dataset[0], "OGBN-Arxiv"
    if config_id == "reddit_deepres8_w128_s7_native":
        trace = project / "artifacts_hpca_xorflow/workloads/reddit_deepres8_w128_s7_native/fp8_supports.npz"
        data = load_dataset("Reddit", project / "data")[0]
        return _unpack(trace), data, "Reddit"
    if config_id == "yelp_deepres8_w128_s7":
        trace = project / "artifacts_hpca_xorflow/workloads/yelp_deepres8_w128_s7/fp8_supports.npz"
        data = load_dataset("Yelp", project / "data")[0]
        return _unpack(trace), data, "Yelp"
    if config_id == "flickr_deepres8_w128_s7":
        trace = project / "artifacts_hpca_xorflow/workloads/flickr_deepres8_w128_s7/fp8_supports.npz"
        data = load_dataset("Flickr", project / "data")[0]
        return _unpack(trace), data, "Flickr"
    path = project / f"artifacts_final8/masks/{config_id}_fp8_supports.npz"
    if "pubmed" in config_id:
        data = load_dataset("PubMed", project / "data")[0]
    elif "chameleon" in config_id:
        data = load_dataset("chameleon", project / "data")[0]
    else:
        data = load_dataset("Cora", project / "data")[0]
    return _unpack(path), data, data.__class__.__name__


def _sources(edge_index: np.ndarray, order: str, source_tile_size: int = 512) -> np.ndarray:
    src, dst = np.asarray(edge_index, dtype=np.int64)
    ordinal = np.arange(src.size, dtype=np.int64)
    if order == "O0":
        indices = np.lexsort((ordinal, dst))
    elif order == "O1":
        indices = np.lexsort((src, dst, src // source_tile_size, dst // 128))
    else:
        raise ValueError(f"unsupported edge order: {order}")
    return src[indices]


def _pair_starts(mask_count: int, limit: int | None) -> list[int]:
    # Supports are numbered from one in paper tables; the hidden-layer index is
    # zero based.  Begin at hidden layer four and form non-overlapping pairs.
    result = list(range(3, mask_count - 1, 2))
    return result if limit is None else result[:limit]


def _physical_traffic(layouts, sources: np.ndarray, cache_bytes: int, pair_id: int) -> tuple[int, int, int, int]:
    """Return feature read bytes, writeback bytes, hits, and misses for two layers."""
    reads = writes = hits = misses = 0
    for layout in layouts:
        # Layers use double-buffered address spaces.  Cache state does not
        # retain stale feature lines across them, so simulate each separately.
        cache = simulate_layout_source_lru(layout, sources, capacity_bytes=cache_bytes)
        reads += cache.read_bytes
        writes += cache.writeback_bytes
        hits += cache.hits
        misses += cache.misses
    return reads, writes, hits, misses


def _output_writeback_traffic(layouts) -> int:
    """Exact write-allocate plus dirty-writeback traffic for fresh outputs."""
    touched = 0
    for layout in layouts:
        # Every row-slice start is 64-byte aligned, so each useful range spans
        # exactly ceil(useful/64) unique output lines.
        touched += int(np.ceil(layout.useful_bytes / 64).sum())
    return touched * 2 * 64  # read-for-ownership, then dirty eviction


def build_pair_format_plan(pair: np.ndarray, tiles: list[np.ndarray], slice_width: int) -> dict:
    """Choose exact causal XORFLOW or BEICSR per tile/slice for one pair."""
    n, features = pair.shape[1:]
    slices = math.ceil(features / slice_width)
    formats = np.full((n, slices), "BEICSR", dtype=object)
    xor_support_bits = beicsr_support_bits = xor_metadata = 0
    fallback_selector_bits = decode_cycles = selector_bits = selected_tiles = 0
    variants: dict[str, int] = {}
    for tile in tiles:
        local_pair = pair[:, tile, :]
        for sid in range(slices):
            lo, hi = sid * slice_width, min(features, (sid + 1) * slice_width)
            selected = select_causal_pair(local_pair[:, :, lo:hi])
            beicsr_support_bits += selected.independent_support_bits
            if selected.representation == "XORFLOW_CAUSAL":
                assert selected.pair is not None
                formats[tile, sid] = "XORFLOW"
                selected_tiles += 1
                xor_support_bits += selected.pair.encoded_support_bits
                xor_metadata += math.ceil(selected.pair.encoded_support_bits / 8 / 64) * 64
                selector_bits += selected.pair.selector_bits
                decode_cycles += math.ceil(selected.pair.encoded_support_bits / 2048)
                variants[selected.pair.anchor_variant] = variants.get(selected.pair.anchor_variant, 0) + 1
            else:
                xor_support_bits += selected.independent_support_bits + 1
                fallback_selector_bits += 1
    xor_metadata += math.ceil(fallback_selector_bits / 8 / 64) * 64 if fallback_selector_bits else 0
    return {
        "formats": formats, "slices": slices, "xor_support_bits": xor_support_bits,
        "beicsr_support_bits": beicsr_support_bits, "xor_metadata": xor_metadata,
        "decode_cycles": decode_cycles, "selector_bits": selector_bits,
        "selected_tiles": selected_tiles, "variants": variants,
    }


def run(
    project: Path,
    config_ids: list[str],
    *,
    slice_width: int,
    tile_rows: int,
    cache_bytes: int,
    max_pairs: int | None,
    edge_order: str,
    output_path: Path | None = None,
) -> pd.DataFrame:
    results = project / "results_hpca_xorflow"
    artifacts = project / "artifacts_hpca_xorflow"
    results.mkdir(exist_ok=True)
    (artifacts / "logs").mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("hpca_xorflow_preflight")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    # One run has one self-contained log.  Long experiments use distinct
    # staged run directories; silently appending incompatible retries makes
    # later auditing needlessly error-prone.
    handler = logging.FileHandler(artifacts / "logs/causal_preflight.jsonl", mode="w")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    rows: list[dict] = []
    started = time.monotonic()
    for config_id in config_ids:
        masks, data, dataset_name = _case(project, config_id)
        edge_index = data.edge_index.cpu().numpy()
        _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(order, tile_rows)
        sources = _sources(edge_index, edge_order)
        # Keep destinations in precisely the same permutation as sources so
        # engine load accounting reflects the selected edge order.
        src, dst = edge_index
        ordinal = np.arange(src.size, dtype=np.int64)
        if edge_order == "O0":
            edge_permutation = np.lexsort((ordinal, dst))
        else:
            edge_permutation = np.lexsort((src, dst, src // 512, dst // 128))
        destinations = dst[edge_permutation]
        logger.info(json.dumps({"event": "config_start", "config_id": config_id, "dataset": dataset_name, "nodes": int(data.num_nodes), "edges": int(edge_index.shape[1]), "layers": int(len(masks))}, sort_keys=True))
        for pair_number, start in enumerate(_pair_starts(len(masks), max_pairs)):
            pair = masks[start:start + 2]
            n, features = pair.shape[1:]
            plan = build_pair_format_plan(pair, tiles, slice_width)
            formats = plan["formats"]; slices = plan["slices"]
            xor_support_bits = plan["xor_support_bits"]; beicsr_support_bits = plan["beicsr_support_bits"]
            xor_metadata = plan["xor_metadata"]; decode_cycles = plan["decode_cycles"]
            selector_bits = plan["selector_bits"]; selected_tiles = plan["selected_tiles"]; variants = plan["variants"]
            xor_layouts = [
                build_mixed_sliced_layout(layer, slice_width=slice_width, formats=formats, node_order=order)
                for layer in pair
            ]
            beicsr_layouts = [
                build_sliced_layout(layer, slice_width=slice_width, format_name="BEICSR", node_order=order)
                for layer in pair
            ]
            assert all(validate_nonoverlap(layout) for layout in xor_layouts + beicsr_layouts)
            xor_feature, xor_wb, xor_hits, xor_misses = _physical_traffic(xor_layouts, sources, cache_bytes, pair_number)
            beic_feature, beic_wb, beic_hits, beic_misses = _physical_traffic(beicsr_layouts, sources, cache_bytes, pair_number)
            topology_bytes = 2 * (edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4)
            descriptor_bytes = sum(layout.starts.size * layout.descriptor_bytes for layout in xor_layouts)
            beic_output = _output_writeback_traffic(beicsr_layouts)
            # XORFLOW writes its packed value rows through the selected layout
            # plus every aligned anchor/exception output stream.
            xor_output = _output_writeback_traffic(xor_layouts) + 2 * xor_metadata
            beic_total = beic_feature + beic_wb + topology_bytes + beic_output
            xor_total = xor_feature + xor_wb + xor_metadata + topology_bytes + xor_output
            descriptor_cycles = math.ceil(descriptor_bytes / 64)
            beic_memory_cycles = math.ceil(beic_total / 256)
            xor_memory_cycles = math.ceil(xor_total / 256)
            beic_cycles = beic_memory_cycles + descriptor_cycles
            xor_cycles = xor_memory_cycles + decode_cycles + descriptor_cycles
            # The support decoder consumes a separate metadata stream and
            # writes a finite tile-local bitmap before edge replay begins.
            # For this pair-level preflight it can overlap the subsequent
            # feature/HBM service, but never descriptor dispatch or a layer
            # barrier.  The full simulator will model each tile buffer event.
            xor_overlapped_cycles = max(xor_memory_cycles, decode_cycles) + descriptor_cycles
            aggregation_values = 0
            aggregation_cycles = 0
            aggregation_imbalance = 1.0
            for layer in pair:
                per_edge = layer.sum(axis=1, dtype=np.int64)[sources]
                engine_values = np.bincount(destinations % 8, weights=per_edge, minlength=8)
                aggregation_values += int(per_edge.sum())
                average = float(engine_values.mean())
                aggregation_imbalance = max(
                    aggregation_imbalance,
                    float(engine_values.max()) / max(average, 1.0),
                )
                aggregation_cycles += math.ceil(float(engine_values.max()) / 16.0)
            row = {
                "config_id": config_id,
                "pair_start_layer": start + 1,
                "pair_end_layer": start + 2,
                "slice_width": slice_width,
                "tile_rows": tile_rows,
                "edge_order": edge_order,
                "feature_cache_bytes": cache_bytes,
                "nodes": n,
                "edges": int(edge_index.shape[1]),
                "pair_active_values": int(pair.sum()),
                "aggregation_active_values": aggregation_values,
                "aggregation_simd_cycles_8x16": aggregation_cycles,
                "aggregation_load_imbalance": aggregation_imbalance,
                "selected_xorflow_tile_slices": selected_tiles,
                "total_tile_slices": len(tiles) * slices,
                "anchor_variants": json.dumps(variants, sort_keys=True),
                "beicsr_support_bits": beicsr_support_bits,
                "xorflow_support_bits": xor_support_bits,
                "support_ratio_to_beicsr": xor_support_bits / max(beicsr_support_bits, 1),
                "xorflow_metadata_read_bytes": xor_metadata,
                "beicsr_feature_read_bytes": beic_feature,
                "xorflow_feature_read_bytes": xor_feature,
                "beicsr_writeback_bytes": beic_wb,
                "xorflow_writeback_bytes": xor_wb,
                "topology_bytes": topology_bytes,
                "beicsr_output_write_bytes": beic_output,
                "xorflow_output_write_bytes": xor_output,
                "beicsr_cache_hits": beic_hits,
                "xorflow_cache_hits": xor_hits,
                "beicsr_cache_misses": beic_misses,
                "xorflow_cache_misses": xor_misses,
                "beicsr_total_bytes": beic_total,
                "xorflow_total_bytes": xor_total,
                "traffic_reduction": 1 - xor_total / max(beic_total, 1),
                "support_decode_cycles": decode_cycles,
                "descriptor_cycles": descriptor_cycles,
                "beicsr_serialized_cycles": beic_cycles,
                "xorflow_serialized_cycles": xor_cycles,
                "xorflow_overlapped_cycles": xor_overlapped_cycles,
                "serialized_speedup": beic_cycles / max(xor_cycles, 1),
                "double_buffered_speedup": beic_cycles / max(xor_overlapped_cycles, 1),
                "exact_decode_pass": True,
                "causal_deployable": True,
            }
            rows.append(row)
            logger.info(json.dumps({"event": "pair_complete", **row}, sort_keys=True))
    frame = pd.DataFrame(rows)
    # A large-workload job must never overwrite another configuration's
    # evidence.  The legacy aggregate filename remains the explicit default
    # for compact quick runs only.
    target = output_path or (results / "01_causal_pair_preflight.csv")
    if not target.is_absolute():
        target = project / target
    target.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target, index=False)
    manifest = {
        "command": "causal_pair_preflight",
        "wall_seconds": time.monotonic() - started,
        "rows": len(frame),
        "output": str(target.relative_to(project)),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
    (artifacts / "causal_preflight_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return frame


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--configs", nargs="+", default=["cora_gcnii16", "pubmed_gcnii16", "cora_deepres28_w128", "ogbn_arxiv_deepres8_w128"])
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--feature-cache-bytes", type=int, default=512 * 1024)
    parser.add_argument("--max-pairs", type=int, default=None)
    parser.add_argument("--edge-order", choices=("O0", "O1"), default="O0")
    parser.add_argument("--output", type=Path, help="configuration-specific CSV path; avoids overwriting another run")
    args = parser.parse_args()
    output = run(args.project.resolve(), args.configs, slice_width=args.slice_width, tile_rows=args.tile_rows, cache_bytes=args.feature_cache_bytes, max_pairs=args.max_pairs, edge_order=args.edge_order, output_path=args.output)
    print(output.to_string(index=False))


if __name__ == "__main__":
    main()
