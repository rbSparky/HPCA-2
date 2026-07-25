#!/usr/bin/env python3
"""One larger-graph transfer run on OGBN-Arxiv."""
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch
import torch_geometric.transforms as T
from torch_geometric.utils import to_torch_csr_tensor
from ogb.nodeproppred import PygNodePropPredDataset

from mosaic_validation.int8_validation import classification_accuracy, make_int8_model
from mosaic_validation.models import build_deepres_v2
from mosaic_validation.reproducibility import seed_everything
from mosaic_validation.training import train_model


ROOT = Path(__file__).resolve().parents[1]


def main():
    seed_everything(7)
    # OGB 1.3.6 predates PyTorch 2.6's weights_only=True default. The file was
    # generated locally from the official OGB download, so explicitly use the
    # legacy trusted-object loader for this dataset constructor only.
    original_load = torch.load
    def trusted_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)
    torch.load = trusted_load
    dataset = PygNodePropPredDataset(
        name="ogbn-arxiv", root=str(ROOT / "data"), transform=T.ToUndirected()
    )
    torch.load = original_load
    data = dataset[0]
    data.y = data.y.view(-1)
    split = dataset.get_idx_split()
    for name in ("train", "valid", "test"):
        mask = torch.zeros(data.num_nodes, dtype=torch.bool)
        mask[split[name]] = True
        setattr(data, "val_mask" if name == "valid" else f"{name}_mask", mask)
    # Sparse adjoint avoids materializing a 2.3M-edge by hidden-width message
    # tensor in every layer.
    data.edge_index = to_torch_csr_tensor(
        data.edge_index.flip(0), size=(data.num_nodes, data.num_nodes)
    )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # The 16x64 edge-list implementation exceeds the available 8 GiB GPU. This
    # bounded transfer uses the existing exact pre-activation residual block
    # with sparse-CSR aggregation.
    model = build_deepres_v2(
        data.num_features, 128, dataset.num_classes, 8, .20, .20
    )
    cfg = SimpleNamespace(
        learning_rate=.005, weight_decay=.0005, max_epochs=220,
        min_epochs=60, validation_interval=2, patience_checks=30,
    )
    out = ROOT / "artifacts_safezone/ogbn_arxiv"
    out.mkdir(parents=True, exist_ok=True)
    result = train_model(model, data, device, cfg, 25, out / "model.pt")
    fp32 = classification_accuracy(model, data, device)
    for conv in model.convs:
        conv._cached_edge_index = None
        conv._cached_adj_t = None
    fp8_model = make_int8_model(model, value_format="fp8").to(device).eval()
    fp8 = classification_accuracy(fp8_model, data, device)
    with torch.no_grad():
        _, traces = fp8_model(data.x.to(device), data.edge_index.to(device), trace=True)
    masks = np.stack([(x > 0).cpu().numpy() for x in traces])
    np.savez_compressed(
        out / "supports.npz", packed=np.packbits(masks, axis=2),
        shape=np.asarray(masks.shape),
    )
    row = {
        "config_id": "ogbn_arxiv_deepres8_w128",
        "nodes": data.num_nodes,
        "edges": int(data.edge_index._nnz()),
        "epochs": result.epochs_completed,
        "best_epoch": result.best_epoch,
        "train_seconds": result.train_seconds,
        "fp32_test_accuracy": fp32["test_accuracy"],
        "fp8_test_accuracy": fp8["test_accuracy"],
        "accuracy_drop": fp32["test_accuracy"] - fp8["test_accuracy"],
        "median_density": float(np.median(masks[3:].mean(axis=(1, 2)))),
    }
    pd.DataFrame([row]).to_csv(ROOT / "results_safezone/58_ogbn_arxiv_quality.csv", index=False)
    print(row)


if __name__ == "__main__":
    main()
