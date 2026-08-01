"""Common exact physical layout and cache traffic model for XORFLOW studies.

The model is intentionally format-neutral.  It assigns every original node and
feature slice one fixed, 64-byte-aligned in-place reservation.  Unused tail
capacity affects storage capacity but is never fetched unless a useful byte
shares its cache line.  This makes BEICSR and XORFLOW traffic comparisons
fair: both replay identical source accesses through the same set-associative
feature cache.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

try:  # Optional acceleration; tests always retain the pure-Python oracle.
    from numba import njit
except ImportError:  # pragma: no cover - developer environments may omit numba
    njit = None

from .delta_encoding import align64


LINE_BYTES = 64


@dataclass(frozen=True)
class SliceLayout:
    """Fixed-address layout for a single layer's row/slice activation values."""

    starts: np.ndarray
    useful_bytes: np.ndarray
    capacity_bytes: int
    slices: int
    feature_width: int
    value_bytes: int
    descriptor_bytes: int
    support_bytes_per_slice: int
    format_name: str
    capacities: np.ndarray | None = None

    @property
    def reserved_capacity_bytes(self) -> int:
        return int(self.capacities.sum()) if self.capacities is not None else int(self.starts.size * self.capacity_bytes)

    @property
    def useful_value_bytes(self) -> int:
        # Descriptor/support bytes are not activation values.
        return int(self.useful_bytes.sum() - self.starts.size * (self.descriptor_bytes + self.support_bytes_per_slice))

    @property
    def useful_layout_bytes(self) -> int:
        return int(self.useful_bytes.sum())

    @property
    def alignment_waste_bytes(self) -> int:
        # Exact physical tail capacity; it consumes capacity but is not read.
        return self.reserved_capacity_bytes - self.useful_layout_bytes

    def range_for(self, node: int, slice_id: int) -> tuple[int, int]:
        index = int(node) * self.slices + int(slice_id)
        return int(self.starts[index]), int(self.useful_bytes[index])

    def capacity_for(self, index: int) -> int:
        return int(self.capacities[index]) if self.capacities is not None else self.capacity_bytes


def _format_support_bytes(
    slice_features: int,
    format_name: str,
    *,
    active_count: int | None = None,
    full_feature_width: int | None = None,
) -> int:
    """Return exact support/index bytes for one physical row-slice.

    ``active_count`` is deliberately explicit: bitmap formats depend only on
    the slice universe whereas CSR formats depend on the encoded set size.
    This single accounting function is shared by every baseline so a format
    cannot receive free indices or an unmodelled selector.
    """
    if format_name == "BEICSR":
        return math.ceil(slice_features / 8)
    if format_name == "XORFLOW":
        # Support lives in the tile-level anchor/exception stream.
        return 0
    if format_name == "DENSE":
        return 0
    if format_name == "CSR32":
        return 4 * int(active_count or 0)
    if format_name == "CSR_PACKED":
        if full_feature_width is None or full_feature_width <= 1:
            raise ValueError("CSR_PACKED requires full_feature_width > 1")
        index_bits = math.ceil(math.log2(full_feature_width))
        return math.ceil(index_bits * int(active_count or 0) / 8)
    raise ValueError(f"unknown physical format: {format_name}")


def _value_count(slice_features: int, active_count: int, format_name: str) -> int:
    """Return stored values for a legal row-slice format."""
    return slice_features if format_name == "DENSE" else int(active_count)


def build_sliced_layout(
    mask: np.ndarray,
    *,
    slice_width: int,
    format_name: str,
    value_bytes: int = 1,
    descriptor_bytes: int = 4,
    reserve_bytes: int | None = None,
    node_order: np.ndarray | None = None,
) -> SliceLayout:
    """Create legal non-overlapping row-slice reservations.

    XORFLOW stores FP8 packed values only; BEICSR additionally embeds one
    bitmap per row/slice.  Both receive a capacity sufficient for the densest
    legal representation of their own format.  The returned starts are stable
    for a given shape and format and can be used directly in address traces.
    """
    support = np.asarray(mask, dtype=bool)
    if support.ndim != 2:
        raise ValueError("mask must have shape (rows, features)")
    rows, features = support.shape
    if slice_width <= 0:
        raise ValueError("slice_width must be positive")
    slices = math.ceil(features / slice_width)
    maximum_feature_count = min(slice_width, features)
    max_support = _format_support_bytes(
        maximum_feature_count, format_name,
        active_count=maximum_feature_count, full_feature_width=features,
    )
    minimum_capacity = align64(
        descriptor_bytes + max_support + _value_count(maximum_feature_count, maximum_feature_count, format_name) * value_bytes
    )
    capacity = int(reserve_bytes) if reserve_bytes is not None else minimum_capacity
    if capacity < minimum_capacity or capacity % LINE_BYTES:
        raise ValueError("reserve_bytes must be aligned and cover the dense row slice")
    if node_order is None:
        order = np.arange(rows, dtype=np.int64)
    else:
        order = np.asarray(node_order, dtype=np.int64)
        if order.shape != (rows,) or len(np.unique(order)) != rows or order.min() != 0 or order.max() != rows - 1:
            raise ValueError("node_order must be a permutation of every original node ID")
    # starts remains indexed by original node ID, while reservation slots follow
    # the topology order.  No aggregation arithmetic is changed by this layout.
    starts = np.empty(rows * slices, dtype=np.int64)
    for slot, node in enumerate(order):
        starts[int(node) * slices:(int(node) + 1) * slices] = (
            np.arange(slices, dtype=np.int64) + slot * slices
        ) * capacity
    useful = np.empty(rows * slices, dtype=np.int64)
    for sid in range(slices):
        lo, hi = sid * slice_width, min(features, (sid + 1) * slice_width)
        active = support[:, lo:hi].sum(axis=1, dtype=np.int64)
        support_bytes = np.asarray([
            _format_support_bytes(
                hi - lo, format_name, active_count=int(count), full_feature_width=features,
            ) for count in active
        ], dtype=np.int64)
        stored_values = np.asarray([
            _value_count(hi - lo, int(count), format_name) for count in active
        ], dtype=np.int64)
        useful[sid::slices] = descriptor_bytes + support_bytes + stored_values * value_bytes
    return SliceLayout(
        starts=starts,
        useful_bytes=useful,
        capacity_bytes=capacity,
        slices=slices,
        feature_width=features,
        value_bytes=value_bytes,
        descriptor_bytes=descriptor_bytes,
        support_bytes_per_slice=max_support,
        format_name=format_name,
    )


def build_mixed_sliced_layout(
    mask: np.ndarray,
    *,
    slice_width: int,
    formats: np.ndarray,
    value_bytes: int = 1,
    descriptor_bytes: int = 4,
    node_order: np.ndarray | None = None,
) -> SliceLayout:
    """Build a fixed in-place layout with a legal format selector per slice.

    ``formats`` has shape ``(rows, slices)`` and currently permits BEICSR and
    XORFLOW.  Each entry gets exactly the reservation required by its chosen
    format, and starts remain indexed by original node ID.  This is the layout
    used for a selector-equipped deployment; there is no hidden global choice.
    """
    support = np.asarray(mask, dtype=bool)
    rows, features = support.shape
    slices = math.ceil(features / slice_width)
    choice = np.asarray(formats, dtype=object)
    if choice.shape != (rows, slices):
        raise ValueError("formats must have shape (rows, ceil(features/slice_width))")
    if node_order is None:
        order = np.arange(rows, dtype=np.int64)
    else:
        order = np.asarray(node_order, dtype=np.int64)
        if order.shape != (rows,) or len(np.unique(order)) != rows:
            raise ValueError("node_order must be a permutation")
    starts = np.empty(rows * slices, dtype=np.int64)
    useful = np.empty(rows * slices, dtype=np.int64)
    capacities = np.empty(rows * slices, dtype=np.int64)
    cursor = 0
    for node in order:
        for sid in range(slices):
            index = int(node) * slices + sid
            lo, hi = sid * slice_width, min(features, (sid + 1) * slice_width)
            fmt = str(choice[int(node), sid])
            active = int(support[int(node), lo:hi].sum())
            support_bytes = _format_support_bytes(
                hi - lo, fmt, active_count=active, full_feature_width=features,
            )
            cap = align64(
                descriptor_bytes
                + _format_support_bytes(hi - lo, fmt, active_count=hi - lo, full_feature_width=features)
                + _value_count(hi - lo, hi - lo, fmt) * value_bytes
            )
            starts[index] = cursor
            capacities[index] = cap
            useful[index] = descriptor_bytes + support_bytes + _value_count(hi - lo, active, fmt) * value_bytes
            cursor += cap
    return SliceLayout(
        starts=starts, useful_bytes=useful, capacity_bytes=int(capacities.max()),
        slices=slices, feature_width=features, value_bytes=value_bytes,
        descriptor_bytes=descriptor_bytes, support_bytes_per_slice=0,
        format_name="MIXED", capacities=capacities,
    )


def validate_nonoverlap(layout: SliceLayout) -> bool:
    """Return true when every reserved row-slice range is disjoint."""
    order = np.argsort(layout.starts)
    starts = layout.starts[order]
    caps = (
        layout.capacities[order] if layout.capacities is not None
        else np.full(len(starts), layout.capacity_bytes, dtype=np.int64)
    )
    return bool(np.all(starts[1:] >= starts[:-1] + caps[:-1]))


def touched_lines(start: int, byte_count: int) -> np.ndarray:
    """Enumerate exactly the cache lines containing useful bytes."""
    if byte_count <= 0:
        return np.empty(0, dtype=np.int64)
    return np.arange(start // LINE_BYTES, (start + byte_count - 1) // LINE_BYTES + 1, dtype=np.int64)


def source_line_trace(
    layout: SliceLayout,
    sources: np.ndarray,
) -> np.ndarray:
    """Materialize exact feature cache-line accesses in the supplied edge order."""
    ids = np.asarray(sources, dtype=np.int64)
    if len(ids) and (ids.min() < 0 or ids.max() >= layout.starts.size // layout.slices):
        raise ValueError("source ID outside layout")
    per_node: list[np.ndarray] = []
    for node in range(layout.starts.size // layout.slices):
        lines = [touched_lines(*layout.range_for(node, sid)) for sid in range(layout.slices)]
        per_node.append(np.concatenate(lines) if lines else np.empty(0, dtype=np.int64))
    counts = np.asarray([len(per_node[int(node)]) for node in ids], dtype=np.int64)
    result = np.empty(int(counts.sum()), dtype=np.int64)
    cursor = 0
    for node in ids:
        current = per_node[int(node)]
        result[cursor:cursor + len(current)] = current
        cursor += len(current)
    return result


@dataclass(frozen=True)
class CacheTraffic:
    accesses: int
    hits: int
    misses: int
    dirty_writebacks: int
    unique_lines: int

    @property
    def hit_rate(self) -> float:
        return self.hits / max(self.accesses, 1)

    @property
    def read_bytes(self) -> int:
        return self.misses * LINE_BYTES

    @property
    def writeback_bytes(self) -> int:
        return self.dirty_writebacks * LINE_BYTES


if njit is not None:
    @njit(cache=True)
    def _stream_read_lru(starts, useful, slices, sources, capacity_bytes, associativity):
        set_count = capacity_bytes // (64 * associativity)
        tags = np.full((set_count, associativity), -1, dtype=np.int64)
        ages = np.zeros((set_count, associativity), dtype=np.int64)
        hits = 0
        misses = 0
        accesses = 0
        tick = 0
        for source in sources:
            row_base = int(source) * slices
            for sid in range(slices):
                index = row_base + sid
                first = starts[index] // 64
                last = (starts[index] + useful[index] - 1) // 64
                for line in range(first, last + 1):
                    accesses += 1
                    tick += 1
                    set_id = line % set_count
                    tag = line // set_count
                    found = -1
                    for way in range(associativity):
                        if tags[set_id, way] == tag:
                            found = way
                            break
                    if found >= 0:
                        hits += 1
                        ages[set_id, found] = tick
                    else:
                        misses += 1
                        victim = 0
                        for way in range(associativity):
                            if tags[set_id, way] < 0:
                                victim = way
                                break
                            if ages[set_id, way] < ages[set_id, victim]:
                                victim = way
                        tags[set_id, victim] = tag
                        ages[set_id, victim] = tick
        return accesses, hits, misses

    @njit(cache=True)
    def _miss_trace_lru(lines, capacity_bytes, associativity):
        """Return cache-miss line IDs in exact request order for DRAM traces."""
        set_count = capacity_bytes // (64 * associativity)
        tags = np.full((set_count, associativity), -1, dtype=np.int64)
        ages = np.zeros((set_count, associativity), dtype=np.int64)
        output = np.empty(len(lines), dtype=np.int64)
        count = 0
        tick = 0
        for line in lines:
            tick += 1
            set_id = line % set_count
            tag = line // set_count
            found = -1
            for way in range(associativity):
                if tags[set_id, way] == tag:
                    found = way
                    break
            if found >= 0:
                ages[set_id, found] = tick
                continue
            output[count] = line
            count += 1
            victim = 0
            for way in range(associativity):
                if tags[set_id, way] < 0:
                    victim = way
                    break
                if ages[set_id, way] < ages[set_id, victim]:
                    victim = way
            tags[set_id, victim] = tag
            ages[set_id, victim] = tick
        return output[:count]


def simulate_layout_source_lru(
    layout: SliceLayout,
    sources: np.ndarray,
    *,
    capacity_bytes: int,
    associativity: int = 16,
    use_numba: bool = True,
) -> CacheTraffic:
    """Exact read-only feature-cache traffic without materializing edge traces.

    This is critical for Reddit-scale graphs: it preserves the exact neighbor
    order while holding only source IDs and cache state, rather than allocating
    a many-gigabyte line-ID vector.  The Numba path is checked against the
    reference LRU simulator in unit tests.
    """
    values = np.asarray(sources, dtype=np.int64)
    if use_numba and njit is not None:
        accesses, hits, misses = _stream_read_lru(
            layout.starts, layout.useful_bytes, layout.slices, values,
            int(capacity_bytes), int(associativity),
        )
        # Unique-line count is a reporting-only statistic; computing the exact
        # set for giant graphs would violate the streaming-memory objective.
        return CacheTraffic(int(accesses), int(hits), int(misses), 0, -1)
    return simulate_set_associative_lru(
        source_line_trace(layout, values), capacity_bytes=capacity_bytes,
        associativity=associativity,
    )


def materialize_cache_miss_lines(
    layout: SliceLayout,
    sources: np.ndarray,
    *,
    capacity_bytes: int,
    associativity: int = 16,
) -> np.ndarray:
    """Materialize ordered misses only for a bounded external DRAM run.

    Principal cache studies use :func:`simulate_layout_source_lru` and remain
    streaming.  A Ramulator frontend presently accepts an ordered request
    stream, so this helper is intentionally isolated for one selected trace
    and callers must delete the transient file after parsing timing results.
    """
    lines = source_line_trace(layout, np.asarray(sources, dtype=np.int64))
    if njit is not None:
        return _miss_trace_lru(lines, int(capacity_bytes), int(associativity))
    # Slow but exact fallback for developer environments without numba.
    cache = np.full((capacity_bytes // (LINE_BYTES * associativity), associativity), -1, dtype=np.int64)
    ages = np.zeros_like(cache)
    result: list[int] = []
    tick = 0
    for line in lines:
        tick += 1; set_id = int(line % len(cache)); tag = int(line // len(cache)); found = np.where(cache[set_id] == tag)[0]
        if len(found):
            ages[set_id, found[0]] = tick; continue
        result.append(int(line)); victim = int(np.argmin(ages[set_id])); empty = np.where(cache[set_id] < 0)[0]
        if len(empty): victim = int(empty[0])
        cache[set_id, victim] = tag; ages[set_id, victim] = tick
    return np.asarray(result, dtype=np.int64)


def simulate_set_associative_lru(
    lines: np.ndarray,
    *,
    capacity_bytes: int,
    associativity: int = 16,
    write_lines: set[int] | None = None,
) -> CacheTraffic:
    """Reference 64-byte set-associative LRU simulation.

    A compact Python reference is used for correctness and is intentionally
    deterministic.  Large principal runs may substitute an equivalent Numba
    backend, which must be checked against this function on sampled traces.
    """
    if capacity_bytes < LINE_BYTES * associativity:
        raise ValueError("cache is smaller than one full set")
    set_count = capacity_bytes // (LINE_BYTES * associativity)
    tags = np.full((set_count, associativity), -1, dtype=np.int64)
    ages = np.zeros((set_count, associativity), dtype=np.int64)
    dirty = np.zeros((set_count, associativity), dtype=bool)
    writes = write_lines or set()
    hits = misses = writebacks = 0
    tick = 0
    for raw_line in np.asarray(lines, dtype=np.int64):
        line = int(raw_line)
        tick += 1
        set_id, tag = line % set_count, line // set_count
        found = -1
        for way in range(associativity):
            if tags[set_id, way] == tag:
                found = way
                break
        is_write = line in writes
        if found >= 0:
            hits += 1
            ages[set_id, found] = tick
            dirty[set_id, found] = dirty[set_id, found] or is_write
            continue
        misses += 1
        victim = int(np.argmin(ages[set_id]))
        for way in range(associativity):
            if tags[set_id, way] < 0:
                victim = way
                break
        if tags[set_id, victim] >= 0 and dirty[set_id, victim]:
            writebacks += 1
        tags[set_id, victim] = tag
        ages[set_id, victim] = tick
        dirty[set_id, victim] = is_write
    return CacheTraffic(
        accesses=int(len(lines)), hits=hits, misses=misses,
        dirty_writebacks=writebacks, unique_lines=int(len(set(np.asarray(lines, dtype=np.int64).tolist()))),
    )
