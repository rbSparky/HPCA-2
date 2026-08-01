"""Spatial pair sampling and normalized Hamming metrics."""

import numpy as np


def _distinct_random_pairs(num_nodes: int, count: int, rng: np.random.Generator) -> np.ndarray:
    left = rng.integers(0, num_nodes, size=count, dtype=np.int64)
    right = rng.integers(0, num_nodes - 1, size=count, dtype=np.int64)
    right += right >= left
    return np.stack((left, right), axis=1)


def sample_pair_sets(
    edges: np.ndarray,
    tiles: list[np.ndarray],
    num_nodes: int,
    limit: int,
    seed: int,
) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    if len(edges) > limit:
        edge_pairs = edges[rng.choice(len(edges), limit, replace=False)]
    else:
        edge_pairs = edges
    usable = [tile for tile in tiles if len(tile) > 1]
    weights = np.asarray([len(tile) * (len(tile) - 1) for tile in usable], dtype=float)
    chosen = rng.choice(len(usable), size=limit, p=weights / weights.sum())
    local = np.empty((limit, 2), dtype=np.int64)
    for index, tile_index in enumerate(chosen):
        tile = usable[tile_index]
        a = int(rng.integers(0, len(tile)))
        b = int(rng.integers(0, len(tile) - 1))
        b += b >= a
        local[index] = tile[a], tile[b]
    return {
        "edge": edge_pairs,
        "local": local,
        "random": _distinct_random_pairs(num_nodes, limit, rng),
    }


def pair_mismatches(mask: np.ndarray, pairs: np.ndarray) -> np.ndarray:
    if len(pairs) == 0:
        return np.asarray([], dtype=float)
    return np.logical_xor(mask[pairs[:, 0]], mask[pairs[:, 1]]).mean(axis=1)


def mean_ci(values: np.ndarray, replicates: int, seed: int) -> tuple[float, float, float]:
    if values.size == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(values.mean())
    rng = np.random.default_rng(seed)
    boot = np.empty(replicates, dtype=float)
    for index in range(replicates):
        boot[index] = values[rng.integers(0, len(values), size=len(values))].mean()
    low, high = np.quantile(boot, [0.025, 0.975])
    return mean, float(low), float(high)


def marginal_entropy(mask: np.ndarray) -> float:
    p = mask.mean(axis=0)
    valid = (p > 0) & (p < 1)
    entropy = np.zeros_like(p, dtype=float)
    entropy[valid] = -(p[valid] * np.log2(p[valid]) + (1 - p[valid]) * np.log2(1 - p[valid]))
    return float(entropy.mean())

