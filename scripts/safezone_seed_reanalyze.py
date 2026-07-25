#!/usr/bin/env python3
"""Reanalyze saved seed checkpoints without retraining."""
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from mosaic_validation.datasets import load_dataset
from mosaic_validation.graph_order import symmetrized_edges_and_rcm, tiles_from_order
from mosaic_validation.int8_validation import classification_accuracy, make_int8_model
from mosaic_validation.models import build_deepres_v2, build_model
from safezone_seed_runs import _performance, _support


ROOT = Path(__file__).resolve().parents[1]
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def main():
    old = pd.read_csv(ROOT / "results_safezone/53_cross_seed_validation.csv")
    rows = []
    for row in old.itertuples():
        kind = "deepres" if "deepres" in row.config_id else "gcnii"
        dataset_name = "PubMed" if "pubmed" in row.config_id else "Cora"
        data, _, classes = load_dataset(dataset_name, ROOT / "data")
        if kind == "deepres":
            model = build_deepres_v2(data.num_features, 128, classes, 28, .20, .20)
        else:
            model = build_model("gcnii", data.num_features, 64, classes, 16, .50)
        checkpoint = torch.load(
            ROOT / f"artifacts_safezone/seeds/{row.config_id}_seed{row.seed}.pt",
            map_location="cpu", weights_only=False,
        )
        model.load_state_dict(checkpoint["model_state"])
        fp32 = classification_accuracy(model, data, DEVICE)
        fp8_model = make_int8_model(model, value_format="fp8")
        fp8 = classification_accuracy(fp8_model, data, DEVICE)
        z = np.load(
            ROOT / f"artifacts_safezone/seeds/{row.config_id}_seed{row.seed}_supports.npz"
        )
        shape = tuple(int(x) for x in z["shape"])
        masks = np.unpackbits(z["packed"], axis=2)[:, :, : shape[2]].astype(bool)
        segment = masks[3:]
        _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(rcm, 128)
        anchor_bits, layer_bits, exact = _support(segment, tiles)
        raw, selected, overlapped = _performance(
            row.config_id, masks, data, anchor_bits, layer_bits
        )
        values = row._asdict()
        values.update(
            fp32_test_accuracy=fp32["test_accuracy"],
            fp8_test_accuracy=fp8["test_accuracy"],
            raw_serialized_speedup=raw,
            selected_speedup=selected,
            overlapped_speedup=max(1.0, overlapped),
            exactness_pass=exact,
        )
        rows.append(values)
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results_safezone/53_cross_seed_validation.csv", index=False)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
