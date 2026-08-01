"""Full same-host B0–B4/X0–X2/oracle format matrix for XORFLOW.

The matrix deliberately keeps physical value layout and graph/cache replay
common. It is a format comparison, not a comparison between unrelated GNN
accelerator hosts.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .causal_xorflow import beicsr_pair_support_bits, encode_offline_majority_pair
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .hpca_baseline_matrix import _external_metadata_output_bytes, run_cases as run_baseline_cases
from .hpca_xorflow_cli import _case, _output_writeback_traffic, _pair_starts, _physical_traffic, _sources, build_pair_format_plan
from .memory_subsystem import build_mixed_sliced_layout, validate_nonoverlap


def _offline_plan(pair: np.ndarray, tiles: list[np.ndarray], slice_width: int) -> dict[str, object]:
    """Choose an offline-majority oracle or BEICSR per tile/slice exactly."""
    rows, features = pair.shape[1:]
    slices = math.ceil(features / slice_width)
    formats = np.full((rows, slices), "BEICSR", dtype=object)
    bits = independent_bits = metadata = selectors = decode_cycles = selected = 0
    variants: dict[str, int] = {}
    fallback_bits = 0
    for tile in tiles:
        local = pair[:, tile, :]
        for sid in range(slices):
            lo, hi = sid * slice_width, min(features, (sid + 1) * slice_width)
            encoded = encode_offline_majority_pair(local[:, :, lo:hi])
            independent = beicsr_pair_support_bits(local[:, :, lo:hi])
            independent_bits += independent
            if encoded.encoded_support_bits < independent:
                formats[tile, sid] = "XORFLOW"
                bits += encoded.encoded_support_bits
                metadata += math.ceil(encoded.encoded_support_bits / 8 / 64) * 64
                selectors += encoded.selector_bits
                decode_cycles += math.ceil(encoded.encoded_support_bits / 2048)
                selected += 1
                variants[encoded.spatial_dictionary.variant] = variants.get(encoded.spatial_dictionary.variant, 0) + 1
            else:
                bits += independent + 1
                fallback_bits += 1
    if fallback_bits:
        metadata += math.ceil(fallback_bits / 8 / 64) * 64
    return {
        "formats": formats, "support_bits": bits, "independent_support_bits": independent_bits,
        "metadata_bytes": metadata, "selector_bits": selectors + fallback_bits,
        "decode_cycles": decode_cycles, "selected_tiles": selected, "variants": variants,
    }


def _free_support_plan(pair: np.ndarray, slice_width: int) -> dict[str, object]:
    rows, features = pair.shape[1:]
    return {
        "formats": np.full((rows, math.ceil(features / slice_width)), "XORFLOW", dtype=object),
        "support_bits": 0, "independent_support_bits": 0, "metadata_bytes": 0,
        "selector_bits": 0, "decode_cycles": 0, "selected_tiles": rows * math.ceil(features / slice_width), "variants": {},
    }


def _normalize_causal_plan(plan: dict[str, object]) -> dict[str, object]:
    """Map the legacy preflight naming to the common format-matrix schema."""
    return {
        "formats": plan["formats"],
        "support_bits": plan["xor_support_bits"],
        "independent_support_bits": plan["beicsr_support_bits"],
        "metadata_bytes": plan["xor_metadata"],
        "selector_bits": plan["selector_bits"],
        "decode_cycles": plan["decode_cycles"],
        "selected_tiles": plan["selected_tiles"],
        "variants": plan["variants"],
    }


def _causal_row(
    *,
    config_id: str,
    dataset: str,
    start: int,
    pair: np.ndarray,
    plan: dict[str, object],
    representation: str,
    deployable: bool,
    order: np.ndarray,
    sources: np.ndarray,
    edge_count: int,
    node_count: int,
    cache_bytes: int,
    slice_width: int,
    edge_order: str,
) -> dict[str, object]:
    layouts = [
        build_mixed_sliced_layout(layer, slice_width=slice_width, formats=plan["formats"], node_order=order)
        for layer in pair
    ]
    if not all(validate_nonoverlap(layout) for layout in layouts):
        raise AssertionError("format-matrix layout overlap")
    reads, writes, hits, misses = _physical_traffic(layouts, sources, cache_bytes, start)
    topology = 2 * (edge_count * 4 + (node_count + 1) * 4)
    output = _output_writeback_traffic(layouts) + 2 * int(plan["metadata_bytes"])
    descriptor = sum(layout.starts.size * layout.descriptor_bytes for layout in layouts)
    total = reads + writes + topology + output + int(plan["metadata_bytes"])
    return {
        "config_id": config_id,
        "dataset": dataset,
        "pair_start_layer": start + 1,
        "pair_end_layer": start + 2,
        "format": representation,
        "deployable": deployable,
        "slice_width": slice_width,
        "feature_cache_bytes": cache_bytes,
        "edge_order": edge_order,
        "value_bytes": int(pair.sum()),
        "support_index_bytes": math.ceil(int(plan["support_bits"]) / 8),
        "row_pointer_stream_bytes": 0,
        "selector_stream_bytes": math.ceil(int(plan["selector_bits"]) / 8),
        "descriptor_bytes": descriptor,
        "reserved_capacity_bytes": sum(layout.reserved_capacity_bytes for layout in layouts) + int(plan["metadata_bytes"]),
        "feature_cache_accesses": hits + misses,
        "feature_cache_hits": hits,
        "feature_cache_misses": misses,
        "feature_read_bytes": reads,
        "feature_writeback_bytes": writes,
        "topology_bytes": topology,
        "output_write_bytes": output,
        "total_traffic_bytes": total,
        "support_decode_cycles": int(plan["decode_cycles"]),
        "anchor_variants": json.dumps(plan["variants"], sort_keys=True),
        "selected_xorflow_tile_slices": int(plan["selected_tiles"]),
        "exact_layout_pass": True,
        "exact_decode_pass": True,
    }


def run_cases(
    cases: list[tuple[str, np.ndarray, object, str]],
    *,
    slice_width: int = 128,
    tile_rows: int = 128,
    cache_bytes: int = 512 * 1024,
    max_pairs: int | None = 2,
    edge_order: str = "O0",
) -> pd.DataFrame:
    """Evaluate all physical-format rows under identical host inputs."""
    baseline = run_baseline_cases(
        cases, slice_width=slice_width, cache_bytes=cache_bytes,
        max_pairs=max_pairs, edge_order=edge_order,
    )
    rows = baseline.to_dict("records")
    for config_id, masks, data, dataset in cases:
        edge_index = data.edge_index.cpu().numpy()
        _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(order, tile_rows)
        sources = _sources(edge_index, edge_order)
        for start in _pair_starts(len(masks), max_pairs):
            pair = masks[start:start + 2]
            plans = {
                "X0_CAUSAL_INDEPENDENT": (_normalize_causal_plan(build_pair_format_plan(pair, tiles, slice_width, dictionary_mode="a0")), True),
                "X1_CAUSAL_AUTO": (_normalize_causal_plan(build_pair_format_plan(pair, tiles, slice_width)), True),
                "X2_CAUSAL_FORCE": (_normalize_causal_plan(build_pair_format_plan(pair, tiles, slice_width, allow_fallback=False)), True),
                "O0_OFFLINE_MAJORITY": (_offline_plan(pair, tiles, slice_width), False),
                "O1_FREE_SUPPORT": (_free_support_plan(pair, slice_width), False),
            }
            for representation, (plan, deployable) in plans.items():
                rows.append(_causal_row(
                    config_id=config_id, dataset=dataset, start=start, pair=pair, plan=plan,
                    representation=representation, deployable=deployable, order=order,
                    sources=sources, edge_count=int(edge_index.shape[1]), node_count=int(data.num_nodes),
                    cache_bytes=cache_bytes, slice_width=slice_width, edge_order=edge_order,
                ))
    frame = pd.DataFrame(rows)
    if not frame.empty:
        best = frame.loc[frame.format == "BEICSR", ["config_id", "pair_start_layer", "total_traffic_bytes"]].rename(columns={"total_traffic_bytes": "beicsr_bytes"})
        frame = frame.merge(best, on=["config_id", "pair_start_layer"], how="left")
        frame["traffic_ratio_to_beicsr"] = frame.total_traffic_bytes / frame.beicsr_bytes
        frame["traffic_reduction_vs_beicsr"] = 1 - frame.traffic_ratio_to_beicsr
        frame.drop(columns="beicsr_bytes", inplace=True)
    return frame


def run(
    project: Path,
    config_ids: list[str],
    *,
    slice_width: int = 128,
    tile_rows: int = 128,
    cache_bytes: int = 512 * 1024,
    max_pairs: int | None = 2,
    edge_order: str = "O0",
) -> pd.DataFrame:
    """Load named traces and evaluate the complete same-host format matrix."""
    return run_cases(
        [(config_id, *_case(project, config_id)) for config_id in config_ids],
        slice_width=slice_width,
        tile_rows=tile_rows,
        cache_bytes=cache_bytes,
        max_pairs=max_pairs,
        edge_order=edge_order,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate common XORFLOW B0–B4/X0–X2/oracle matrix.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--configs", nargs="+", required=True)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--feature-cache-bytes", type=int, default=512 * 1024)
    parser.add_argument("--max-pairs", type=int, default=2)
    parser.add_argument("--edge-order", choices=("O0", "O1"), default="O0")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(); project = args.project.resolve()
    output = args.output if args.output.is_absolute() else project / args.output
    frame = run(project, args.configs, slice_width=args.slice_width, tile_rows=args.tile_rows, cache_bytes=args.feature_cache_bytes, max_pairs=args.max_pairs, edge_order=args.edge_order)
    output.parent.mkdir(parents=True, exist_ok=True); frame.to_csv(output, index=False)
    output.with_suffix(".manifest.json").write_text(json.dumps({
        "command": "hpca_format_matrix", "configs": args.configs, "rows": len(frame),
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
    }, indent=2, sort_keys=True) + "\n")
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
