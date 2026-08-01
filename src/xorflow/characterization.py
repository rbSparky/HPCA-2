"""Empirical adjacent-support persistence and matched-null characterization."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.hpca_xorflow_cli import _case
from .online_replay import unpack_supports
from .serializer import Codec, serialize_record


COLUMNS = [
    "run_id", "dataset", "model", "seed", "layer", "target_layer", "tile", "slice",
    "slice_width", "control_type", "density_l", "density_target", "xor_density",
    "hamming_similarity", "jaccard_similarity", "intersection_count", "union_count",
    "row_events_mean", "row_events_p50", "row_events_p95", "row_events_max",
    "flattened_delta_events", "gap_mean", "gap_p50", "gap_p90", "gap_max",
    "gap_fraction_gt255", "a0_bytes", "a2_bytes", "beicsr_anchor_bytes",
    "beicsr_target_bytes", "delta_bytes", "selected_target_format", "fallback",
    "boundary_support", "exact_density_preserved", "input_sha256",
]


def _pct(values: np.ndarray, q: float) -> float:
    return float(np.percentile(values, q)) if values.size else 0.0


def _exact_count_null(target: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    result = np.zeros_like(target)
    for row, count in enumerate(target.sum(axis=1, dtype=np.int64)):
        if count:
            result[row, rng.choice(target.shape[1], size=int(count), replace=False)] = True
    return result


def _metrics(
    *, run_id: str, dataset: str, model: str, seed: int, layer: int,
    target_layer: int, tile: int, feature_slice: int, width: int,
    control: str, anchor: np.ndarray, target: np.ndarray,
    anchor_codes: tuple[Any, Any, Any], boundary: bool,
) -> dict[str, Any]:
    delta = np.logical_xor(anchor, target)
    intersection = int(np.logical_and(anchor, target).sum())
    union = int(np.logical_or(anchor, target).sum())
    row_events = delta.sum(axis=1, dtype=np.int64)
    events = np.flatnonzero(delta.reshape(-1))
    gaps = np.diff(events)
    a0, a2, beic_anchor = anchor_codes
    beic_target = serialize_record(target, Codec.BEICSR)
    delta_record = serialize_record(delta, Codec.DELTA)
    selected = "DELTA" if delta_record.unpadded_bytes < beic_target.unpadded_bytes else "BEICSR"
    return {
        "run_id": run_id, "dataset": dataset, "model": model, "seed": seed, "layer": layer,
        "target_layer": target_layer, "tile": tile, "slice": feature_slice, "slice_width": width,
        "control_type": control, "density_l": float(anchor.mean()), "density_target": float(target.mean()),
        "xor_density": float(delta.mean()), "hamming_similarity": float(1 - delta.mean()),
        "jaccard_similarity": intersection / union if union else 1.0,
        "intersection_count": intersection, "union_count": union,
        "row_events_mean": float(row_events.mean()), "row_events_p50": _pct(row_events, 50),
        "row_events_p95": _pct(row_events, 95), "row_events_max": int(row_events.max(initial=0)),
        "flattened_delta_events": len(events), "gap_mean": float(gaps.mean()) if gaps.size else 0.0,
        "gap_p50": _pct(gaps, 50), "gap_p90": _pct(gaps, 90), "gap_max": int(gaps.max(initial=0)),
        "gap_fraction_gt255": float((gaps > 255).mean()) if gaps.size else 0.0,
        "a0_bytes": a0.padded_bytes, "a2_bytes": a2.padded_bytes,
        "beicsr_anchor_bytes": beic_anchor.padded_bytes, "beicsr_target_bytes": beic_target.padded_bytes,
        "delta_bytes": delta_record.padded_bytes, "selected_target_format": selected,
        "fallback": selected == "BEICSR", "boundary_support": boundary,
        "exact_density_preserved": int(target.sum()),
        "input_sha256": hashlib.sha256(np.packbits(np.stack((anchor, target))).tobytes()).hexdigest(),
    }


def characterize(
    *, project: Path, config_id: str, output: Path, slice_width: int = 128,
    tile_rows: int = 128, include_controls: bool = True,
) -> list[dict[str, Any]]:
    trace = project / "artifacts_hpca_xorflow" / "workloads" / config_id / "fp8_supports.npz"
    if not trace.exists(): trace = project / "artifacts_final8" / "masks" / f"{config_id}_fp8_supports.npz"
    supports = unpack_supports(trace)
    _, data, dataset = _case(project, config_id)
    if dataset == "Data": dataset = config_id.split("_", 1)[0].title()
    _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    record_path = project / "artifacts_hpca_xorflow" / "workloads" / config_id / "record.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {"seed": 7, "model_kind": config_id.rsplit("_", 1)[-1]}
    seed = int(record.get("seed", 7)); model = str(record.get("model_kind", "deepres_v2"))
    rows: list[dict[str, Any]] = []
    for layer in range(len(supports) - 1):
        for tile, start in enumerate(range(0, len(order), tile_rows)):
            nodes = order[start:min(len(order), start + tile_rows)]
            for feature_slice, col in enumerate(range(0, supports.shape[2], slice_width)):
                stop = min(supports.shape[2], col + slice_width)
                anchor = supports[layer, nodes, col:stop]
                target = supports[layer + 1, nodes, col:stop]
                anchor_codes = (
                    serialize_record(anchor, Codec.A0), serialize_record(anchor, Codec.A2),
                    serialize_record(anchor, Codec.BEICSR),
                )
                cases: list[tuple[str, int, np.ndarray]] = [("real_adjacent", layer + 1, target)]
                if include_controls:
                    rng = np.random.default_rng(7007 + layer * 1_000_003 + tile * 101 + feature_slice)
                    cases.extend([
                        ("row_permutation", layer + 1, target[rng.permutation(len(target))]),
                        ("feature_permutation", layer + 1, target[:, rng.permutation(target.shape[1])]),
                        ("exact_count_independent", layer + 1, _exact_count_null(target, rng)),
                    ])
                    if layer + 2 < len(supports):
                        cases.append(("nonadjacent_l_plus_2", layer + 2, supports[layer + 2, nodes, col:stop]))
                for control, target_layer, controlled in cases:
                    rows.append(_metrics(
                        run_id=config_id, dataset=dataset, model=model, seed=seed, layer=layer,
                        target_layer=target_layer, tile=tile, feature_slice=feature_slice,
                        width=stop - col, control=control, anchor=anchor, target=controlled,
                        anchor_codes=anchor_codes, boundary=layer == 0 or target_layer == len(supports) - 1,
                    ))
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS); writer.writeheader(); writer.writerows(rows)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--no-controls", action="store_true")
    args = parser.parse_args()
    rows = characterize(project=args.project.resolve(), config_id=args.config_id, output=args.output, slice_width=args.slice_width, tile_rows=args.tile_rows, include_controls=not args.no_controls)
    print(json.dumps({"rows": len(rows), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
