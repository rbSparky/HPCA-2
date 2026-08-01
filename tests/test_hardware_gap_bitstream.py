import numpy as np
import pytest

from mosaic_validation.hardware_gap import (
    encode_hardware_event_set,
    pack_hardware_event_code,
    unpack_hardware_event_code,
)


@pytest.mark.parametrize("density", [0.0, 0.02, 0.25, 0.7, 1.0])
def test_packed_hardware_events_roundtrip_exactly(density):
    mask = np.random.default_rng(7).random(128) < density
    code = encode_hardware_event_set(mask)
    payload, bits = pack_hardware_event_code(code)
    decoded = unpack_hardware_event_code(payload, bits, 128)
    assert bits == code.encoded_bits
    assert np.array_equal(decoded.decode(), mask)


def test_hardware_gap_rejects_truncated_payload():
    code = encode_hardware_event_set(np.array([1, 5, 9]), universe=32)
    payload, bits = pack_hardware_event_code(code)
    with pytest.raises(ValueError):
        unpack_hardware_event_code(payload, bits - 1, 32)
