import numpy as np
from mosaic_validation.global_gap import encode_event_set


def test_global_gap_roundtrip():
    rng = np.random.default_rng(7)
    for universe in (1, 7, 32, 257):
        mask = rng.random(universe) < 0.2
        assert np.array_equal(encode_event_set(mask, allow_complement=True).decode(), mask)

