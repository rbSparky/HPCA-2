"""Persistent topology-local window cohort construction."""

from dataclasses import dataclass
from math import ceil

import numpy as np

from .cohorts import rcm_cost_cluster
from .delta_encoding import (
    ABSENT,
    DELTA_DICTIONARY,
    REGULAR_CORE,
    choose_plane_mode,
)


@dataclass
class WindowGroups:
    groups: list[np.ndarray]
    objective_history: list[float]


def _split(order: np.ndarray, cohort_size: int) -> list[np.ndarray]:
    return [order[start : start + cohort_size] for start in range(0, len(order), cohort_size)]


def random_balanced_window(
    tiles: list[np.ndarray], cohort_size: int, seed: int
) -> WindowGroups:
    rng = np.random.default_rng(seed)
    groups = [group for tile in tiles for group in _split(rng.permutation(tile), cohort_size)]
    return WindowGroups(groups, [])


def rcm_contiguous_window(tiles: list[np.ndarray], cohort_size: int) -> WindowGroups:
    return WindowGroups([group for tile in tiles for group in _split(tile, cohort_size)], [])


def first_layer_rcm_cost_reused(
    window: np.ndarray, tiles: list[np.ndarray], cohort_size: int
) -> WindowGroups:
    # Phase-0 clustering has at most four cohorts per tile. Split larger sweep
    # tiles into topology-contiguous initialization tiles so capacity remains
    # legal for every requested cohort size.
    init_tiles = [
        tile[start : start + 4 * cohort_size]
        for tile in tiles
        for start in range(0, len(tile), 4 * cohort_size)
    ]
    fitted = rcm_cost_cluster(window[0], init_tiles, cohort_size)
    return WindowGroups(fitted.groups, [])


def _raw_objective(
    window: np.ndarray,
    groups: list[np.ndarray],
    rho_delta: float,
    decode_width_bits: int,
) -> float:
    objective = float(len(groups))  # gamma = 1 cycle-equivalent per cohort.
    for group in groups:
        cohort = window[:, group, :]
        modes, metadata_bits = _modes_and_metadata(
            cohort, rho_delta, decode_width_bits
        )
        regular = modes == REGULAR_CORE
        delta = modes == DELTA_DICTIONARY
        objective += window.shape[0] * len(group) * int(regular.sum())
        objective += rho_delta * float(cohort[:, :, delta].sum())
        objective += float(np.ceil(metadata_bits[delta].sum() / decode_width_bits))
    return objective


def _modes_and_metadata(
    cohort: np.ndarray,
    rho_delta: float,
    decode_width_bits: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Vectorized exact finite mode selection for every feature plane."""
    layers, lanes, width = cohort.shape
    active = cohort.sum(axis=(0, 1))
    dense_transition_bytes = ceil(lanes / 8)
    if layers > 1:
        flips = np.logical_xor(cohort[:-1], cohort[1:]).sum(axis=1)
        transition_bytes = np.minimum(dense_transition_bytes, 1 + flips).sum(axis=0)
    else:
        transition_bytes = np.zeros(width, dtype=np.int64)
    metadata_bits = 16 + 8 * ceil(lanes / 8) + 8 * transition_bytes
    regular_cost = layers * lanes
    delta_cost = rho_delta * active + np.ceil(metadata_bits / decode_width_bits)
    modes = np.full(width, DELTA_DICTIONARY, dtype=object)
    modes[regular_cost <= delta_cost] = REGULAR_CORE
    modes[active == 0] = ABSENT
    return modes, metadata_bits


def _group_modes(
    window: np.ndarray,
    group: np.ndarray,
    rho_delta: float,
    decode_width_bits: int,
) -> np.ndarray:
    return _modes_and_metadata(
        window[:, group, :], rho_delta, decode_width_bits
    )[0]


def _node_cost(
    node_trace: np.ndarray,
    modes: np.ndarray,
    rho_delta: float,
    decode_width_bits: int,
) -> float:
    active_by_feature = node_trace.sum(axis=0)
    flips_by_feature = np.logical_xor(node_trace[:-1], node_trace[1:]).sum(axis=0)
    regular = modes == REGULAR_CORE
    delta = modes == DELTA_DICTIONARY
    absent_activated = (modes == ABSENT) & (active_by_feature > 0)
    cost = node_trace.shape[0] * int(regular.sum())
    cost += rho_delta * float(active_by_feature[delta | absent_activated].sum())
    cost += float(flips_by_feature[delta | absent_activated].sum()) / decode_width_bits
    return cost


def window_cost_cluster(
    window: np.ndarray,
    tiles: list[np.ndarray],
    cohort_size: int,
    rho_delta: float = 1.25,
    decode_width_bits: int = 64,
    max_iterations: int = 6,
) -> WindowGroups:
    """Alternating deterministic assignment with a monotone acceptance guard."""
    current = first_layer_rcm_cost_reused(window, tiles, cohort_size).groups
    history = [_raw_objective(window, current, rho_delta, decode_width_bits)]
    # Preserve per-tile optimization: group counts are known from capacity.
    group_offset = 0
    for _ in range(max_iterations):
        proposed: list[np.ndarray] = []
        changed = False
        group_offset = 0
        for tile in tiles:
            k = ceil(len(tile) / cohort_size)
            tile_groups = current[group_offset : group_offset + k]
            group_offset += k
            modes = [
                _group_modes(window, group, rho_delta, decode_width_bits)
                for group in tile_groups
            ]
            active = window[:, tile, :].sum(axis=0).astype(float)
            flips = np.logical_xor(
                window[:-1, tile, :], window[1:, tile, :]
            ).sum(axis=0).astype(float)
            costs = np.empty((len(tile), k), dtype=float)
            for index, mode in enumerate(modes):
                regular = mode == REGULAR_CORE
                nonregular = ~regular
                costs[:, index] = window.shape[0] * int(regular.sum())
                costs[:, index] += rho_delta * (active[:, nonregular].sum(axis=1))
                costs[:, index] += (
                    flips[:, nonregular].sum(axis=1) / decode_width_bits
                )
            choices = np.argsort(costs, axis=1, kind="stable")
            margins = (
                costs[np.arange(len(tile)), choices[:, 1]]
                - costs[np.arange(len(tile)), choices[:, 0]]
                if k > 1
                else np.zeros(len(tile))
            )
            order = sorted(range(len(tile)), key=lambda i: (-margins[i], int(tile[i])))
            capacity = ceil(len(tile) / k)
            remaining = np.full(k, capacity, dtype=np.int64)
            assignment = np.empty(len(tile), dtype=np.int64)
            for row in order:
                for candidate in choices[row]:
                    if remaining[candidate]:
                        assignment[row] = candidate
                        remaining[candidate] -= 1
                        break
            new_tile_groups = [tile[assignment == index] for index in range(k)]
            proposed.extend(new_tile_groups)
            changed |= any(
                not np.array_equal(np.sort(a), np.sort(b))
                for a, b in zip(tile_groups, new_tile_groups, strict=True)
            )
        if not changed:
            break
        objective = _raw_objective(window, proposed, rho_delta, decode_width_bits)
        # Balanced reassignment is approximate; accept only exact objective
        # descent, which makes the optimizer scientifically auditable.
        if objective > history[-1] + 1e-9:
            break
        history.append(objective)
        current = proposed
        if history[-2] - history[-1] <= 1e-5 * max(history[-2], 1.0):
            break
    assert all(b <= a + 1e-9 for a, b in zip(history, history[1:]))
    return WindowGroups(current, history)


def window_global_oracle(
    window: np.ndarray, cohort_size: int, seed: int
) -> WindowGroups:
    nodes = window.shape[1]
    flattened = window.transpose(1, 0, 2).reshape(nodes, -1).astype(np.int16) * 2 - 1
    projection = np.random.default_rng(seed).choice(
        np.asarray([-1, 1], dtype=np.int16), size=(flattened.shape[1], 16)
    )
    bits = flattened @ projection >= 0
    signatures = (bits.astype(np.uint32) * (1 << np.arange(16, dtype=np.uint32))).sum(axis=1)
    node_ids = np.arange(nodes, dtype=np.int64)
    nnz = window.sum(axis=(0, 2))
    order = np.lexsort((node_ids, nnz, signatures))
    return WindowGroups(_split(order, cohort_size), [])


def build_window_groups(
    method: str,
    window: np.ndarray,
    tiles: list[np.ndarray],
    cohort_size: int,
    seed: int,
    rho_delta: float = 1.25,
    decode_width_bits: int = 64,
) -> WindowGroups:
    if method == "random_balanced_window":
        return random_balanced_window(tiles, cohort_size, seed)
    if method == "rcm_contiguous_window":
        return rcm_contiguous_window(tiles, cohort_size)
    if method == "first_layer_rcm_cost_reused":
        return first_layer_rcm_cost_reused(window, tiles, cohort_size)
    if method == "window_global_oracle":
        return window_global_oracle(window, cohort_size, seed)
    if method == "window_cost_cluster":
        return window_cost_cluster(
            window, tiles, cohort_size, rho_delta, decode_width_bits
        )
    raise ValueError(f"Unknown grouping method: {method}")
