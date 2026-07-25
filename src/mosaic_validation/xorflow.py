"""Exact MOSAIC-XORFLOW support coding and memory-traffic primitives.

The implementation deliberately keeps support and values separate: support is
encoded once for a tile/slice and values are addressed in increasing feature
order.  All byte counts include explicit descriptors and 64-byte alignment.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from collections import OrderedDict
import numpy as np

from .delta_encoding import align64
from .global_gap import EventCode, encode_event_set, entropy_lower_bound_bits


def majority_anchor(window: np.ndarray) -> np.ndarray:
    """Return the Hamming-optimal temporal majority anchor (ties are zero)."""
    x = np.asarray(window, dtype=bool)
    return (x.sum(axis=0) > (x.shape[0] / 2)).astype(bool)


def _anchor_objective(window: np.ndarray, anchor: np.ndarray) -> tuple[int, list[EventCode]]:
    codes = [encode_event_set(np.logical_xor(layer, anchor).reshape(-1)) for layer in window]
    bits = int(anchor.size)
    bits += sum(c.encoded_bits for c in codes)
    bits += 8 * (len(codes) + 2)  # selectors and offsets
    return bits, codes


def refine_anchor(window: np.ndarray, initial: np.ndarray | None = None, max_passes: int = 2) -> tuple[np.ndarray, list[int], list[EventCode]]:
    """Exact coordinate descent over anchor bits with monotone objective history."""
    x = np.asarray(window, dtype=bool)
    anchor = majority_anchor(x) if initial is None else np.asarray(initial, dtype=bool).copy()
    value, codes = _anchor_objective(x, anchor)
    history = [value]
    for _ in range(max_passes):
        changed = False
        for i in range(anchor.shape[0]):
            for j in range(anchor.shape[1]):
                trial = anchor.copy(); trial[i, j] = ~trial[i, j]
                trial_value, trial_codes = _anchor_objective(x, trial)
                if trial_value < value:
                    anchor, value, codes = trial, trial_value, trial_codes
                    history.append(value); changed = True
        if not changed:
            break
    assert all(history[i] >= history[i + 1] for i in range(len(history) - 1))
    return anchor, history, codes


def prototype_dictionary(anchor: np.ndarray, k: int) -> dict:
    """Deterministic farthest-first binary prototype dictionary."""
    rows = np.asarray(anchor, dtype=bool)
    n, c = rows.shape
    k = max(1, min(int(k), n))
    density = rows.sum(axis=1)
    first = int(np.argmax(density))
    ids = [first]
    while len(ids) < k:
        d = np.min(np.asarray([np.count_nonzero(rows ^ rows[p], axis=1) for p in ids]), axis=0)
        d[ids] = -1
        ids.append(int(np.argmax(d)))
    prototypes = rows[ids].copy()
    assignment = np.zeros(n, dtype=np.int64)
    for _ in range(4):
        distances = np.asarray([np.count_nonzero(rows ^ p, axis=1) for p in prototypes]).T
        assignment = np.argmin(distances, axis=1)
        new = prototypes.copy()
        for p in range(k):
            members = rows[assignment == p]
            if len(members):
                new[p] = members.sum(axis=0) > (len(members) / 2)
        if np.array_equal(new, prototypes):
            break
        prototypes = new
    residual = rows ^ prototypes[assignment]
    codes = [encode_event_set(r) for r in residual]
    bits = int(prototypes.size) + n * max(1, math.ceil(math.log2(k + 1))) + sum(x.encoded_bits for x in codes) + 16
    return {"prototypes": prototypes, "assignment": assignment, "residual": residual, "codes": codes, "bits": bits}


def select_spatial_dictionary(anchor: np.ndarray, cohort_size: int = 32) -> tuple[str, int, dict]:
    """Choose the exact minimum among independent rows and prototype variants."""
    rows = np.asarray(anchor, dtype=bool)
    a0 = sum(encode_event_set(r).encoded_bits for r in rows) + 16 * rows.shape[0]
    candidates = [(a0, "A0", 0, {"rows": rows, "bits": a0})]
    for k in (1, 2, 4, 8, 16):
        d = prototype_dictionary(rows, k)
        candidates.append((d["bits"], "A1", k, d))
    # A2 is cohort-local and uses the same exact dictionary accounting.
    pieces = []
    for start in range(0, rows.shape[0], cohort_size):
        d = prototype_dictionary(rows[start:start + cohort_size], min(4, cohort_size))
        pieces.append(d)
    a2 = sum(d["bits"] for d in pieces) + 16 * len(pieces)
    candidates.append((
        a2,
        "A2",
        sum(len(d["prototypes"]) for d in pieces),
        {"pieces": pieces, "bits": a2},
    ))
    return min(candidates, key=lambda x: (x[0], x[1]))[1:]


def encode_slice(window: np.ndarray, slice_start: int, slice_width: int, cohort_size: int = 32) -> dict:
    """Encode one tile/window feature slice and return exact accounting."""
    x = np.asarray(window, dtype=bool)
    sl = x[:, :, slice_start:slice_start + slice_width]
    # Exhaustive coordinate refinement is reserved for tiny correctness tests.
    # On real tiles, temporal majority is the exact Hamming optimum and avoids
    # an O(n*C*W*n*C) recomputation of global event streams.
    if sl.shape[1] * sl.shape[2] <= 64:
        anchor, history, codes = refine_anchor(sl)
    else:
        anchor = majority_anchor(sl)
        objective, codes = _anchor_objective(sl, anchor)
        history = [objective]
    variant, k, dictionary = select_spatial_dictionary(anchor, cohort_size)
    exception_bits = sum(c.encoded_bits for c in codes)
    anchor_bits = int(dictionary["bits"])
    selectors = 8 * (len(codes) + 3)
    support_bits = anchor_bits + exception_bits + selectors
    entropy = sum(entropy_lower_bound_bits(anchor.size, int(np.logical_xor(layer, anchor).sum())) for layer in sl)
    return {"anchor": anchor, "codes": codes, "variant": variant, "prototype_count": k,
            "objective_history": history, "support_bits": support_bits,
            "anchor_bits": anchor_bits, "exception_bits": exception_bits,
            "entropy_bits": entropy, "exact": all(np.array_equal(c.decode().reshape(anchor.shape) ^ anchor, layer) for c, layer in zip(codes, sl)),
            "nnz": int(sl.sum()), "slice": sl}


def decode_slice(encoded: dict) -> np.ndarray:
    a = encoded["anchor"]
    return np.stack([code.decode().reshape(a.shape) ^ a for code in encoded["codes"]])


@dataclass(frozen=True)
class RowSliceAddress:
    row: int
    start: int
    capacity: int


def row_slice_layout(rows: int, width: int, slice_width: int, value_bytes: int = 4) -> list[RowSliceAddress]:
    """Generate non-overlapping fixed in-place row-slice regions."""
    cap = align64(width * value_bytes + math.ceil(width / 8) + 16)
    out = []
    for row in range(rows):
        for s in range(math.ceil(width / slice_width)):
            out.append(RowSliceAddress(row * math.ceil(width / slice_width) + s, (row * math.ceil(width / slice_width) + s) * cap, cap))
    return out


def touched_cache_lines(start: int, useful_bytes: int) -> int:
    if useful_bytes <= 0:
        return 0
    return len(range(start // 64, (start + useful_bytes - 1) // 64 + 1))


class LRUCache:
    """Deterministic set-associative-ish line cache used by the quick model."""
    def __init__(self, capacity_bytes: int, line_bytes: int = 64, associativity: int = 16):
        self.lines = max(1, capacity_bytes // line_bytes)
        self.associativity = associativity
        self.data: OrderedDict[int, bool] = OrderedDict()
        self.accesses = self.hits = self.misses = self.writebacks = 0

    def access(self, line: int, write: bool = False) -> bool:
        self.accesses += 1
        if line in self.data:
            self.hits += 1; dirty = self.data.pop(line) or write; self.data[line] = dirty; return True
        self.misses += 1
        if len(self.data) >= self.lines:
            _, dirty = self.data.popitem(last=False); self.writebacks += int(dirty)
        self.data[line] = write
        return False


def cache_traffic(addresses: list[tuple[int, int, bool]], capacity_bytes: int) -> dict[str, int | float]:
    cache = LRUCache(capacity_bytes)
    unique = set(); read = write = 0
    for start, size, is_write in addresses:
        for line in range(start // 64, (start + max(size, 1) - 1) // 64 + 1):
            unique.add(line); cache.access(line, is_write)
            if is_write: write += 64
            else: read += 64
    return {"cache_accesses": cache.accesses, "cache_hits": cache.hits, "cache_misses": cache.misses,
            "cache_hit_rate": cache.hits / max(cache.accesses, 1), "dirty_writebacks": cache.writebacks,
            "unique_lines": len(unique), "dram_read_bytes": read, "dram_write_bytes": write}


def aggregation_order(edge_index: np.ndarray, destination_count: int, source_tile: int | None = None) -> list[tuple[int, int]]:
    """Return deterministic source accesses in CSR destination or source-tiled order."""
    edges = np.asarray(edge_index, dtype=np.int64)
    pairs = list(zip(edges[1].tolist(), edges[0].tolist()))
    if source_tile is None:
        return sorted(pairs, key=lambda x: (x[0], x[1]))
    return sorted(pairs, key=lambda x: (x[0], x[1] // source_tile, x[1]))
