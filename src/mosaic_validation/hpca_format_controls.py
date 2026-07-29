"""Matched-support controls evaluated through the common XORFLOW host.

The controls in this module intentionally modify only binary activation support.
They retain the graph, RCM ordering, cache, feature-slice layout, precision, and
edge schedule used by the real trace.  Consequently a difference in exact
cache-line traffic cannot be attributed to a different host or a free metadata
assumption.  Generated masks are diagnostic support traces: they are never
presented as numerically trained models.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .hpca_format_matrix import run_cases
from .hpca_xorflow_cli import _case
from .null_controls import density_matched_independent_null, temporal_order_null


CONTROL_ORDER = (
    "real_trained",
    "density_matched_independent",
    "node_permuted_within_rcm_tile",
    "temporally_shuffled",
)


def node_permutation_within_tiles(
    masks: np.ndarray, tiles: list[np.ndarray], seed: int = 7007
) -> np.ndarray:
    """Destroy row identity/locality while preserving every row's support count.

    Each layer receives an independently drawn permutation *inside* every RCM
    tile.  No node moves across topology-tile boundaries, so the comparison
    cannot gain traffic merely by changing the tile population.
    """
    source = np.asarray(masks, dtype=bool)
    output = source.copy()
    rng = np.random.default_rng(seed)
    for layer in range(source.shape[0]):
        for tile in tiles:
            output[layer, tile] = source[layer, rng.permutation(tile)]
    return output


def construct_controls(masks: np.ndarray, tiles: list[np.ndarray], seed: int = 7007) -> dict[str, np.ndarray]:
    """Return deterministic support controls, including the unmodified trace."""
    real = np.asarray(masks, dtype=bool)
    return {
        "real_trained": real.copy(),
        "density_matched_independent": density_matched_independent_null(real, seed),
        "node_permuted_within_rcm_tile": node_permutation_within_tiles(real, tiles, seed),
        "temporally_shuffled": temporal_order_null(real, seed),
    }


def _audit(original: np.ndarray, transformed: np.ndarray) -> dict[str, object]:
    """Record preservation properties rather than relying on the control name."""
    original_counts = original.sum(axis=2)
    transformed_counts = transformed.sum(axis=2)
    return {
        "density": float(transformed.mean()),
        "density_delta": float(transformed.mean() - original.mean()),
        "per_layer_density_max_delta": float(np.abs(transformed.mean(axis=(1, 2)) - original.mean(axis=(1, 2))).max()),
        "row_count_multiset_preserved": bool(
            all(np.array_equal(np.sort(original_counts[layer]), np.sort(transformed_counts[layer])) for layer in range(len(original)))
        ),
        "support_sha256": hashlib.sha256(np.packbits(transformed, axis=2).tobytes()).hexdigest(),
    }


def run(
    project: Path,
    config_ids: list[str],
    *,
    output: Path,
    audit_output: Path,
    slice_width: int = 128,
    tile_rows: int = 128,
    cache_bytes: int = 512 * 1024,
    max_pairs: int | None = 1,
    edge_order: str = "O0",
    seed: int = 7007,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Evaluate all exact formats for real and matched synthetic support traces."""
    all_rows: list[pd.DataFrame] = []
    audits: list[dict[str, object]] = []
    for config_id in config_ids:
        masks, data, dataset = _case(project, config_id)
        _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(order, tile_rows)
        for control, support in construct_controls(masks, tiles, seed).items():
            control_id = f"{config_id}__{control}"
            frame = run_cases(
                [(control_id, support, data, dataset)],
                slice_width=slice_width,
                tile_rows=tile_rows,
                cache_bytes=cache_bytes,
                max_pairs=max_pairs,
                edge_order=edge_order,
            )
            frame.insert(1, "source_config_id", config_id)
            frame.insert(2, "control_type", control)
            all_rows.append(frame)
            audits.append({"source_config_id": config_id, "control_type": control, "seed": seed, **_audit(masks, support)})
    result = pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame()
    audit = pd.DataFrame(audits)
    output.parent.mkdir(parents=True, exist_ok=True)
    audit_output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False); audit.to_csv(audit_output, index=False)
    output.with_suffix(".manifest.json").write_text(json.dumps({
        "command": "hpca_format_controls", "configs": config_ids, "seed": seed,
        "rows": len(result), "result_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "audit_sha256": hashlib.sha256(audit_output.read_bytes()).hexdigest(),
    }, indent=2, sort_keys=True) + "\n")
    return result, audit


def main() -> None:
    parser = argparse.ArgumentParser(description="Run matched XORFLOW traffic controls through the common host.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--configs", nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit-output", type=Path, required=True)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--feature-cache-bytes", type=int, default=512 * 1024)
    parser.add_argument("--max-pairs", type=int, default=1)
    parser.add_argument("--edge-order", choices=("O0", "O1"), default="O0")
    parser.add_argument("--seed", type=int, default=7007)
    args = parser.parse_args(); project = args.project.resolve()
    output = args.output if args.output.is_absolute() else project / args.output
    audit = args.audit_output if args.audit_output.is_absolute() else project / args.audit_output
    frame, checks = run(project, args.configs, output=output, audit_output=audit,
                        slice_width=args.slice_width, tile_rows=args.tile_rows,
                        cache_bytes=args.feature_cache_bytes, max_pairs=args.max_pairs,
                        edge_order=args.edge_order, seed=args.seed)
    print(frame.groupby(["source_config_id", "control_type", "format"], as_index=False).total_traffic_bytes.sum().to_string(index=False))
    print(checks.to_string(index=False))


if __name__ == "__main__":
    main()
