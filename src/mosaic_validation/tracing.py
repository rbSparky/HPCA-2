"""Exact post-ReLU support tracing and compact storage."""

from pathlib import Path

import numpy as np
import torch


@torch.no_grad()
def capture_masks(model, data, device: torch.device) -> tuple[list[np.ndarray], float]:
    import time

    start = time.monotonic()
    model.eval()
    _, activations = model(data.x.to(device), data.edge_index.to(device), trace=True)
    masks = [(value > 0).detach().cpu().numpy().astype(np.bool_) for value in activations]
    return masks, time.monotonic() - start


def save_masks(masks: list[np.ndarray], directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for layer, mask in enumerate(masks, 1):
        np.savez_compressed(
            directory / f"layer_{layer:02d}.npz",
            packed=np.packbits(mask, axis=1),
            shape=np.asarray(mask.shape, dtype=np.int64),
            row_nnz=mask.sum(axis=1).astype(np.int16),
            density=np.asarray(mask.mean(), dtype=np.float32),
        )

