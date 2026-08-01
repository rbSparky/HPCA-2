"""Exact global event-set formats and stable entropy accounting."""

from dataclasses import dataclass
import math

import numpy as np


def bits_for(value_count: int) -> int:
    return max(1, math.ceil(math.log2(max(value_count, 2))))


def entropy_lower_bound_bits(universe: int, events: int) -> int:
    """Return ceil(log2(binomial(U,k))) without constructing the binomial."""
    if events < 0 or events > universe:
        raise ValueError("event count outside universe")
    if events in (0, universe):
        return 0
    log_choose = (
        math.lgamma(universe + 1)
        - math.lgamma(events + 1)
        - math.lgamma(universe - events + 1)
    ) / math.log(2)
    return int(math.ceil(log_choose - 1e-12))


@dataclass(frozen=True)
class EventCode:
    universe: int
    events: tuple[int, ...]
    selected_format: str
    encoded_bits: int
    gap_block_events: int
    complement: bool = False

    def decode(self) -> np.ndarray:
        out = np.zeros(self.universe, dtype=bool)
        if self.complement:
            out[:] = True
            out[list(self.events)] = False
        elif self.events:
            out[list(self.events)] = True
        return out


def _block_for_bits(events: np.ndarray, universe: int, block: int) -> int:
    count_bits = bits_for(universe + 1)
    id_bits = bits_for(universe)
    width_header = bits_for(id_bits + 1)
    total = 2 + 2 + count_bits  # format selector, block selector, event count
    for start in range(0, len(events), block):
        values = events[start : start + block]
        total += id_bits
        if len(values) > 1:
            gaps = np.diff(values)
            gap_width = bits_for(int(gaps.max()) + 1)
            total += width_header + gap_width * len(gaps)
        else:
            total += width_header
    return total


def candidate_event_bits(
    event_ids: np.ndarray,
    universe: int,
    blocks: tuple[int, ...] = (8, 16, 32),
    allow_complement: bool = False,
) -> dict[tuple[str, int, bool], int]:
    events = np.unique(np.asarray(event_ids, dtype=np.int64))
    if len(events) and (events[0] < 0 or events[-1] >= universe):
        raise ValueError("event ID outside universe")
    count_bits = bits_for(universe + 1)
    id_bits = bits_for(universe)
    candidates: dict[tuple[str, int, bool], int] = {
        ("DENSE_XOR", 0, False): 2 + universe,
        ("FIXED_IDS", 0, False): 2 + count_bits + len(events) * id_bits,
    }
    for block in blocks:
        candidates[("BLOCK_FOR_GAPS", block, False)] = _block_for_bits(
            events, universe, block
        )
    if allow_complement:
        zeros = universe - len(events)
        candidates[("ZERO_IDS", 0, True)] = 2 + 1 + count_bits + zeros * id_bits
    return candidates


def encode_event_set(
    mask_or_ids: np.ndarray,
    universe: int | None = None,
    blocks: tuple[int, ...] = (8, 16, 32),
    allow_complement: bool = False,
) -> EventCode:
    array = np.asarray(mask_or_ids)
    if array.dtype == np.bool_:
        universe = int(array.size)
        events = np.flatnonzero(array)
    else:
        if universe is None:
            raise ValueError("universe is required for ID input")
        events = np.unique(array.astype(np.int64))
    candidates = candidate_event_bits(events, int(universe), blocks, allow_complement)
    selected = min(candidates, key=lambda key: (candidates[key], key))
    fmt, block, complement = selected
    stored = (
        tuple(np.setdiff1d(np.arange(universe), events).tolist())
        if complement else tuple(events.tolist())
    )
    return EventCode(int(universe), stored, fmt, candidates[selected], block, complement)

