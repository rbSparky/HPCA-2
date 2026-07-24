"""Exact persistent row-panel schedules for MOSAIC-PANEL.

The representation partitions feature coordinates once per depth segment.  A
topology tile then stores one persistent, sorted row list per panel.  Selected
row-panel rectangles are dense; every active element outside those rectangles
is retained in an independently decodable residual stream.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable

import numpy as np

from .delta_encoding import align64
from .global_gap import EventCode, encode_event_set

try:
    from numba import njit
except ImportError:  # pragma: no cover - the project environment includes numba.
    njit = None


@dataclass(frozen=True)
class PanelCostConfig:
    """Hardware parameters used by the exact finite prefix objective."""

    rho_residual: float = 1.50
    decoder_width_bits: int = 64
    gather_width_values: int = 32
    accumulator_width_values: int = 32
    output_features: int = 64
    escape_enabled: bool = False
    alignment_bytes: int = 64


@dataclass
class TilePanelSchedule:
    """One exact persistent schedule for one topology tile and feature panel."""

    features: np.ndarray
    selected_rows: np.ndarray
    escape_layers: np.ndarray
    row_code: EventCode
    residual_codes: list[EventCode]
    objective_by_prefix: np.ndarray
    total_cycles: float
    regular_cycles: float
    residual_cycles: float
    gather_cycles: float
    decoder_cycles: float
    output_vector_cycles: float
    dense_slots: int
    dense_true_nnz: int
    residual_nnz: int

    def reconstruct(self, window: np.ndarray) -> np.ndarray:
        """Reconstruct the support from the dense rectangles and residuals."""
        out = np.zeros_like(window, dtype=bool)
        for layer in range(window.shape[0]):
            if not self.escape_layers[layer] and self.selected_rows.size:
                out[layer][np.ix_(self.selected_rows, self.features)] = window[
                    layer
                ][np.ix_(self.selected_rows, self.features)]
            residual = self.residual_codes[layer].decode().reshape(
                window.shape[1], len(self.features)
            )
            index = np.ix_(np.arange(window.shape[1]), self.features)
            out[layer][index] = np.logical_or(out[layer][index], residual)
        return out


@dataclass
class PanelEncoding:
    """Complete exact encoding for one segment and all topology tiles."""

    panels: list[np.ndarray]
    schedules: list[list[TilePanelSchedule]]
    metrics: dict[str, float | int | bool]
    objective_history: list[float]


def validate_partition(panels: Iterable[np.ndarray], features: int) -> None:
    """Raise when panels are not a disjoint cover of ``range(features)``."""
    flat = np.concatenate([np.asarray(panel, dtype=np.int64) for panel in panels])
    if flat.size != features or not np.array_equal(np.sort(flat), np.arange(features)):
        raise ValueError("feature panels must be a disjoint exact feature cover")


def contiguous_panels(features: int, width: int) -> list[np.ndarray]:
    """P0: contiguous feature panels without silent feature padding."""
    if width <= 0:
        raise ValueError("panel width must be positive")
    return [np.arange(start, min(start + width, features)) for start in range(0, features, width)]


def density_sorted_panels(window: np.ndarray, width: int) -> list[np.ndarray]:
    """P1: deterministic decreasing-density feature panels."""
    density = window.mean(axis=(0, 1))
    order = np.lexsort((np.arange(window.shape[2]), -density))
    return [order[start : start + width].copy() for start in range(0, order.size, width)]


def _jaccard_matrix(window: np.ndarray) -> np.ndarray:
    """Pairwise support Jaccard using packed bit intersections."""
    flat = window.reshape(-1, window.shape[2]).T
    packed = np.packbits(flat, axis=1, bitorder="little")
    counts = flat.sum(axis=1).astype(np.int64)
    features = flat.shape[0]
    result = np.eye(features, dtype=np.float64)
    # F is at most 128 in the principal traces; loops are over columns, never
    # over individual activation elements.
    for left in range(features):
        both = np.bitwise_and(packed[left], packed[left:]).view(np.uint8)
        inter = np.unpackbits(both, axis=1, bitorder="little").sum(axis=1)
        union = counts[left] + counts[left:] - inter
        values = np.divide(inter, union, out=np.ones_like(inter, dtype=float), where=union != 0)
        result[left, left:] = values
        result[left:, left] = values
    return result


def correlation_panels(window: np.ndarray, width: int) -> list[np.ndarray]:
    """P2: greedy support-Jaccard panels with deterministic tie breaking."""
    similarity = _jaccard_matrix(window)
    density = window.mean(axis=(0, 1))
    remaining = set(range(window.shape[2]))
    panels: list[np.ndarray] = []
    while remaining:
        start = min(remaining, key=lambda f: (-density[f], f))
        panel = [start]
        remaining.remove(start)
        while remaining and len(panel) < width:
            candidate = min(
                remaining,
                key=lambda f: (-float(similarity[f, panel].mean()), f),
            )
            panel.append(candidate)
            remaining.remove(candidate)
        panels.append(np.asarray(panel, dtype=np.int64))
    return panels


def row_list_code(rows: np.ndarray, tile_rows: int) -> EventCode:
    """Smallest legal exact bitmap/fixed-ID/block-FOR row-list stream."""
    mask = np.zeros(tile_rows, dtype=bool)
    mask[np.asarray(rows, dtype=np.int64)] = True
    return encode_event_set(mask, blocks=(8, 16, 32), allow_complement=False)


def _residual_mask(
    layer: np.ndarray,
    features: np.ndarray,
    selected: np.ndarray,
    escape: bool,
) -> np.ndarray:
    residual = np.zeros_like(layer, dtype=bool)
    residual[:, features] = layer[:, features]
    if not escape and selected.size:
        residual[np.ix_(selected, features)] = False
    return residual


def _panel_residual_code(
    layer: np.ndarray,
    features: np.ndarray,
    selected: np.ndarray,
    escape: bool,
) -> EventCode:
    """Encode one panel-local residual stream without unrelated zero features."""
    panel = layer[:, features].copy()
    if not escape and selected.size:
        panel[selected] = False
    return encode_event_set(panel.reshape(-1))


def _fast_event_bits(mask: np.ndarray) -> int:
    """Exact minimum event-stream bit count with vectorized block-FOR gaps."""
    events = np.flatnonzero(np.asarray(mask).reshape(-1))
    universe = int(np.asarray(mask).size)
    count_bits = max(1, math.ceil(math.log2(max(universe + 1, 2))))
    id_bits = max(1, math.ceil(math.log2(max(universe, 2))))
    width_header = max(1, math.ceil(math.log2(max(id_bits + 1, 2))))
    candidates = [2 + universe, 2 + count_bits + len(events) * id_bits]
    for block in (8, 16, 32):
        blocks = math.ceil(len(events) / block)
        total = 2 + 2 + count_bits
        if blocks:
            padded = np.pad(
                events,
                (0, blocks * block - len(events)),
                mode="edge",
            ).reshape(blocks, block)
            lengths = np.minimum(block, len(events) - np.arange(blocks) * block)
            max_gap = np.diff(padded, axis=1).max(axis=1, initial=0)
            widths = np.maximum(
                1, np.ceil(np.log2(np.maximum(max_gap + 1, 2))).astype(np.int64)
            )
            total += blocks * (id_bits + width_header)
            total += int(np.sum(widths * np.maximum(lengths - 1, 0)))
        candidates.append(total)
    return int(min(candidates))


if njit is not None:

    @njit(cache=True)
    def _prefix_event_bits_numba(panel_window, order):
        layers, rows, width = panel_window.shape
        universe = rows * width
        count_bits = max(1, int(math.ceil(math.log2(max(universe + 1, 2)))))
        id_bits = max(1, int(math.ceil(math.log2(max(universe, 2)))))
        width_header = max(1, int(math.ceil(math.log2(max(id_bits + 1, 2)))))
        rank = np.empty(rows, dtype=np.int64)
        for index in range(rows):
            rank[order[index]] = index
        result = np.empty((layers, rows + 1), dtype=np.int64)
        events = np.empty(universe, dtype=np.int64)
        block_sizes = (8, 16, 32)
        for layer in range(layers):
            for prefix in range(rows + 1):
                count = 0
                for row in range(rows):
                    if rank[row] < prefix:
                        continue
                    for feature in range(width):
                        if panel_window[layer, row, feature]:
                            events[count] = row * width + feature
                            count += 1
                best = min(2 + universe, 2 + count_bits + count * id_bits)
                for block in block_sizes:
                    total = 2 + 2 + count_bits
                    start = 0
                    while start < count:
                        stop = min(start + block, count)
                        max_gap = 0
                        for event in range(start + 1, stop):
                            gap = events[event] - events[event - 1]
                            if gap > max_gap:
                                max_gap = gap
                        gap_width = max(
                            1, int(math.ceil(math.log2(max(max_gap + 1, 2))))
                        )
                        total += id_bits + width_header + gap_width * (stop - start - 1)
                        start = stop
                    if total < best:
                        best = total
                result[layer, prefix] = best
        return result


def _all_prefix_event_bits(panel_window: np.ndarray, order: np.ndarray) -> np.ndarray:
    """Exact event bits for every layer/prefix, compiled when Numba is present."""
    if njit is not None:
        return _prefix_event_bits_numba(panel_window, order)
    result = np.empty(
        (panel_window.shape[0], panel_window.shape[1] + 1), dtype=np.int64
    )
    for layer in range(panel_window.shape[0]):
        for prefix in range(panel_window.shape[1] + 1):
            residual = panel_window[layer].copy()
            residual[order[:prefix]] = False
            result[layer, prefix] = _fast_event_bits(residual)
    return result


def _prefix_objectives(
    window: np.ndarray,
    features: np.ndarray,
    config: PanelCostConfig,
    cycle_lookup: Callable[[int, int, int], tuple[float, float]],
) -> tuple[np.ndarray, list[np.ndarray]]:
    """Evaluate every legal top-count prefix under the complete local cost."""
    layers, rows, _ = window.shape
    k = len(features)
    counts = window[:, :, features].sum(axis=(0, 2))
    order = np.lexsort((np.arange(rows), -counts))
    panel_window = window[:, :, features]
    row_counts = panel_window[:, order, :].sum(axis=2)
    selected_prefix = np.concatenate(
        [np.zeros((layers, 1), dtype=np.int64), np.cumsum(row_counts, axis=1)],
        axis=1,
    )
    layer_nnz = panel_window.sum(axis=(1, 2)).astype(np.int64)
    all_bits_by_layer = [_fast_event_bits(panel_window[layer]) for layer in range(layers)]
    active_rows_by_layer = np.count_nonzero(panel_window.any(axis=2), axis=1)
    prefix_event_bits = _all_prefix_event_bits(panel_window, order)
    objectives = np.empty(rows + 1, dtype=np.float64)
    escapes: list[np.ndarray] = []
    descriptor_cycles = math.ceil((16 * k + 32 * 6) / config.decoder_width_bits)
    for m in range(rows + 1):
        selected = order[:m]
        row_bits = row_list_code(selected, rows).encoded_bits
        total = descriptor_cycles + math.ceil(row_bits / config.decoder_width_bits)
        layer_escapes = np.zeros(layers, dtype=bool)
        for layer_id, layer in enumerate(window):
            selected_nnz = int(selected_prefix[layer_id, m])
            unselected_nnz = int(layer_nnz[layer_id]) - selected_nnz
            residual_bits = int(prefix_event_bits[layer_id, m])
            regular_cycles = cycle_lookup(m, k, config.output_features)[0] if m else 0.0
            dense_cost = (
                regular_cycles
                + config.rho_residual * unselected_nnz
                + math.ceil(m * k / config.gather_width_values)
                + math.ceil(residual_bits / config.decoder_width_bits)
                + m * math.ceil(config.output_features / config.accumulator_width_values)
            )
            all_nnz = int(layer_nnz[layer_id])
            all_bits = all_bits_by_layer[layer_id]
            residual_cost = (
                config.rho_residual * all_nnz
                + math.ceil(all_bits / config.decoder_width_bits)
                + int(active_rows_by_layer[layer_id])
                * math.ceil(config.output_features / config.accumulator_width_values)
            )
            if config.escape_enabled and residual_cost < dense_cost:
                layer_escapes[layer_id] = True
                total += residual_cost
            else:
                total += dense_cost
        # Persistent descriptor/weight-panel packing is explicit and amortized
        # across the segment. One cycle per 32 descriptor bytes and per 32
        # weights models bounded packing/dispatch bandwidth.
        total += math.ceil((2 * k + math.ceil(row_bits / 8) + 24) / 32)
        total += math.ceil(k * config.output_features / 32)
        objectives[m] = total
        escapes.append(layer_escapes)
    return objectives, escapes


def optimize_fixed_panel(
    window: np.ndarray,
    features: np.ndarray,
    config: PanelCostConfig,
    cycle_lookup: Callable[[int, int, int], tuple[float, float]],
) -> TilePanelSchedule:
    """Choose the globally best top-count prefix for a fixed feature panel.

    For fixed ``m``, selected-row identities cannot change the dense GEMM,
    gather, row-list length, or vector contribution count. Selecting the rows
    with the largest activation counts therefore minimizes residual work.
    Every prefix length, including zero, is evaluated using calibrated cycles.
    """
    objectives, escapes = _prefix_objectives(window, features, config, cycle_lookup)
    m = int(np.argmin(objectives))
    counts = window[:, :, features].sum(axis=(0, 2))
    order = np.lexsort((np.arange(window.shape[1]), -counts))
    selected = np.sort(order[:m])
    row_code = row_list_code(selected, window.shape[1])
    residual_codes: list[EventCode] = []
    regular = residual_cycles = gather = decoder = output = 0.0
    dense_slots = dense_true = residual_nnz = 0
    for layer_id, layer in enumerate(window):
        escaped = bool(escapes[m][layer_id])
        residual = _residual_mask(layer, features, selected, escaped)
        code = _panel_residual_code(layer, features, selected, escaped)
        residual_codes.append(code)
        layer_residual = int(residual.sum())
        residual_nnz += layer_residual
        residual_cycles += config.rho_residual * layer_residual
        decoder += math.ceil(code.encoded_bits / config.decoder_width_bits)
        if not escaped and m:
            regular += cycle_lookup(m, len(features), config.output_features)[0]
            gather += math.ceil(m * len(features) / config.gather_width_values)
            output += m * math.ceil(config.output_features / config.accumulator_width_values)
            dense_slots += m * len(features)
            dense_true += int(layer[np.ix_(selected, features)].sum())
        elif escaped:
            output += int(np.count_nonzero(layer[:, features].any(axis=1))) * math.ceil(
                config.output_features / config.accumulator_width_values
            )
    decoder += math.ceil(row_code.encoded_bits / config.decoder_width_bits)
    total = float(objectives[m])
    return TilePanelSchedule(
        features=np.asarray(features),
        selected_rows=selected,
        escape_layers=escapes[m],
        row_code=row_code,
        residual_codes=residual_codes,
        objective_by_prefix=objectives,
        total_cycles=total,
        regular_cycles=regular,
        residual_cycles=residual_cycles,
        gather_cycles=gather,
        decoder_cycles=decoder,
        output_vector_cycles=output,
        dense_slots=dense_slots,
        dense_true_nnz=dense_true,
        residual_nnz=residual_nnz,
    )


def _schedule_for_rows(
    window: np.ndarray,
    features: np.ndarray,
    selected: np.ndarray,
    config: PanelCostConfig,
    cycle_lookup: Callable[[int, int, int], tuple[float, float]],
) -> TilePanelSchedule:
    """Build exact streams and accounting for a prescribed persistent row set."""
    selected = np.sort(np.unique(selected)).astype(np.int64)
    row_code = row_list_code(selected, window.shape[1])
    residual_codes = []
    regular = residual_cycles = gather = decoder = output = 0.0
    dense_slots = dense_true = residual_nnz = 0
    for layer in window:
        residual = _residual_mask(layer, features, selected, False)
        code = _panel_residual_code(layer, features, selected, False)
        residual_codes.append(code)
        layer_residual = int(residual.sum())
        residual_nnz += layer_residual
        residual_cycles += config.rho_residual * layer_residual
        decoder += math.ceil(code.encoded_bits / config.decoder_width_bits)
        if selected.size:
            regular += cycle_lookup(
                len(selected), len(features), config.output_features
            )[0]
            gather += math.ceil(
                len(selected) * len(features) / config.gather_width_values
            )
            output += len(selected) * math.ceil(
                config.output_features / config.accumulator_width_values
            )
            dense_slots += len(selected) * len(features)
            dense_true += int(layer[np.ix_(selected, features)].sum())
    decoder += math.ceil(row_code.encoded_bits / config.decoder_width_bits)
    weight_pack = math.ceil(len(features) * config.output_features / 32)
    descriptor = math.ceil(
        (2 * len(features) + math.ceil(row_code.encoded_bits / 8) + 24) / 32
    )
    total = regular + residual_cycles + gather + decoder + output + weight_pack + descriptor
    return TilePanelSchedule(
        features=np.asarray(features),
        selected_rows=selected,
        escape_layers=np.zeros(window.shape[0], dtype=bool),
        row_code=row_code,
        residual_codes=residual_codes,
        objective_by_prefix=np.asarray([total]),
        total_cycles=float(total),
        regular_cycles=regular,
        residual_cycles=residual_cycles,
        gather_cycles=gather,
        decoder_cycles=decoder,
        output_vector_cycles=output,
        dense_slots=dense_slots,
        dense_true_nnz=dense_true,
        residual_nnz=residual_nnz,
    )


def optimize_fixed_bsr_panel(
    window: np.ndarray,
    features: np.ndarray,
    config: PanelCostConfig,
    cycle_lookup: Callable[[int, int, int], tuple[float, float]],
    row_block: int = 16,
) -> TilePanelSchedule:
    """P4 control: fixed contiguous row blocks, never arbitrary compaction."""
    selected_blocks: list[np.ndarray] = []
    for start in range(0, window.shape[1], row_block):
        rows = np.arange(start, min(start + row_block, window.shape[1]))
        active = int(window[:, rows][:, :, features].sum())
        dense = (
            window.shape[0]
            * cycle_lookup(len(rows), len(features), config.output_features)[0]
            + window.shape[0]
            * math.ceil(len(rows) * len(features) / config.gather_width_values)
            + window.shape[0]
            * len(rows)
            * math.ceil(config.output_features / config.accumulator_width_values)
        )
        sparse = config.rho_residual * active
        if dense < sparse:
            selected_blocks.append(rows)
    selected = (
        np.concatenate(selected_blocks)
        if selected_blocks
        else np.empty(0, dtype=np.int64)
    )
    return _schedule_for_rows(window, features, selected, config, cycle_lookup)


def encode_panel_segment(
    window: np.ndarray,
    tile_indices: list[np.ndarray],
    panels: list[np.ndarray],
    config: PanelCostConfig,
    cycle_lookup: Callable[[int, int, int], tuple[float, float]],
    fixed_bsr: bool = False,
) -> PanelEncoding:
    """Encode a segment exactly, preserving topology-tile boundaries."""
    validate_partition(panels, window.shape[2])
    schedules: list[list[TilePanelSchedule]] = []
    for tile in tile_indices:
        local = window[:, tile, :]
        optimizer = optimize_fixed_bsr_panel if fixed_bsr else optimize_fixed_panel
        schedules.append([optimizer(local, panel, config, cycle_lookup) for panel in panels])
    all_schedules = [item for tile in schedules for item in tile]
    dense_slots = sum(item.dense_slots for item in all_schedules)
    dense_true = sum(item.dense_true_nnz for item in all_schedules)
    residual_nnz = sum(item.residual_nnz for item in all_schedules)
    row_bits = sum(item.row_code.encoded_bits for item in all_schedules)
    residual_bits = sum(
        code.encoded_bits for item in all_schedules for code in item.residual_codes
    )
    panel_bits = 16 * window.shape[2]
    descriptor_bits = 32 * (len(all_schedules) + len(panels) + 1)
    escape_bits = len(all_schedules) * window.shape[0] if config.escape_enabled else 0
    dense_value_bytes = sum(
        align64(4 * item.dense_slots // window.shape[0])
        * int((~item.escape_layers).sum())
        for item in all_schedules
        if item.dense_slots
    )
    residual_value_bytes = sum(
        align64(4 * int(code.decode().sum()))
        for item in all_schedules
        for code in item.residual_codes
    )
    metadata_bytes = sum(
        align64(math.ceil(bits / 8))
        for bits in (panel_bits, row_bits, residual_bits, descriptor_bits + escape_bits)
    )
    total_cycles = sum(item.total_cycles for item in all_schedules)
    regular = sum(item.regular_cycles for item in all_schedules)
    residual_cycles = sum(item.residual_cycles for item in all_schedules)
    gather = sum(item.gather_cycles for item in all_schedules)
    decoder = sum(item.decoder_cycles for item in all_schedules)
    vector = sum(item.output_vector_cycles for item in all_schedules)
    # Each row-layer's first contribution initializes; subsequent ones add.
    init_contrib = add_contrib = 0
    chunks = math.ceil(config.output_features / config.accumulator_width_values)
    for tile_id, tile in enumerate(tile_indices):
        for layer in range(window.shape[0]):
            counts = np.zeros(len(tile), dtype=np.int32)
            for item in schedules[tile_id]:
                if not item.escape_layers[layer]:
                    counts[item.selected_rows] += 1
                residual = item.residual_codes[layer].decode().reshape(
                    len(tile), len(item.features)
                )
                counts[residual.any(axis=1)] += 1
            init_contrib += int(np.count_nonzero(counts)) * chunks
            add_contrib += int(np.maximum(counts - 1, 0).sum()) * chunks
    exact = True
    for tile_id, tile in enumerate(tile_indices):
        rebuilt = np.zeros_like(window[:, tile, :])
        for item in schedules[tile_id]:
            rebuilt |= item.reconstruct(window[:, tile, :])
        exact &= bool(np.array_equal(rebuilt, window[:, tile, :]))
    nnz = int(window.sum())
    metrics: dict[str, float | int | bool] = {
        "total_nnz": nnz,
        "dense_panel_slots": dense_slots,
        "dense_panel_true_nnz": dense_true,
        "dense_panel_holes": dense_slots - dense_true,
        "residual_nnz": residual_nnz,
        "panel_feature_metadata_bits": panel_bits,
        "row_list_metadata_bits": row_bits,
        "residual_metadata_bits": residual_bits,
        "descriptor_bits": descriptor_bits + escape_bits,
        "dense_value_bytes": dense_value_bytes,
        "residual_value_bytes": residual_value_bytes,
        "total_transfer_bytes": dense_value_bytes + residual_value_bytes + metadata_bytes,
        "regular_scalesim_cycles": regular,
        "residual_cycles": residual_cycles,
        "gather_cycles": gather,
        "decoder_cycles": decoder,
        "output_init_cycles": init_contrib,
        "output_add_cycles": add_contrib,
        "weight_pack_cycles": sum(
            math.ceil(len(panel) * config.output_features / 32) for panel in panels
        ),
        "total_hybrid_cycles": total_cycles,
        "dense_nnz_capture": dense_true / max(nnz, 1),
        "padding_fraction": (dense_slots - dense_true) / max(dense_slots, 1),
        "residual_fraction": residual_nnz / max(nnz, 1),
        "exact_decode_pass": exact,
        "independently_decodable": True,
        "numeric_equivalence_pass": exact,
        "escape_fraction": float(
            np.mean(np.concatenate([item.escape_layers for item in all_schedules]))
        ),
    }
    return PanelEncoding(panels, schedules, metrics, [total_cycles])


def cost_aware_swaps(
    initial: list[np.ndarray],
    cost: Callable[[list[np.ndarray]], float],
    max_passes: int = 2,
) -> tuple[list[np.ndarray], list[float], int]:
    """P3 deterministic strict-decrease pairwise feature swaps."""
    panels = [panel.copy() for panel in initial]
    objective = float(cost(panels))
    history = [objective]
    accepted = 0
    for _ in range(max_passes):
        changed = False
        for left in range(len(panels)):
            for right in range(left + 1, len(panels)):
                for li in range(len(panels[left])):
                    for ri in range(len(panels[right])):
                        candidate = [panel.copy() for panel in panels]
                        candidate[left][li], candidate[right][ri] = (
                            candidate[right][ri],
                            candidate[left][li],
                        )
                        value = float(cost(candidate))
                        if value + 1e-9 < objective:
                            panels, objective = candidate, value
                            history.append(value)
                            accepted += 1
                            changed = True
        if not changed:
            break
    return panels, history, accepted


def numeric_decomposition(
    values: np.ndarray,
    weights: np.ndarray,
    encoding: PanelEncoding,
    tile_indices: list[np.ndarray],
) -> tuple[np.ndarray, np.ndarray]:
    """Return dense reference and exact panel-plus-residual combination result."""
    reference = values @ weights
    output = np.zeros_like(reference)
    for tile_id, tile in enumerate(tile_indices):
        for layer in range(values.shape[0]):
            for item in encoding.schedules[tile_id]:
                features = item.features
                if not item.escape_layers[layer] and item.selected_rows.size:
                    global_rows = tile[item.selected_rows]
                    output[layer, global_rows] += (
                        values[layer][np.ix_(global_rows, features)] @ weights[layer, features]
                    )
                residual = item.residual_codes[layer].decode().reshape(
                    len(tile), len(features)
                )
                residual_values = values[layer][np.ix_(tile, features)] * residual
                output[layer, tile] += residual_values @ weights[layer, features]
    return reference, output
