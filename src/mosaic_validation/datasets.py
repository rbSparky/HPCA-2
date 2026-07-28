"""Memory-safe PyG dataset loading."""

from pathlib import Path

import torch
from torch_geometric.data import Data
from torch_geometric.datasets import Flickr, Planetoid, Reddit, WikipediaNetwork, Yelp
from torch_geometric.transforms import NormalizeFeatures


def load_dataset(name: str, root: Path) -> tuple[Data, int, int]:
    normalized = name.lower().replace("-", "_")
    if normalized == "chameleon":
        dataset = WikipediaNetwork(
            root=str(root / "chameleon"),
            name="chameleon",
            geom_gcn_preprocess=True,
            transform=NormalizeFeatures(),
        )
    elif normalized == "reddit":
        # These benchmark features are already standardized dense vectors.
        # Applying row-sum normalization destroys their native scale (mean
        # magnitude falls from ~0.68 to ~0.0017 on Reddit) and prevents the
        # classifier from learning.  Retain the published preprocessing.
        dataset = Reddit(root=str(root / "reddit"))
    elif normalized == "flickr":
        dataset = Flickr(root=str(root / "flickr"))
    elif normalized == "yelp":
        dataset = Yelp(root=str(root / "yelp"))
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
