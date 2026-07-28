"""Exact event coding constrained to a small, synthesizable decoder.

Unlike the entropy-oriented Phase-2 selector, this format intentionally fixes
all deltas to eight bits. Large gaps start a new independently dispatchable
block. The modest byte penalty buys predictable 64-bit/cycle lane throughput.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .global_gap import bits_for
from .xorflow import prototype_dictionary


@dataclass(frozen=True)
class HardwareEventCode:
    universe: int
    events: tuple[int, ...]
    selected_format: str
    encoded_bits: int
    blocks: tuple[tuple[int, ...], ...] = ()

    def decode(self) -> np.ndarray:
        result = np.zeros(self.universe, dtype=bool)
        if self.events:
            result[np.asarray(self.events, dtype=np.int64)] = True
        return result

    @property
    def lane_work_cycles(self) -> int:
        if self.selected_format == "DENSE_XOR":
            return math.ceil(self.universe / 64)
        if self.selected_format == "FIXED_IDS":
            return math.ceil(len(self.events) / 4)
        return sum(math.ceil(len(block) / 8) for block in self.blocks)


class _BitWriter:
    """Little-endian bit writer used by the deployable stream format."""

    def __init__(self) -> None:
        self._value = 0
        self.bits = 0

    def write(self, value: int, width: int) -> None:
        if width < 0 or value < 0 or value >= (1 << width):
            raise ValueError("bit field does not fit")
        self._value |= int(value) << self.bits
        self.bits += width

    def bytes(self) -> bytes:
        return self._value.to_bytes((self.bits + 7) // 8, "little")


class _BitReader:
    """Matching bounds-checked little-endian stream reader."""

    def __init__(self, payload: bytes, valid_bits: int) -> None:
        if valid_bits < 0 or valid_bits > len(payload) * 8:
            raise ValueError("invalid bit count")
        self._value = int.from_bytes(payload, "little")
        self._valid_bits = valid_bits
        self.position = 0

    def read(self, width: int) -> int:
        if width < 0 or self.position + width > self._valid_bits:
            raise ValueError("truncated hardware event stream")
        value = (self._value >> self.position) & ((1 << width) - 1)
        self.position += width
        return int(value)


def encode_hardware_event_set(mask_or_ids: np.ndarray, universe: int | None = None) -> HardwareEventCode:
    """Select dense, fixed-ID, or dispatchable fixed-gap8 encoding exactly."""
    value = np.asarray(mask_or_ids)
    if value.dtype == np.bool_:
        universe = int(value.size)
        events = np.flatnonzero(value)
    else:
        if universe is None:
            raise ValueError("universe is required for ID input")
        events = np.unique(value.astype(np.int64))
    universe = int(universe)
    if len(events) and (events[0] < 0 or events[-1] >= universe):
        raise ValueError("event ID outside universe")
    count_bits = bits_for(universe + 1)
    id_bits = bits_for(universe)
    blocks: list[np.ndarray] = []
    start = 0
    for index in range(1, len(events)):
        if index - start >= 32 or int(events[index] - events[index - 1]) > 255:
            blocks.append(events[start:index])
            start = index
    if len(events):
        blocks.append(events[start:])
    candidates = {
        "DENSE_XOR": 2 + universe,
        "FIXED_IDS": 2 + count_bits + len(events) * id_bits,
        "FIXED_GAP8": (
            2 + 2 + count_bits + 8
            + sum(id_bits + 5 + 8 * max(0, len(block) - 1) for block in blocks)
        ),
    }
    selected = min(candidates, key=lambda name: (candidates[name], name))
    return HardwareEventCode(
        universe,
        tuple(int(x) for x in events),
        selected,
        int(candidates[selected]),
        tuple(tuple(int(x) for x in block) for block in blocks)
        if selected == "FIXED_GAP8" else (),
    )


def pack_hardware_event_code(code: HardwareEventCode) -> tuple[bytes, int]:
    """Return the exact hardware byte stream and its meaningful bit count.

    The descriptor supplies the universe.  The payload itself uses the same
    field widths as :func:`encode_hardware_event_set`, so ``bit_count`` is
    guaranteed to equal ``code.encoded_bits`` rather than being a separate
    accounting approximation.
    """
    writer = _BitWriter()
    count_bits = bits_for(code.universe + 1)
    id_bits = bits_for(code.universe)
    events = tuple(int(value) for value in code.events)
    if code.selected_format == "DENSE_XOR":
        writer.write(0, 2)
        bitmap = code.decode()
        for bit in bitmap:
            writer.write(int(bit), 1)
    elif code.selected_format == "FIXED_IDS":
        writer.write(1, 2)
        writer.write(len(events), count_bits)
        for event in events:
            writer.write(event, id_bits)
    elif code.selected_format == "FIXED_GAP8":
        writer.write(2, 2)
        writer.write(0, 2)  # fixed eight-bit gap policy selector
        writer.write(len(events), count_bits)
        writer.write(len(code.blocks), 8)
        for block in code.blocks:
            if not block or len(block) > 32:
                raise ValueError("invalid fixed-gap8 block")
            writer.write(block[0], id_bits)
            writer.write(len(block), 5)
            for previous, current in zip(block, block[1:], strict=False):
                gap = int(current - previous)
                if gap <= 0 or gap > 255:
                    raise ValueError("fixed-gap8 block has an illegal gap")
                writer.write(gap, 8)
    else:  # pragma: no cover - protects future enum additions
        raise ValueError(f"unsupported event format: {code.selected_format}")
    if writer.bits != code.encoded_bits:
        raise AssertionError((writer.bits, code.encoded_bits, code.selected_format))
    return writer.bytes(), writer.bits


def unpack_hardware_event_code(payload: bytes, bit_count: int, universe: int) -> HardwareEventCode:
    """Decode one exact deployable event stream without predecessor state."""
    reader = _BitReader(payload, bit_count)
    selected = reader.read(2)
    count_bits = bits_for(universe + 1)
    id_bits = bits_for(universe)
    if selected == 0:
        events = tuple(index for index in range(universe) if reader.read(1))
        result = HardwareEventCode(universe, events, "DENSE_XOR", bit_count)
    elif selected == 1:
        count = reader.read(count_bits)
        events = tuple(reader.read(id_bits) for _ in range(count))
        result = HardwareEventCode(universe, events, "FIXED_IDS", bit_count)
    elif selected == 2:
        policy = reader.read(2)
        if policy != 0:
            raise ValueError("unsupported gap policy")
        expected_events = reader.read(count_bits)
        block_count = reader.read(8)
        blocks: list[tuple[int, ...]] = []
        events_list: list[int] = []
        for _ in range(block_count):
            first = reader.read(id_bits)
            length = reader.read(5)
            if length < 1 or length > 32:
                raise ValueError("invalid block length")
            block = [first]
            for _ in range(length - 1):
                block.append(block[-1] + reader.read(8))
            blocks.append(tuple(block))
            events_list.extend(block)
        if len(events_list) != expected_events:
            raise ValueError("event count does not match gap blocks")
        events = tuple(events_list)
        result = HardwareEventCode(universe, events, "FIXED_GAP8", bit_count, tuple(blocks))
    else:
        raise ValueError("reserved event format")
    if reader.position != bit_count or any(event >= universe for event in result.events):
        raise ValueError("malformed hardware event stream")
    if tuple(sorted(set(result.events))) != result.events:
        raise ValueError("event IDs must be sorted and unique")
    # Reconstructing through the selector checks that no inconsistent header
    # was accepted even if a caller passes a hand-constructed payload.
    expected = encode_hardware_event_set(np.asarray(result.events), universe=universe)
    if expected.selected_format != result.selected_format or expected.encoded_bits != bit_count:
        raise ValueError("stream does not satisfy its selected hardware format")
    return result


def select_hardware_dictionary(anchor: np.ndarray, cohort_size: int = 32) -> tuple[str, int, int]:
    """Choose A0/A1/A2 using the hardware-constrained residual code."""
    rows = np.asarray(anchor, dtype=bool)
    a0 = sum(encode_hardware_event_set(row).encoded_bits for row in rows) + 16 * len(rows)
    candidates: list[tuple[int, str, int]] = [(a0, "A0", 0)]
    id_bits_by_k: dict[int, int] = {}
    for k in (1, 2, 4, 8, 16):
        dictionary = prototype_dictionary(rows, k)
        actual_k = len(dictionary["prototypes"])
        id_bits_by_k[k] = max(1, math.ceil(math.log2(actual_k + 1)))
        bits = (
            int(dictionary["prototypes"].size)
            + len(rows) * id_bits_by_k[k]
            + sum(
                encode_hardware_event_set(residual).encoded_bits
                for residual in dictionary["residual"]
            )
            + 16
        )
        candidates.append((bits, "A1", actual_k))
    pieces = []
    for start in range(0, len(rows), cohort_size):
        local = rows[start : start + cohort_size]
        dictionary = prototype_dictionary(local, min(4, len(local)))
        actual_k = len(dictionary["prototypes"])
        bits = (
            int(dictionary["prototypes"].size)
            + len(local) * max(1, math.ceil(math.log2(actual_k + 1)))
            + sum(
                encode_hardware_event_set(residual).encoded_bits
                for residual in dictionary["residual"]
            )
            + 16
        )
        pieces.append((bits, actual_k))
    candidates.append((sum(x[0] for x in pieces) + 16 * len(pieces), "A2",
                       sum(x[1] for x in pieces)))
    bits, variant, count = min(candidates, key=lambda item: (item[0], item[1]))
    return variant, count, int(bits)
