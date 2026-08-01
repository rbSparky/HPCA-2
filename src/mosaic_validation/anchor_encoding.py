"""Deployable independently decodable MOSAIC-Anchor representation."""

from dataclasses import dataclass
import math

import numpy as np

from .delta_encoding import align64, encode_window
from .global_gap import EventCode, encode_event_set

ABSENT = "ABSENT"
FULL_CORE = "FULL_CORE"
LANE_ANCHOR = "LANE_ANCHOR"
INDEPENDENT_SPARSE = "INDEPENDENT_SPARSE"


@dataclass
class AnchorEncoding:
    anchor: np.ndarray
    modes: np.ndarray
    exceptions: list[EventCode]
    objective_history: list[float]
    metrics: dict[str, float | int | bool]

    def decode_layer(self, layer: int) -> np.ndarray:
        """Decode using only the persistent anchor and this layer's stream."""
        exception = self.exceptions[layer].decode().reshape(self.anchor.shape)
        return np.logical_xor(self.anchor, exception)


def _objective(
    window: np.ndarray,
    anchor: np.ndarray,
    rho: float,
    decode_width: int,
) -> tuple[float, list[EventCode]]:
    codes = [
        encode_event_set(np.logical_xor(layer, anchor).reshape(-1))
        for layer in window
    ]
    regular = window.shape[0] * int(anchor.sum())
    sparse = int(np.logical_and(window, ~anchor).sum())
    metadata = 2 * window.shape[2] + 16 * int(anchor.any(axis=0).sum())
    metadata += anchor.shape[0] * int(anchor.any(axis=0).sum())
    metadata += sum(code.encoded_bits for code in codes)
    return regular + rho * sparse + math.ceil(metadata / decode_width), codes


def encode_anchor(
    window: np.ndarray,
    rho: float = 1.25,
    decode_width: int = 64,
    max_passes: int = 4,
    brute_force_tiny: bool = True,
) -> AnchorEncoding:
    """Optimize the exact finite anchor objective with monotone descent."""
    layers, lanes, features = window.shape
    counts = window.sum(axis=0)
    anchor = layers < rho * counts
    history: list[float] = []
    objective, codes = _objective(window, anchor, rho, decode_width)
    history.append(objective)
    # Exhaustive reference doubles as exact coordinate descent for tiny tests.
    if brute_force_tiny and lanes * features <= 10:
        best = anchor.copy()
        for bits in range(1 << (lanes * features)):
            candidate = np.asarray(
                [(bits >> index) & 1 for index in range(lanes * features)],
                dtype=bool,
            ).reshape(lanes, features)
            value, _ = _objective(window, candidate, rho, decode_width)
            if value < objective:
                objective, best = value, candidate
        anchor = best
        objective, codes = _objective(window, anchor, rho, decode_width)
        history.append(objective)
    else:
        # The separable threshold is the compute optimum. Evaluate every bit's
        # exact compute move, then accept a full pass only if coupled metadata
        # also strictly improves the declared objective.
        for _ in range(max_passes):
            candidate = anchor.copy()
            for lane in range(lanes):
                for feature in range(features):
                    active = counts[lane, feature]
                    anchored = layers
                    residual = rho * active
                    candidate[lane, feature] = anchored < residual
            value, candidate_codes = _objective(window, candidate, rho, decode_width)
            if value + 1e-12 < history[-1]:
                anchor, codes = candidate, candidate_codes
                history.append(value)
            else:
                break
    modes = np.full(features, INDEPENDENT_SPARSE, dtype=object)
    modes[counts.sum(axis=0) == 0] = ABSENT
    modes[anchor.all(axis=0)] = FULL_CORE
    modes[anchor.any(axis=0) & ~anchor.all(axis=0)] = LANE_ANCHOR
    regular_slots = layers * int(anchor.sum())
    anchor_true = int(np.logical_and(window, anchor).sum())
    holes = regular_slots - anchor_true
    sparse = int(np.logical_and(window, ~anchor).sum())
    support_bits = (
        2 * features
        + 16 * int(anchor.any(axis=0).sum())
        + lanes * int(anchor.any(axis=0).sum())
        + sum(code.encoded_bits for code in codes)
        + 32 * (layers + 5)
    )
    value_bytes = 4 * (regular_slots + sparse)
    metadata_bytes = align64(math.ceil(support_bits / 8))
    regular_value_bytes = sum(align64(4 * int(anchor.sum())) for _ in range(layers))
    sparse_value_bytes = sum(
        align64(4 * int(np.logical_and(layer, ~anchor).sum())) for layer in window
    )
    total_bytes = metadata_bytes + regular_value_bytes + sparse_value_bytes
    exact = all(np.array_equal(codes[t].decode().reshape(lanes, features) ^ anchor, window[t])
                for t in range(layers))
    metrics = {
        "regular_slots": regular_slots,
        "anchor_slots": regular_slots,
        "anchor_true_nnz": anchor_true,
        "anchor_holes": holes,
        "sparse_additions": sparse,
        "support_metadata_bits": support_bits,
        "value_bytes": value_bytes,
        "total_transfer_bytes": total_bytes,
        "exact_decode_pass": exact,
        "fraction_absent": float(np.mean(modes == ABSENT)),
        "fraction_full_core": float(np.mean(modes == FULL_CORE)),
        "fraction_lane_anchor": float(np.mean(modes == LANE_ANCHOR)),
        "fraction_independent_sparse": float(np.mean(modes == INDEPENDENT_SPARSE)),
        "anchor_nnz_capture": anchor_true / max(int(window.sum()), 1),
        "anchor_slot_occupancy": anchor_true / max(regular_slots, 1),
        "padding_fraction": holes / max(regular_slots, 1),
        "sparse_addition_fraction": sparse / max(int(window.sum()), 1),
        "mean_anchor_lanes_per_feature": float(anchor.sum(axis=0).mean()),
    }
    for value in (1.10, 1.25, 1.50, 1.75):
        cycles = regular_slots + value * sparse + math.ceil(support_bits / decode_width)
        baseline = min(window.size, 2.0 * int(window.sum()))
        metrics[f"proxy_{value:.2f}"] = baseline / cycles
        metrics[f"cycles_{value:.2f}"] = cycles
    return AnchorEncoding(anchor, modes, codes, history, metrics)


def encode_independent(window: np.ndarray) -> dict[str, int | float | bool]:
    """R0: independently decodable minimum bitmap/ID support per row."""
    layers, nodes, features = window.shape
    support_bits = value_bytes = total = 0
    id_bits = max(1, math.ceil(math.log2(max(features, 2))))
    for layer in window:
        for row in layer:
            nnz = int(row.sum())
            bitmap = features
            sparse = max(1, math.ceil(math.log2(features + 1))) + nnz * id_bits
            bits = min(bitmap, sparse) + 1
            support_bits += bits
            value_bytes += 4 * nnz
            total += align64(math.ceil(bits / 8)) + align64(4 * nnz)
    return {
        "support_metadata_bits": support_bits, "value_bytes": value_bytes,
        "total_transfer_bytes": total, "exact_decode_pass": True,
    }


def encode_chain_gap(window: np.ndarray) -> tuple[dict[str, int | float | bool], list[EventCode]]:
    """R2 optimistic predecessor chain using cohort-global event streams."""
    layers, nodes, features = window.shape
    universe = nodes * features
    codes = [encode_event_set(window[0].reshape(-1), allow_complement=True)]
    codes.extend(
        encode_event_set(np.logical_xor(window[t - 1], window[t]).reshape(-1))
        for t in range(1, layers)
    )
    support = sum(code.encoded_bits for code in codes)
    values = 4 * int(window.sum())
    total = align64(math.ceil(codes[0].encoded_bits / 8))
    total += sum(align64(math.ceil(code.encoded_bits / 8)) for code in codes[1:])
    total += sum(align64(4 * int(layer.sum())) for layer in window)
    decoded = [codes[0].decode().reshape(nodes, features)]
    for code in codes[1:]:
        decoded.append(np.logical_xor(decoded[-1], code.decode().reshape(nodes, features)))
    return {
        "support_metadata_bits": support, "value_bytes": values,
        "total_transfer_bytes": total,
        "exact_decode_pass": bool(np.array_equal(np.stack(decoded), window)),
    }, codes

