"""Frozen, standalone XORFLOW support serializer.

Bit fields are written least-significant bit first into each byte.  Integer
fields are unsigned and little endian at bit granularity.  Every record begins
with a 16-bit header: a two-bit kind followed by a fourteen-bit payload-byte
count.  The payload is byte rounded and the complete record is then zero padded
to a 64-byte boundary.  Decoding depends only on the byte stream and the public
``rows``/``features`` dimensions; it never consults the source support.

The format deliberately favors a small, verifiable hardware contract over an
entropy-optimal codec.  Event-mode ties resolve DENSE, then IDS, then GAP8.
Record-kind ties are resolved by the online replay, with BEICSR preferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import hashlib
import math
from typing import Iterable

import numpy as np


ALIGNMENT_BYTES = 64
COHORT_ROWS = 32
MAX_PAYLOAD_BYTES = (1 << 14) - 1


class Codec(IntEnum):
    BEICSR = 0
    A0 = 1
    A2 = 2
    DELTA = 3


class EventMode(IntEnum):
    DENSE = 0
    IDS = 1
    GAP8 = 2


class FormatError(ValueError):
    """Raised for a malformed, truncated, or dimension-incompatible stream."""


class BitWriter:
    def __init__(self) -> None:
        self._data = bytearray()
        self._bit_count = 0

    @property
    def bit_count(self) -> int:
        return self._bit_count

    def write(self, value: int, width: int) -> None:
        if width < 0 or value < 0 or value >= (1 << width if width else 1):
            raise ValueError(f"value {value} does not fit unsigned {width}-bit field")
        self.write_packed(value.to_bytes(math.ceil(width / 8), "little"), width)

    def write_bits(self, values: Iterable[bool | int]) -> None:
        array = np.asarray(values, dtype=np.uint8).reshape(-1)
        packed = np.packbits(array, bitorder="little")
        self.write_packed(packed.tobytes(), len(array))

    def write_values(self, values: np.ndarray, width: int) -> None:
        """Write fixed-width unsigned values without a Python loop per bit."""
        array = np.asarray(values, dtype=np.uint64).reshape(-1)
        if array.size == 0:
            return
        if width <= 0 or width > 64 or np.any(array >= (1 << width if width < 64 else 1 << 64)):
            raise ValueError("fixed-width value does not fit field")
        # Shape (values, width), flattened value-major, exactly matches a
        # sequence of LSB-first scalar writes.
        shifts = np.arange(width, dtype=np.uint64)
        bits = ((array[:, None] >> shifts) & 1).astype(np.uint8).reshape(-1)
        self.write_packed(np.packbits(bits, bitorder="little").tobytes(), len(bits))

    def write_packed(self, data: bytes, valid_bits: int) -> None:
        if valid_bits < 0 or len(data) * 8 < valid_bits:
            raise ValueError("packed source shorter than valid_bits")
        if valid_bits == 0:
            return
        size = math.ceil(valid_bits / 8)
        raw = bytearray(data[:size])
        if valid_bits % 8:
            raw[-1] &= (1 << (valid_bits % 8)) - 1
        old_bits = self._bit_count
        offset = old_bits % 8
        if offset == 0:
            self._data.extend(raw)
        else:
            # Merge packed bytes at the current bit offset.  This loops once
            # per byte (not once per bit) while preserving the frozen LSB-first
            # stream exactly.
            for byte in raw:
                self._data[-1] |= (byte << offset) & 0xFF
                self._data.append(byte >> (8 - offset))
        self._bit_count = old_bits + valid_bits
        required = math.ceil(self._bit_count / 8)
        if len(self._data) > required:
            del self._data[required:]

    def to_bytes(self) -> bytes:
        return bytes(self._data)


class BitReader:
    def __init__(self, data: bytes, valid_bits: int | None = None) -> None:
        self.data = data
        self.valid_bits = len(data) * 8 if valid_bits is None else valid_bits
        self.position = 0

    def read(self, width: int) -> int:
        if width < 0 or self.position + width > self.valid_bits:
            raise FormatError("truncated bit field")
        value = 0
        for bit in range(width):
            value |= ((self.data[(self.position + bit) // 8] >> ((self.position + bit) % 8)) & 1) << bit
        self.position += width
        return value

    def read_bits(self, width: int) -> np.ndarray:
        if width < 0 or self.position + width > self.valid_bits:
            raise FormatError("truncated bit field")
        if width == 0:
            return np.empty(0, dtype=bool)
        positions = np.arange(self.position, self.position + width, dtype=np.int64)
        raw = np.frombuffer(self.data, dtype=np.uint8)
        result = ((raw[positions // 8] >> (positions % 8)) & 1).astype(bool)
        self.position += width
        return result

    def read_values(self, width: int, count: int) -> np.ndarray:
        """Vectorized equivalent of ``count`` consecutive scalar reads."""
        if width < 0 or count < 0 or self.position + width * count > self.valid_bits:
            raise FormatError("truncated fixed-width fields")
        if count == 0:
            return np.empty(0, dtype=np.uint64)
        positions = self.position + np.arange(count, dtype=np.int64)[:, None] * width + np.arange(width, dtype=np.int64)
        raw = np.frombuffer(self.data, dtype=np.uint8)
        bits = ((raw[positions // 8] >> (positions % 8)) & 1).astype(np.uint64)
        result = (bits * (np.uint64(1) << np.arange(width, dtype=np.uint64))).sum(axis=1, dtype=np.uint64)
        self.position += width * count
        return result


@dataclass(frozen=True)
class EventEncoding:
    mode: EventMode
    universe: int
    event_count: int
    bits: int
    data: bytes
    block_count: int = 0


@dataclass(frozen=True)
class SerializedRecord:
    codec: Codec
    rows: int
    features: int
    payload_bits: int
    payload_bytes: int
    unpadded_bytes: int
    padded_bytes: int
    data: bytes
    selected_modes: tuple[str, ...]
    event_count: int

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.data).hexdigest()


@dataclass(frozen=True)
class DecodedRecord:
    codec: Codec
    support: np.ndarray
    consumed_bytes: int
    payload_bits_consumed: int


def _bits_for(values: int) -> int:
    return max(1, math.ceil(math.log2(max(values, 2))))


def _gap_blocks(events: np.ndarray) -> list[np.ndarray]:
    if events.size == 0:
        return []
    values = np.asarray(events, dtype=np.int64)
    # Gaps above 255 are mandatory restart points.  Between such points every
    # gap is legal, so deterministic 32-event chunks exactly reproduce the
    # original greedy grammar without visiting each event in Python.
    restarts = np.flatnonzero(np.diff(values) > 255) + 1
    boundaries = np.concatenate(([0], restarts, [len(values)]))
    blocks: list[np.ndarray] = []
    for left, right in zip(boundaries[:-1], boundaries[1:]):
        blocks.extend(values[start:min(start + 32, right)] for start in range(int(left), int(right), 32))
    return blocks


def _event_candidate_bits(events: np.ndarray, universe: int, blocks: list[np.ndarray] | None = None) -> dict[EventMode, int]:
    count_width = _bits_for(universe + 1)
    id_width = _bits_for(universe)
    header = 2 + count_width
    blocks = _gap_blocks(events) if blocks is None else blocks
    gap = header + 9
    for block in blocks:
        gap += 5 + id_width + max(0, len(block) - 1) * 8
    return {
        EventMode.DENSE: header + universe,
        EventMode.IDS: header + len(events) * id_width,
        EventMode.GAP8: gap,
    }


def encode_event(mask: np.ndarray) -> EventEncoding:
    flat = np.asarray(mask, dtype=bool).reshape(-1)
    universe = int(flat.size)
    if universe <= 0:
        raise ValueError("event universe must be non-empty")
    events = np.flatnonzero(flat).astype(np.int64)
    blocks = _gap_blocks(events)
    candidates = _event_candidate_bits(events, universe, blocks)
    mode = min((EventMode.DENSE, EventMode.IDS, EventMode.GAP8), key=lambda item: (candidates[item], int(item)))
    writer = BitWriter()
    writer.write(int(mode), 2)
    writer.write(len(events), _bits_for(universe + 1))
    if mode == EventMode.DENSE:
        writer.write_bits(flat)
    elif mode == EventMode.IDS:
        width = _bits_for(universe)
        writer.write_values(events, width)
    else:
        if len(blocks) >= (1 << 9):
            raise ValueError("Gap8 block count exceeds 9-bit field")
        writer.write(len(blocks), 9)
        width = _bits_for(universe)
        for block in blocks:
            writer.write(len(block) - 1, 5)
            writer.write(int(block[0]), width)
            gaps = np.diff(block)
            if np.any(gaps < 1) or np.any(gaps > 255):
                raise AssertionError("Gap8 block construction emitted an illegal gap")
            writer.write_packed(gaps.astype(np.uint8).tobytes(), len(gaps) * 8)
    return EventEncoding(mode, universe, len(events), writer.bit_count, writer.to_bytes(), len(blocks))


def decode_event(reader: BitReader, universe: int) -> np.ndarray:
    mode_value = reader.read(2)
    if mode_value not in {int(item) for item in EventMode}:
        raise FormatError(f"reserved event mode {mode_value}")
    mode = EventMode(mode_value)
    count = reader.read(_bits_for(universe + 1))
    if count > universe:
        raise FormatError("event count exceeds universe")
    result = np.zeros(universe, dtype=bool)
    if mode == EventMode.DENSE:
        result = reader.read_bits(universe)
        if int(result.sum()) != count:
            raise FormatError("dense event count does not match bitmap")
    elif mode == EventMode.IDS:
        width = _bits_for(universe)
        events = reader.read_values(width, count).astype(np.int64)
        if np.any(events >= universe) or (len(events) > 1 and np.any(np.diff(events) <= 0)):
            raise FormatError("event IDs must be sorted, unique, and in range")
        result[events] = True
    else:
        blocks = reader.read(9)
        seen = 0
        previous_global = -1
        width = _bits_for(universe)
        for _ in range(blocks):
            length = reader.read(5) + 1
            first = reader.read(width)
            if first >= universe or first <= previous_global:
                raise FormatError("invalid Gap8 block restart ID")
            result[first] = True
            previous = first
            seen += 1
            gaps = reader.read_values(8, length - 1).astype(np.int64)
            if np.any(gaps == 0):
                raise FormatError("Gap8 gaps must be positive")
            positions = first + np.cumsum(gaps)
            if np.any(positions >= universe):
                raise FormatError("Gap8 event exceeds universe")
            result[positions] = True
            if len(positions): previous = int(positions[-1])
            seen += len(positions)
            previous_global = previous
        if seen != count:
            raise FormatError("Gap8 block lengths do not match event count")
    return result


def _payload_beicsr(support: np.ndarray) -> tuple[bytes, int, tuple[str, ...], int]:
    writer = BitWriter()
    writer.write_bits(support.reshape(-1))
    return writer.to_bytes(), writer.bit_count, ("BITMAP",), int(support.sum())


def _payload_a0(support: np.ndarray) -> tuple[bytes, int, tuple[str, ...], int]:
    writer = BitWriter()
    modes: list[str] = []
    events = 0
    for row in support:
        code = encode_event(row)
        writer.write_packed(code.data, code.bits)
        modes.append(code.mode.name)
        events += code.event_count
    return writer.to_bytes(), writer.bit_count, tuple(modes), events


def _payload_a2(support: np.ndarray) -> tuple[bytes, int, tuple[str, ...], int]:
    writer = BitWriter()
    modes: list[str] = []
    events = 0
    for start in range(0, support.shape[0], COHORT_ROWS):
        cohort = support[start:start + COHORT_ROWS]
        prototype = cohort.sum(axis=0, dtype=np.int16) > (len(cohort) / 2)
        writer.write_bits(prototype)
        modes.append("PROTOTYPE")
        for row in cohort:
            code = encode_event(np.logical_xor(row, prototype))
            writer.write_packed(code.data, code.bits)
            modes.append(code.mode.name)
            events += code.event_count
    return writer.to_bytes(), writer.bit_count, tuple(modes), events


def _payload_delta(support: np.ndarray) -> tuple[bytes, int, tuple[str, ...], int]:
    code = encode_event(support.reshape(-1))
    return code.data, code.bits, (code.mode.name,), code.event_count


def serialize_record(support: np.ndarray, codec: Codec | str) -> SerializedRecord:
    value = np.asarray(support, dtype=bool)
    if value.ndim != 2 or min(value.shape) <= 0:
        raise ValueError("support must have shape (rows, features) with nonzero dimensions")
    kind = Codec[codec] if isinstance(codec, str) else Codec(codec)
    payload_fn = {
        Codec.BEICSR: _payload_beicsr,
        Codec.A0: _payload_a0,
        Codec.A2: _payload_a2,
        Codec.DELTA: _payload_delta,
    }[kind]
    payload, payload_bits, modes, event_count = payload_fn(value)
    payload_bytes = len(payload)
    if payload_bytes > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload {payload_bytes} exceeds 14-bit record limit")
    header = int(kind) | (payload_bytes << 2)
    unpadded = 2 + payload_bytes
    padded = math.ceil(unpadded / ALIGNMENT_BYTES) * ALIGNMENT_BYTES
    data = header.to_bytes(2, "little") + payload + bytes(padded - unpadded)
    return SerializedRecord(kind, value.shape[0], value.shape[1], payload_bits, payload_bytes, unpadded, padded, data, modes, event_count)


def decode_record(data: bytes, *, rows: int, features: int, require_zero_padding: bool = True) -> DecodedRecord:
    if len(data) < 2:
        raise FormatError("truncated record header")
    header = int.from_bytes(data[:2], "little")
    kind = Codec(header & 0b11)
    payload_bytes = header >> 2
    unpadded = 2 + payload_bytes
    padded = math.ceil(unpadded / ALIGNMENT_BYTES) * ALIGNMENT_BYTES
    if len(data) < padded:
        raise FormatError("truncated record payload or padding")
    if require_zero_padding and any(data[unpadded:padded]):
        raise FormatError("record padding must be zero")
    payload = data[2:unpadded]
    reader = BitReader(payload)
    if kind == Codec.BEICSR:
        support = reader.read_bits(rows * features).reshape(rows, features)
    elif kind == Codec.A0:
        support = np.stack([decode_event(reader, features) for _ in range(rows)])
    elif kind == Codec.A2:
        pieces: list[np.ndarray] = []
        for start in range(0, rows, COHORT_ROWS):
            count = min(COHORT_ROWS, rows - start)
            prototype = reader.read_bits(features)
            pieces.extend(np.logical_xor(prototype, decode_event(reader, features)) for _ in range(count))
        support = np.stack(pieces)
    else:
        support = decode_event(reader, rows * features).reshape(rows, features)
    # All remaining payload bits are byte-rounding zeros.  Nonzero tail bits
    # indicate an overlong or ambiguous stream.
    payload_bits_consumed = reader.position
    while reader.position < reader.valid_bits:
        if reader.read(1):
            raise FormatError("nonzero payload tail bits")
    return DecodedRecord(kind, support, padded, payload_bits_consumed)


def record_index_entry(layer: int, tile: int, feature_slice: int, offset: int) -> bytes:
    """Return the frozen 16-byte stream-index entry.

    Layout: layer u16, slice u16, tile u32, byte offset u64, all little endian.
    """
    for value, limit, name in ((layer, 1 << 16, "layer"), (feature_slice, 1 << 16, "slice"), (tile, 1 << 32, "tile"), (offset, 1 << 64, "offset")):
        if value < 0 or value >= limit:
            raise ValueError(f"{name} outside index-entry range")
    return layer.to_bytes(2, "little") + feature_slice.to_bytes(2, "little") + tile.to_bytes(4, "little") + offset.to_bytes(8, "little")
