#!/usr/bin/env python3
"""Emit exact selected ablation records without rerunning cache simulation.

The selected width for each variant is read from the already completed common-
accounting campaign.  Only the support serializer is replayed at those widths;
no graph-edge or cache traffic is recomputed.  This is the bounded path used
to feed variants into the final causal scheduler.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.hpca_xorflow_cli import _case
from xorflow.ablation import VARIANTS, _choice, _choose_precomputed, _rle_choice
from xorflow.online_replay import unpack_supports
from xorflow.serializer import Codec, serialize_record


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as h:
        return list(csv.DictReader(h))


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--config-id", required=True)
    p.add_argument("--aggregate", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()
    project = args.project.resolve(); config = args.config_id
    summary = read(args.aggregate)
    selected_width: dict[str, int] = {}
    for variant in VARIANTS:
        candidates = [r for r in summary if r["variant"] == variant]
        if candidates:
            best = min(candidates, key=lambda r: (float(r["cycles"]), int(r["slice_width"])))
            selected_width[variant] = int(best["slice_width"])
    trace = project / "artifacts_hpca_xorflow/workloads" / config / "fp8_supports.npz"
    if not trace.exists(): trace = project / "artifacts_final8/masks" / f"{config}_fp8_supports.npz"
    supports = unpack_supports(trace)
    _, data, dataset = _case(project, config)
    _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    rec_path = project / "artifacts_hpca_xorflow/workloads" / config / "record.json"
    meta = json.loads(rec_path.read_text()) if rec_path.exists() else {"seed": 7, "model_kind": config}
    output: dict[str, list[dict[str, object]]] = {v: [] for v in selected_width}
    by_width: dict[int, list[str]] = {}
    for variant, width in selected_width.items(): by_width.setdefault(width, []).append(variant)
    for width, variants in by_width.items():
        for layer, mask in enumerate(supports):
            for tile, start in enumerate(range(0, len(order), 128)):
                nodes = order[start:min(len(order), start + 128)]
                for sid, col in enumerate(range(0, mask.shape[1], width)):
                    stop = min(mask.shape[1], col + width); local = mask[nodes, col:stop]
                    choices = {"BEICSR": _choice(serialize_record(local, Codec.BEICSR)),
                               "A0": _choice(serialize_record(local, Codec.A0)),
                               "A2": _choice(serialize_record(local, Codec.A2))}
                    other = None
                    if layer % 2 == 1: other = supports[layer - 1, nodes, col:stop]
                    elif layer + 1 < len(supports): other = supports[layer + 1, nodes, col:stop]
                    if other is not None:
                        delta = np.logical_xor(local, other)
                        choices["DELTA"] = _choice(serialize_record(delta, Codec.DELTA))
                        choices["RLE"] = _rle_choice(delta)
                        choices["PAIR_BEICSR"] = _choice(serialize_record(other, Codec.BEICSR))
                        if layer % 2 == 1:
                            choices["PAIR_A0"] = _choice(serialize_record(other, Codec.A0))
                            choices["PAIR_A2"] = _choice(serialize_record(other, Codec.A2))
                    for variant in variants:
                        choice = _choose_precomputed(variant, layer, choices)
                        output[variant].append({
                            "run_id": config, "dataset": dataset, "model": meta.get("model_kind", config),
                            "seed": meta.get("seed", 7), "layer": layer, "tile": tile, "slice": sid,
                            "pair_id": layer // 2, "role": "anchor" if layer % 2 == 0 else "target",
                            "chosen_format": "DELTA" if choice.name in {"DELTA", "GENERIC_RLE"} else choice.name,
                            "payload_bits": choice.payload_bits, "header_bits": 16,
                            "unpadded_bytes": choice.unpadded_bytes, "padded_bytes": choice.padded_bytes,
                            "input_support_bits": int(local.size), "rows": len(nodes), "features": stop - col,
                            "anchor_read_bytes": 0, "consumer_anchor_read_bytes": 0,
                            "consumer_anchor_decode_cycles": 0,
                        })
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for variant, out_rows in output.items():
        path = args.output_dir / f"{config}_{variant}.csv"
        with path.open("w", newline="") as h:
            writer = csv.DictWriter(h, fieldnames=list(out_rows[0])); writer.writeheader(); writer.writerows(out_rows)
    print(json.dumps({"config_id": config, "variants": len(output), "records": sum(len(x) for x in output.values())}, sort_keys=True))


if __name__ == "__main__":
    main()
