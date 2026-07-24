"""Exact MOSAIC-Delta feature-plane encoding and cost accounting.

Logical byte streams are aligned once per cohort-window: regular feature IDs;
one regular value stream per layer; delta feature IDs; delta initial masks; one
delta-transition stream per transition; and one delta active-value stream per
layer. Individual features are never aligned separately.
"""

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np

from .analytical_cost import representation_metrics
from .cohorts import CohortSet

ABSENT = "ABSENT"
REGULAR_CORE = "REGULAR_CORE"
DELTA_DICTIONARY = "DELTA_DICTIONARY"


def align64(value: int) -> int:
    return int(math.ceil(value / 64) * 64) if value else 0


@dataclass(frozen=True)
class TransitionCode:
    dense: bool
    payload: bytes
    flip_count: int


def encode_transition(previous: np.ndarray, current: np.ndarray) -> TransitionCode:
    """Encode one exact lane-mask XOR using the cheaper legal byte stream."""
    xor = np.logical_xor(previous, current)
    flipped = np.flatnonzero(xor)
    dense_payload = np.packbits(xor, bitorder="little").tobytes()
    if len(flipped) > 255:
        return TransitionCode(True, dense_payload, len(flipped))
    sparse_payload = bytes([len(flipped)]) + bytes(flipped.tolist())
    if len(dense_payload) <= len(sparse_payload):
        return TransitionCode(True, dense_payload, len(flipped))
    return TransitionCode(False, sparse_payload, len(flipped))


def decode_transition(previous: np.ndarray, code: TransitionCode) -> np.ndarray:
    if code.dense:
        xor = np.unpackbits(
            np.frombuffer(code.payload, dtype=np.uint8), bitorder="little"
        )[: previous.size].astype(bool)
    else:
        count = code.payload[0]
        xor = np.zeros(previous.size, dtype=bool)
        if count:
            xor[np.frombuffer(code.payload[1 : 1 + count], dtype=np.uint8)] = True
    return np.logical_xor(previous, xor)


@dataclass
class PlaneEncoding:
    mode: str
    initial_mask: np.ndarray | None
    transitions: list[TransitionCode]


def choose_plane_mode(
    plane: np.ndarray,
    rho_delta: float = 1.25,
    decode_width_bits: int = 64,
) -> str:
    """Choose the finite legal mode minimizing the declared cycle proxy."""
    active = int(plane.sum())
    if active == 0:
        return ABSENT
    layers, lanes = plane.shape
    regular = layers * lanes
    transition_bits = sum(
        8 * len(encode_transition(plane[t - 1], plane[t]).payload)
        for t in range(1, layers)
    )
    metadata_bits = 16 + 8 * math.ceil(lanes / 8) + transition_bits
    delta = rho_delta * active + math.ceil(metadata_bits / decode_width_bits)
    return REGULAR_CORE if regular <= delta else DELTA_DICTIONARY


def encode_plane(
    plane: np.ndarray,
    rho_delta: float = 1.25,
    decode_width_bits: int = 64,
) -> PlaneEncoding:
    mode = choose_plane_mode(plane, rho_delta, decode_width_bits)
    if mode == ABSENT:
        return PlaneEncoding(mode, None, [])
    if mode == REGULAR_CORE:
        return PlaneEncoding(mode, None, [])
    return PlaneEncoding(
        mode,
        plane[0].copy(),
        [encode_transition(plane[t - 1], plane[t]) for t in range(1, len(plane))],
    )


def decode_plane(encoded: PlaneEncoding, layers: int, lanes: int) -> np.ndarray:
    if encoded.mode == ABSENT:
        return np.zeros((layers, lanes), dtype=bool)
    if encoded.mode == REGULAR_CORE:
        raise ValueError("Regular planes require their exact stored values/support")
    rows = [encoded.initial_mask.copy()]
    for transition in encoded.transitions:
        rows.append(decode_transition(rows[-1], transition))
    return np.stack(rows)


@dataclass
class WindowEncoding:
    metrics: dict[str, float | int | str | bool]
    mode_summary: dict[str, float]
    objective: float


def _phase0_cycles(window: np.ndarray, groups: list[np.ndarray], rho: float) -> float:
    cost = 0.0
    for layer_mask in window:
        cohort = CohortSet(
            groups,
            [
                (4 * len(group) + 2 < 6 * layer_mask[group].sum(axis=0))
                for group in groups
            ],
        )
        stats = representation_metrics(layer_mask, cohort)
        cost += float(stats["core_slots"]) + rho * float(stats["residual_nnz"])
    return cost


def _phase0_bytes(window: np.ndarray, groups: list[np.ndarray]) -> int:
    total = 0
    for layer_mask in window:
        cohort = CohortSet(
            groups,
            [
                (4 * len(group) + 2 < 6 * layer_mask[group].sum(axis=0))
                for group in groups
            ],
        )
        total += int(representation_metrics(layer_mask, cohort)["mosaic_transfer_bytes"])
    return total


def encode_window(
    window: np.ndarray,
    groups: list[np.ndarray],
    rho_delta: float = 1.25,
    decode_width_bits: int = 64,
    rho_independent: float = 2.0,
    rebase_fraction: float = 0.01,
    selector_fraction: float = 0.001,
) -> WindowEncoding:
    """Encode a W x N x F support tensor exactly and evaluate all fallbacks."""
    layers, nodes, width = window.shape
    total_nnz = int(window.sum())
    dense_slots = layers * nodes * width
    dense_bytes = layers * nodes * align64(4 * width)
    row_nnz = window.sum(axis=2)
    independent_bytes = sum(
        align64(math.ceil(width / 8) + 4 * int(value)) for value in row_nnz.flat
    )
    phase0_bytes = _phase0_bytes(window, groups)
    phase0_cycles_default = _phase0_cycles(window, groups, rho_independent)

    counts = {ABSENT: 0, REGULAR_CORE: 0, DELTA_DICTIONARY: 0}
    regular_slots = regular_true = delta_active = 0
    initial_mask_bits = transition_dense_bits = transition_sparse_bytes = flip_count = 0
    delta_metadata_bits = 0
    delta_bytes = 0
    occupancies_regular: list[float] = []
    occupancies_delta: list[float] = []
    exact = True
    regular_holes = 0
    for group in groups:
        cohort = window[:, group, :]
        m = len(group)
        modes: list[str] = []
        transition_bytes_by_layer = np.zeros(max(layers - 1, 0), dtype=np.int64)
        delta_values_by_layer = np.zeros(layers, dtype=np.int64)
        regular_count = delta_count = 0
        initial_bytes = 0
        for feature in range(width):
            plane = cohort[:, :, feature]
            encoded = encode_plane(plane, rho_delta, decode_width_bits)
            mode = encoded.mode
            modes.append(mode)
            counts[mode] += 1
            active = int(plane.sum())
            if mode == REGULAR_CORE:
                regular_count += 1
                regular_slots += layers * m
                regular_true += active
                regular_holes += layers * m - active
                occupancies_regular.append(active / (layers * m))
            elif mode == DELTA_DICTIONARY:
                delta_count += 1
                delta_active += active
                delta_values_by_layer += plane.sum(axis=1).astype(np.int64)
                initial_bytes += math.ceil(m / 8)
                initial_mask_bits += math.ceil(m / 8) * 8
                reconstructed = decode_plane(encoded, layers, m)
                exact &= bool(np.array_equal(reconstructed, plane))
                for t, transition in enumerate(encoded.transitions):
                    transition_bytes_by_layer[t] += len(transition.payload)
                    flip_count += transition.flip_count
                    if transition.dense:
                        transition_dense_bits += len(transition.payload) * 8
                    else:
                        transition_sparse_bytes += len(transition.payload)
                occupancies_delta.append(active / (layers * m))
            else:
                exact &= active == 0
        # Six logical stream families, aligned at cohort/window granularity.
        delta_bytes += align64(2 * regular_count)
        delta_bytes += sum(align64(4 * m * regular_count) for _ in range(layers))
        delta_bytes += align64(2 * delta_count)
        delta_bytes += align64(initial_bytes)
        delta_bytes += sum(align64(int(value)) for value in transition_bytes_by_layer)
        delta_bytes += sum(align64(4 * int(value)) for value in delta_values_by_layer)
        delta_metadata_bits += 16 * delta_count + 8 * initial_bytes
        delta_metadata_bits += 8 * int(transition_bytes_by_layer.sum())

    rebase_cycles = rebase_fraction * dense_slots
    selector_cycles = selector_fraction * dense_slots
    candidate_bytes = {
        "dense": dense_bytes,
        "independent_bitmap": independent_bytes,
        "phase0_mosaic": phase0_bytes,
        "mosaic_delta": delta_bytes,
    }
    candidate_base_cycles = {
        "dense": float(dense_slots),
        "independent_bitmap": rho_independent * total_nnz,
        "phase0_mosaic": phase0_cycles_default,
    }
    best_baseline = min(float(dense_slots), rho_independent * total_nnz)
    metrics: dict[str, float | int | str | bool] = {
        "num_cohorts": len(groups),
        "regular_feature_planes": counts[REGULAR_CORE],
        "delta_feature_planes": counts[DELTA_DICTIONARY],
        "absent_feature_planes": counts[ABSENT],
        "regular_slots": regular_slots,
        "regular_true_nnz": regular_true,
        "regular_holes": regular_holes,
        "delta_active_nnz": delta_active,
        "initial_mask_bits": initial_mask_bits,
        "transition_dense_bits": transition_dense_bits,
        "transition_sparse_bytes": transition_sparse_bytes,
        "flip_count": flip_count,
        "total_nnz": total_nnz,
        "dense_bytes": dense_bytes,
        "independent_bitmap_bytes": independent_bytes,
        "phase0_mosaic_bytes": phase0_bytes,
        "mosaic_delta_bytes": delta_bytes,
        "exact_decode_pass": exact,
        "_best_baseline_cycles": best_baseline,
        "_phase0_cycles_rho2": phase0_cycles_default,
        "_delta_metadata_bits": delta_metadata_bits,
    }
    rho_fields = {
        1.10: "1_10",
        1.25: "1_25",
        1.50: "1_50",
        1.75: "1_75",
    }
    raw_delta_default = 0.0
    for rho, key in rho_fields.items():
        delta_cycles = (
            regular_slots
            + rho * delta_active
            + math.ceil(delta_metadata_bits / decode_width_bits)
            + rebase_cycles
        )
        candidates = {**candidate_base_cycles, "mosaic_delta": delta_cycles}
        winner = min(candidates, key=candidates.get)
        selected_cycles = candidates[winner] + selector_cycles
        metrics[f"proxy_cycles_rho{key}"] = selected_cycles
        metrics[f"proxy_speedup_rho{key}"] = best_baseline / selected_cycles
        metrics[f"_mosaic_delta_raw_cycles_rho{key}"] = delta_cycles
        if abs(rho - 1.25) < 1e-9:
            raw_delta_default = delta_cycles
            metrics["selected_representation"] = winner
            metrics["selected_bytes"] = candidate_bytes[winner]
            metrics["byte_ratio_to_best_baseline"] = (
                candidate_bytes[winner] / min(dense_bytes, independent_bytes)
            )
    decode_cycles = math.ceil(delta_metadata_bits / decode_width_bits)
    for target, field in (
        (1.0, "rho_delta_max_for_1x"),
        (1.15, "rho_delta_max_for_1_15x"),
        (1.25, "rho_delta_max_for_1_25x"),
    ):
        numerator = best_baseline / target - regular_slots - decode_cycles - rebase_cycles
        metrics[field] = numerator / delta_active if delta_active else float("inf")
    planes = sum(counts.values())
    mode_summary = {
        "fraction_absent": counts[ABSENT] / planes if planes else 0.0,
        "fraction_regular": counts[REGULAR_CORE] / planes if planes else 0.0,
        "fraction_delta": counts[DELTA_DICTIONARY] / planes if planes else 0.0,
        "regular_occupancy_mean": float(np.mean(occupancies_regular)) if occupancies_regular else 0.0,
        "delta_occupancy_mean": float(np.mean(occupancies_delta)) if occupancies_delta else 0.0,
        "regular_capture": regular_true / total_nnz if total_nnz else 0.0,
        "padding_fraction": regular_holes / regular_slots if regular_slots else 0.0,
        "delta_fraction": delta_active / total_nnz if total_nnz else 0.0,
        "metadata_bits_per_nnz": delta_metadata_bits / total_nnz if total_nnz else 0.0,
        "flips_per_node_feature": flip_count / (nodes * width * max(layers - 1, 1)),
    }
    # The clustering objective is the proposed representation itself, before
    # fallback selection; otherwise a grouping-insensitive fallback could mask
    # assignment improvements.
    objective = raw_delta_default
    return WindowEncoding(metrics, mode_summary, objective)


def reconstruct_support(
    window: np.ndarray,
    groups: Iterable[np.ndarray],
    rho_delta: float = 1.25,
    decode_width_bits: int = 64,
) -> np.ndarray:
    """Round-trip every non-regular plane; regular support comes from exact values."""
    output = np.zeros_like(window)
    for group in groups:
        cohort = window[:, group, :]
        for feature in range(window.shape[2]):
            plane = cohort[:, :, feature]
            encoded = encode_plane(plane, rho_delta, decode_width_bits)
            if encoded.mode == REGULAR_CORE:
                decoded = plane.copy()
            else:
                decoded = decode_plane(encoded, len(window), len(group))
            output[:, group, feature] = decoded
    return output
