from __future__ import annotations

import numpy as np
import pytest

from xorflow.serializer import (
    BitWriter,
    Codec,
    FormatError,
    decode_record,
    encode_event,
    serialize_record,
)


def test_optimized_bit_writer_matches_independent_bit_reference() -> None:
    """Guard the frozen grammar while optimizing the serializer hot path."""
    rng = np.random.default_rng(7007)
    for _ in range(100):
        writer = BitWriter()
        reference: list[int] = []
        for _ in range(50):
            width = int(rng.integers(0, 67))
            value = int.from_bytes(rng.bytes((width + 7) // 8), "little")
            if width:
                value &= (1 << width) - 1
            writer.write(value, width)
            reference.extend((value >> bit) & 1 for bit in range(width))
        expected = bytearray((len(reference) + 7) // 8)
        for position, bit in enumerate(reference):
            expected[position // 8] |= bit << (position % 8)
        assert writer.bit_count == len(reference)
        assert writer.to_bytes() == bytes(expected)


@pytest.mark.parametrize("rows", [1, 31, 32, 33, 128])
@pytest.mark.parametrize("features", [64, 96, 128, 256])
@pytest.mark.parametrize("codec", list(Codec))
def test_serializer_roundtrip_random(rows: int, features: int, codec: Codec) -> None:
    rng = np.random.default_rng(rows * 1000 + features * 10 + int(codec))
    support = rng.random((rows, features)) < 0.37
    record = serialize_record(support, codec)
    decoded = decode_record(record.data, rows=rows, features=features)
    assert np.array_equal(decoded.support, support)
    assert decoded.consumed_bytes == len(record.data) == record.padded_bytes
    assert record.unpadded_bytes == 2 + record.payload_bytes
    assert record.padded_bytes % 64 == 0


@pytest.mark.parametrize("events", [0, 1, 31, 32, 33, 256])
def test_event_boundary_counts(events: int) -> None:
    mask = np.zeros(256, dtype=bool)
    mask[:events] = True
    code = encode_event(mask)
    assert code.event_count == events


def test_gap_boundaries_roundtrip() -> None:
    mask = np.zeros(1024, dtype=bool)
    positions = np.asarray([0, 1, 255, 510, 766, 1023])  # gaps 1, 254, 255, 256, 257
    mask[positions] = True
    record = serialize_record(mask.reshape(8, 128), Codec.DELTA)
    decoded = decode_record(record.data, rows=8, features=128)
    assert np.array_equal(decoded.support, mask.reshape(8, 128))


def test_cohort_majority_tie_is_zero() -> None:
    support = np.zeros((32, 64), dtype=bool)
    support[:16, 7] = True
    record = serialize_record(support, Codec.A2)
    decoded = decode_record(record.data, rows=32, features=64)
    assert np.array_equal(decoded.support, support)


def test_malformed_streams_are_rejected() -> None:
    support = np.eye(32, 64, dtype=bool)
    record = serialize_record(support, Codec.A0)
    with pytest.raises(FormatError):
        decode_record(record.data[:-1], rows=32, features=64)
    corrupted = bytearray(record.data)
    corrupted[-1] = 1
    with pytest.raises(FormatError):
        decode_record(bytes(corrupted), rows=32, features=64)


def test_dense_worst_cases() -> None:
    for fill in (False, True):
        support = np.full((128, 256), fill, dtype=bool)
        for codec in Codec:
            record = serialize_record(support, codec)
            assert np.array_equal(decode_record(record.data, rows=128, features=256).support, support)
