"""Exact template cohorts and deterministic grouping methods."""

from dataclasses import dataclass
from math import ceil

import numpy as np


@dataclass
class CohortSet:
    groups: list[np.ndarray]
    templates: list[np.ndarray]


def optimal_template(rows: np.ndarray) -> np.ndarray:
    """Return the exact per-feature optimum for 4-byte core, 6-byte residual."""
    if rows.shape[0] == 0:
        return np.zeros(rows.shape[1], dtype=np.bool_)
    counts = rows.sum(axis=0)
    return (4 * rows.shape[0] + 2) < (6 * counts)


def _from_groups(mask: np.ndarray, groups: list[np.ndarray]) -> CohortSet:
    return CohortSet(groups, [optimal_template(mask[group]) for group in groups])


def random_balanced(mask: np.ndarray, cohort_size: int, seed: int) -> CohortSet:
    order = np.random.default_rng(seed).permutation(mask.shape[0])
    groups = [order[i : i + cohort_size] for i in range(0, len(order), cohort_size)]
    return _from_groups(mask, groups)


def rcm_contiguous(mask: np.ndarray, tiles: list[np.ndarray], cohort_size: int) -> CohortSet:
    groups = [
        tile[start : start + cohort_size]
        for tile in tiles
        for start in range(0, len(tile), cohort_size)
    ]
    return _from_groups(mask, groups)


def _seed_rows(mask: np.ndarray, nodes: np.ndarray, k: int) -> list[int]:
    local = mask[nodes]
    counts = local.sum(axis=1)
    median = np.median(counts)
    candidates = np.flatnonzero(np.abs(counts - median) == np.min(np.abs(counts - median)))
    first = int(candidates[np.argmin(nodes[candidates])])
    seeds = [first]
    while len(seeds) < k:
        distances = np.logical_xor(local[:, None, :], local[np.asarray(seeds)][None, :, :]).sum(axis=2)
        nearest = distances.min(axis=1)
        nearest[np.asarray(seeds)] = -1
        best = np.flatnonzero(nearest == nearest.max())
        seeds.append(int(best[np.argmin(nodes[best])]))
    return seeds


def _cluster_tile(mask: np.ndarray, nodes: np.ndarray, cohort_size: int) -> list[np.ndarray]:
    k = min(4, ceil(len(nodes) / cohort_size))
    seeds = _seed_rows(mask, nodes, k)
    templates = [mask[nodes[index]].copy() for index in seeds]
    previous: np.ndarray | None = None
    assignment = np.zeros(len(nodes), dtype=np.int64)
    capacity = ceil(len(nodes) / k)
    for _ in range(5):
        costs = np.empty((len(nodes), k), dtype=np.int64)
        for group_index, template in enumerate(templates):
            costs[:, group_index] = 4 * int(template.sum()) + 6 * np.logical_and(
                mask[nodes], ~template
            ).sum(axis=1)
        sorted_choices = np.argsort(costs, axis=1, kind="stable")
        margins = costs[np.arange(len(nodes)), sorted_choices[:, 1]] - costs[
            np.arange(len(nodes)), sorted_choices[:, 0]
        ] if k > 1 else np.zeros(len(nodes), dtype=np.int64)
        row_order = sorted(range(len(nodes)), key=lambda i: (-int(margins[i]), int(nodes[i])))
        remaining = np.full(k, capacity, dtype=np.int64)
        for row in row_order:
            for choice in sorted_choices[row]:
                if remaining[choice] > 0:
                    assignment[row] = choice
                    remaining[choice] -= 1
                    break
        if previous is not None and np.array_equal(previous, assignment):
            break
        previous = assignment.copy()
        templates = [
            optimal_template(mask[nodes[assignment == group_index]]) for group_index in range(k)
        ]
    return [nodes[assignment == group_index] for group_index in range(k)]


def rcm_cost_cluster(mask: np.ndarray, tiles: list[np.ndarray], cohort_size: int) -> CohortSet:
    groups = [group for tile in tiles for group in _cluster_tile(mask, tile, cohort_size)]
    return _from_groups(mask, groups)


def global_lsh_oracle(mask: np.ndarray, cohort_size: int, seed: int) -> CohortSet:
    rng = np.random.default_rng(seed)
    projection = rng.choice(np.asarray([-1, 1], dtype=np.int16), size=(mask.shape[1], 16))
    scores = (mask.astype(np.int16) * 2 - 1) @ projection
    bits = scores >= 0
    signatures = (bits.astype(np.uint32) * (1 << np.arange(16, dtype=np.uint32))).sum(axis=1)
    nodes = np.arange(mask.shape[0], dtype=np.int64)
    order = np.lexsort((nodes, mask.sum(axis=1), signatures))
    groups = [order[i : i + cohort_size] for i in range(0, len(order), cohort_size)]
    return _from_groups(mask, groups)

