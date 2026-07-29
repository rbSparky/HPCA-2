"""Exact independently-decodable activation-format baselines for XORFLOW.

Every format in this module has a physical :class:`SliceLayout` with fixed,
64-byte-aligned row-slice addresses.  The layout, cache simulator, feature
precision, node order, and value stream are therefore shared with XORFLOW;
only legal support/index metadata changes.  This prevents a baseline from
receiving free row pointers, feature IDs, selectors, or alignment.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Literal

import numpy as np

from .delta_encoding import align64
from .memory_subsystem import (
    CacheTraffic,
    LINE_BYTES,
    SliceLayout,
    build_mixed_sliced_layout,
    build_sliced_layout,
    njit,
    simulate_set_associative_lru,
    touched_lines,
)


BaselineName = Literal["DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST"]
_ROW_FORMATS: tuple[str, ...] = ("DENSE", "CSR32", "CSR_PACKED", "BEICSR")


@dataclass(frozen=True)
class BaselineLayout:
    """Physical layout plus every separately stored support metadata stream."""

    name: BaselineName
    layout: SliceLayout
    value_bytes: int
    support_bytes: int
    row_pointer_bytes: int
    selector_bits: int
    descriptor_bytes: int
    feature_id_bits: int
    selected_row_formats: np.ndarray | None = None

    @property
    def selector_bytes(self) -> int:
        """One logical selector stream aligned once, never per row-slice."""
        return align64(math.ceil(self.selector_bits / 8)) if self.selector_bits else 0

    @property
    def row_pointer_stream_bytes(self) -> int:
        """One 64-byte-aligned row-pointer stream, if the format uses one."""
        return align64(self.row_pointer_bytes) if self.row_pointer_bytes else 0

    @property
    def total_metadata_bytes(self) -> int:
        return self.support_bytes + self.row_pointer_stream_bytes + self.selector_bytes + self.descriptor_bytes

    @property
    def useful_transfer_bytes(self) -> int:
        """Logical bytes before cache-line replay; alignment is in ``layout``."""
        return self.value_bytes + self.total_metadata_bytes

    @property
    def pointer_base_bytes(self) -> int:
        """Physical byte address for the pointer stream, or ``-1`` if absent."""
        return self.layout.reserved_capacity_bytes if self.row_pointer_bytes else -1

    @property
    def selector_base_bytes(self) -> int:
        """Physical byte address for the selector stream, or ``-1`` if absent."""
        if not self.selector_bits:
            return -1
        return self.layout.reserved_capacity_bytes + self.row_pointer_stream_bytes


def _index_bits(feature_width: int) -> int:
    if feature_width <= 1:
        return 0
    return math.ceil(math.log2(feature_width))


def _slice_shape(features: int, slice_width: int, sid: int) -> tuple[int, int]:
    lo = sid * slice_width
    return lo, min(features, lo + slice_width)


def _row_payload_bytes(format_name: str, *, active: int, slice_features: int, full_features: int, value_bytes: int) -> int:
    """Exact packed payload bytes for one row-slice, excluding global streams."""
    if format_name == "DENSE":
        return slice_features * value_bytes
    if format_name == "CSR32":
        return active * (value_bytes + 4)
    if format_name == "CSR_PACKED":
        return active * value_bytes + math.ceil(active * _index_bits(full_features) / 8)
    if format_name == "BEICSR":
        return active * value_bytes + math.ceil(slice_features / 8)
    raise ValueError(f"unknown row-slice format {format_name}")


def _metadata_for_fixed(mask: np.ndarray, *, name: str, slice_width: int, value_bytes: int) -> tuple[int, int, int, int]:
    """Return value, support/index, row-pointer, descriptor bytes exactly."""
    rows, features = mask.shape
    slices = math.ceil(features / slice_width)
    active = int(mask.sum())
    if name == "DENSE":
        return rows * features * value_bytes, 0, 0, 0
    if name == "BEICSR":
        support = sum(rows * math.ceil((_slice_shape(features, slice_width, sid)[1] - _slice_shape(features, slice_width, sid)[0]) / 8) for sid in range(slices))
        # A 32-bit slice descriptor contains the active count and packed-value
        # offset. It is emitted per row-slice and is physically co-located in
        # the BEICSR layout.
        return active * value_bytes, support, 0, rows * slices * 4
    if name == "CSR32":
        # One globally packed CSR stream per row-slice needs exactly one 32-bit
        # pointer for each row-slice plus its terminal pointer.
        return active * value_bytes, active * 4, (rows * slices + 1) * 4, 0
    if name == "CSR_PACKED":
        # Each independently addressable row-slice owns a byte-packed ID
        # stream.  Rounding must therefore occur per row-slice, not once over
        # the full layer (which would undercount physical bytes).
        packed_ids = 0
        for node in range(rows):
            for sid in range(slices):
                lo, hi = _slice_shape(features, slice_width, sid)
                packed_ids += math.ceil(int(mask[node, lo:hi].sum()) * _index_bits(features) / 8)
        return active * value_bytes, packed_ids, (rows * slices + 1) * 4, 0
    raise ValueError(name)


def build_baseline_layout(
    mask: np.ndarray,
    *,
    name: BaselineName,
    slice_width: int,
    value_bytes: int = 1,
    node_order: np.ndarray | None = None,
) -> BaselineLayout:
    """Build an exact physical baseline layout without hidden metadata.

    ``INDEPENDENT_BEST`` has one aligned, bit-packed selector stream and is
    evaluated independently for every row-slice.  Ties resolve by the stable
    order in ``_ROW_FORMATS``; no post-hoc format preference is possible.
    """
    support = np.asarray(mask, dtype=bool)
    if support.ndim != 2:
        raise ValueError("mask must have shape (rows, features)")
    rows, features = support.shape
    if slice_width <= 0:
        raise ValueError("slice_width must be positive")
    slices = math.ceil(features / slice_width)
    if name != "INDEPENDENT_BEST":
        descriptor = 4 if name == "BEICSR" else 0
        layout = build_sliced_layout(
            support, slice_width=slice_width, format_name=name,
            value_bytes=value_bytes, descriptor_bytes=descriptor, node_order=node_order,
        )
        values, support_bytes, pointers, descriptors = _metadata_for_fixed(
            support, name=name, slice_width=slice_width, value_bytes=value_bytes,
        )
        return BaselineLayout(
            name=name, layout=layout, value_bytes=values, support_bytes=support_bytes,
            row_pointer_bytes=pointers, selector_bits=0, descriptor_bytes=descriptors,
            feature_id_bits=0 if name in {"DENSE", "BEICSR"} else _index_bits(features),
        )

    choices = np.empty((rows, slices), dtype=object)
    values = support_bytes = 0
    for node in range(rows):
        for sid in range(slices):
            lo, hi = _slice_shape(features, slice_width, sid)
            width = hi - lo
            active = int(support[node, lo:hi].sum())
            selected = min(
                _ROW_FORMATS,
                key=lambda fmt: (_row_payload_bytes(fmt, active=active, slice_features=width, full_features=features, value_bytes=value_bytes), _ROW_FORMATS.index(fmt)),
            )
            choices[node, sid] = selected
            if selected == "DENSE":
                values += width * value_bytes
            else:
                values += active * value_bytes
            support_bytes += _row_payload_bytes(selected, active=active, slice_features=width, full_features=features, value_bytes=value_bytes) - (width if selected == "DENSE" else active) * value_bytes
    layout = build_mixed_sliced_layout(
        support, slice_width=slice_width, formats=choices, value_bytes=value_bytes,
        descriptor_bytes=0, node_order=node_order,
    )
    # A 2-bit selector identifies one of the four legal row formats.  The
    # pointer stream is required even when the selected format is dense.
    return BaselineLayout(
        name="INDEPENDENT_BEST", layout=layout, value_bytes=values,
        support_bytes=support_bytes, row_pointer_bytes=(rows * slices + 1) * 4,
        selector_bits=2 * rows * slices, descriptor_bytes=0,
        feature_id_bits=_index_bits(features), selected_row_formats=choices,
    )


def baseline_names() -> tuple[BaselineName, ...]:
    """Stable baseline order for tables and plots."""
    return ("DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST")


if njit is not None:
    @njit(cache=True)
    def _simulate_baseline_lru_numba(starts, useful, slices, sources, capacity_bytes, associativity, pointer_base, selector_base, selector_bits):
        set_count = capacity_bytes // (LINE_BYTES * associativity)
        tags = np.full((set_count, associativity), -1, dtype=np.int64)
        ages = np.zeros((set_count, associativity), dtype=np.int64)
        accesses = hits = misses = tick = 0
        for source in sources:
            base = int(source) * slices
            for sid in range(slices):
                index = base + sid
                # A CSR pointer pair is needed to find the independently
                # packed row-slice payload.  Each 32-bit pointer maps to one
                # exact line; the base is 64-byte aligned.
                for address in (pointer_base + index * 4, pointer_base + (index + 1) * 4):
                    if pointer_base < 0:
                        continue
                    line = address // LINE_BYTES
                    accesses += 1; tick += 1
                    set_id = line % set_count; tag = line // set_count; found = -1
                    for way in range(associativity):
                        if tags[set_id, way] == tag:
                            found = way; break
                    if found >= 0:
                        hits += 1; ages[set_id, found] = tick
                    else:
                        misses += 1; victim = 0
                        for way in range(associativity):
                            if tags[set_id, way] < 0:
                                victim = way; break
                            if ages[set_id, way] < ages[set_id, victim]:
                                victim = way
                        tags[set_id, victim] = tag; ages[set_id, victim] = tick
                if selector_base >= 0:
                    line = (selector_base + (index * selector_bits) // 8) // LINE_BYTES
                    accesses += 1; tick += 1
                    set_id = line % set_count; tag = line // set_count; found = -1
                    for way in range(associativity):
                        if tags[set_id, way] == tag:
                            found = way; break
                    if found >= 0:
                        hits += 1; ages[set_id, found] = tick
                    else:
                        misses += 1; victim = 0
                        for way in range(associativity):
                            if tags[set_id, way] < 0:
                                victim = way; break
                            if ages[set_id, way] < ages[set_id, victim]:
                                victim = way
                        tags[set_id, victim] = tag; ages[set_id, victim] = tick
                first = starts[index] // LINE_BYTES
                last = (starts[index] + useful[index] - 1) // LINE_BYTES
                for line in range(first, last + 1):
                    accesses += 1; tick += 1
                    set_id = line % set_count; tag = line // set_count; found = -1
                    for way in range(associativity):
                        if tags[set_id, way] == tag:
                            found = way; break
                    if found >= 0:
                        hits += 1; ages[set_id, found] = tick
                    else:
                        misses += 1; victim = 0
                        for way in range(associativity):
                            if tags[set_id, way] < 0:
                                victim = way; break
                            if ages[set_id, way] < ages[set_id, victim]:
                                victim = way
                        tags[set_id, victim] = tag; ages[set_id, victim] = tick
        return accesses, hits, misses


def _baseline_line_trace(item: BaselineLayout, sources: np.ndarray) -> np.ndarray:
    """Small-input reference trace, including pointer and selector reads."""
    lines: list[np.ndarray] = []
    layout = item.layout
    for source in np.asarray(sources, dtype=np.int64):
        for sid in range(layout.slices):
            index = int(source) * layout.slices + sid
            if item.pointer_base_bytes >= 0:
                lines.append(np.asarray([
                    (item.pointer_base_bytes + index * 4) // LINE_BYTES,
                    (item.pointer_base_bytes + (index + 1) * 4) // LINE_BYTES,
                ], dtype=np.int64))
            if item.selector_base_bytes >= 0:
                lines.append(np.asarray([
                    (item.selector_base_bytes + (index * item.selector_bits // (layout.starts.size))) // LINE_BYTES,
                ], dtype=np.int64))
            lines.append(touched_lines(*layout.range_for(int(source), sid)))
    return np.concatenate(lines) if lines else np.empty(0, dtype=np.int64)


def simulate_baseline_layout_lru(
    item: BaselineLayout,
    sources: np.ndarray,
    *,
    capacity_bytes: int,
    associativity: int = 16,
    use_numba: bool = True,
) -> CacheTraffic:
    """Replay exact baseline metadata and value addresses through one LRU cache."""
    if capacity_bytes < LINE_BYTES * associativity:
        raise ValueError("cache is smaller than one full set")
    ids = np.asarray(sources, dtype=np.int64)
    if len(ids) and (ids.min() < 0 or ids.max() >= item.layout.starts.size // item.layout.slices):
        raise ValueError("source ID outside baseline layout")
    if use_numba and njit is not None:
        accesses, hits, misses = _simulate_baseline_lru_numba(
            item.layout.starts, item.layout.useful_bytes, item.layout.slices, ids,
            int(capacity_bytes), int(associativity), int(item.pointer_base_bytes),
            int(item.selector_base_bytes), 2 if item.selector_bits else 0,
        )
        return CacheTraffic(int(accesses), int(hits), int(misses), 0, -1)
    return simulate_set_associative_lru(
        _baseline_line_trace(item, ids), capacity_bytes=capacity_bytes, associativity=associativity,
    )
