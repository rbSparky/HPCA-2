"""Memory-safe PyG dataset loading."""

from pathlib import Path

import torch
from torch_geometric.data import Data
from torch_geometric.datasets import Planetoid, WikipediaNetwork
from torch_geometric.transforms import NormalizeFeatures


def load_dataset(name: str, root: Path) -> tuple[Data, int, int]:
    if name.lower() == "chameleon":
        dataset = WikipediaNetwork(
            root=str(root / "chameleon"),
            name="chameleon",
            geom_gcn_preprocess=True,
            transform=NormalizeFeatures(),
        )
    else:
        dataset = Planetoid(
            root=str(root / name.lower()),
            name=name,
            transform=NormalizeFeatures(),
        )
    data = dataset[0]
    if data.train_mask.ndim == 2:
        data.train_mask = data.train_mask[:, 0]
        data.val_mask = data.val_mask[:, 0]
        data.test_mask = data.test_mask[:, 0]
    for key in ("train_mask", "val_mask", "test_mask"):
        setattr(data, key, getattr(data, key).to(torch.bool))
    return data, int(dataset.num_features), int(dataset.num_classes)

