"""Density-preserving temporal and node-identity null controls."""

import numpy as np


def temporal_order_null(masks: np.ndarray, seed: int = 7007) -> np.ndarray:
    return masks[np.random.default_rng(seed).permutation(len(masks))].copy()


def density_matched_independent_null(
    masks: np.ndarray, seed: int = 7007
) -> np.ndarray:
    """Preserve each layer-feature marginal while destroying dependence."""
    rng = np.random.default_rng(seed)
    output = np.empty_like(masks)
    for layer in range(len(masks)):
        probabilities = masks[layer].mean(axis=0)
        output[layer] = rng.random(masks[layer].shape) < probabilities
    return output


def node_permutation_null(masks: np.ndarray, seed: int = 7007) -> np.ndarray:
    rng = np.random.default_rng(seed)
    output = masks.copy()
    for layer in range(len(output)):
        output[layer] = output[layer, rng.permutation(output.shape[1])]
    return output


def temporal_flip(masks: np.ndarray) -> float:
    if len(masks) < 2:
        return 0.0
    return float(np.logical_xor(masks[:-1], masks[1:]).mean())

