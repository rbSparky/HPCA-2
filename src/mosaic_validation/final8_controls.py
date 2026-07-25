"""Matched-density structural controls for the final FP8 XORFLOW result."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

from .datasets import load_dataset
from .final8_cli import _encode_support
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .null_controls import density_matched_independent_null, node_permutation_null


def _load(path: Path) -> np.ndarray:
    with np.load(path) as data:
        layers, nodes, features = map(int, data["shape"])
        return np.unpackbits(data["packed"], axis=2)[:, :, :features].astype(bool)


def run(project: Path):
    summary = pd.read_csv(project / "results_final8/48_final8_summary.csv").set_index(
        "config_id"
    )
    rows = []
    for cid, dataset in [
        ("cora_gcnii16", "Cora"),
        ("pubmed_gcnii16", "PubMed"),
        ("cora_deepres28_w128", "Cora"),
        ("chameleon_gcnii16", "chameleon"),
    ]:
        masks = _load(project / f"artifacts_final8/masks/{cid}_fp8_supports.npz")
        segment = masks[3 : min(28 if "deepres" in cid else 16, len(masks))]
        data, _, _ = load_dataset(dataset, project / "data")
        _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(order, 128)
        width = int(summary.loc[cid].best_slice_width)
        controls = {
            "real_fp8": segment,
            "density_matched_independent": density_matched_independent_null(
                segment, 7007
            ),
            "node_permuted": node_permutation_null(segment, 7007),
        }
        ratios = {}
        for name, support in controls.items():
            encoded = _encode_support(support, tiles, width)
            ratio = (
                encoded["anchor_bits"] + int(encoded["layer_bits"].sum())
            ) / support.size
            ratios[name] = ratio
            rows.append({
                "config_id": cid,
                "control_type": name,
                "density": float(support.mean()),
                "support_ratio_to_beicsr": ratio,
                "metadata_reduction": 1 - ratio,
                "exact_decode_pass": encoded["exact"],
            })
        for row in rows:
            if row["config_id"] == cid:
                row["control_support_ratio_over_real"] = (
                    ratios[row["control_type"]] / ratios["real_fp8"]
                )
                row["real_support_ratio_advantage"] = (
                    ratios[row["control_type"]] - ratios["real_fp8"]
                )
    frame = pd.DataFrame(rows)
    frame.to_csv(project / "results_final8/50_fp8_null_controls.csv", index=False)
    print(frame.to_string(index=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path("."))
    run(parser.parse_args().project.resolve())


if __name__ == "__main__":
    main()
