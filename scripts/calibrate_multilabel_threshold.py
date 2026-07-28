#!/usr/bin/env python3
"""Validation-only output-threshold calibration for a completed multi-label run."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from mosaic_validation.datasets import load_dataset
from mosaic_validation.hpca_sparse import deepres_csr_forward, normalized_csr_adjacency
from mosaic_validation.int8_validation import make_int8_model
from mosaic_validation.models import build_deepres_v2


def micro_f1(logits: torch.Tensor, labels: torch.Tensor, mask: torch.Tensor, threshold: float) -> float:
    predicted = logits[mask] > threshold
    truth = labels[mask] > 0.5
    tp = int((predicted & truth).sum())
    fp = int((predicted & ~truth).sum())
    fn = int((~predicted & truth).sum())
    return (2.0 * tp) / max(2 * tp + fp + fn, 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    args = parser.parse_args()
    project = args.project.resolve()
    root = project / "artifacts_hpca_xorflow/workloads" / args.config_id
    payload = torch.load(root / "model.pt", map_location="cpu", weights_only=False)
    config = payload["config"]
    data, features, classes = load_dataset(config["dataset"], project / "data")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_deepres_v2(features, config["width"], classes, config["layers"], config["dropout"], config["residual_scale"])
    model.load_state_dict(payload["model_state"]); model.to(device).eval()
    adjacency = normalized_csr_adjacency(data.edge_index, data.num_nodes, device)
    x = data.x.to(device); labels = data.y.to(device); masks = {key: getattr(data, f"{key}_mask").to(device) for key in ("val", "test")}
    with torch.no_grad():
        logits = deepres_csr_forward(model, x, adjacency)
    thresholds = np.linspace(-2.0, 2.0, 33)
    values = [(float(value), micro_f1(logits, labels, masks["val"], float(value))) for value in thresholds]
    threshold, val_f1 = max(values, key=lambda item: (item[1], -abs(item[0]), -item[0]))
    fp32_test = micro_f1(logits, labels, masks["test"], threshold)
    fp8_model = make_int8_model(model.cpu(), value_format="fp8", weight_format="fp16").to(device).eval()
    with torch.no_grad():
        fp8_logits = deepres_csr_forward(fp8_model, x, adjacency, fp8=True)
    fp8_test = micro_f1(fp8_logits, labels, masks["test"], threshold)
    result = {"config_id": args.config_id, "selection_split": "validation", "threshold_grid": [float(x) for x in thresholds], "selected_logit_threshold": threshold, "validation_micro_f1": val_f1, "fp32_test_micro_f1": fp32_test, "fp8_fp16_test_micro_f1": fp8_test, "accuracy_drop": fp32_test - fp8_test}
    (root / "threshold_calibration.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
