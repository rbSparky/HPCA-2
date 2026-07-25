import numpy as np

from mosaic_validation.hardware_gap import encode_hardware_event_set


def test_hardware_gap_roundtrip_and_gap_bound():
    rng = np.random.default_rng(7)
    for universe in (31, 64, 511, 8192, 16384):
        for density in (0.0, 0.01, 0.2, 0.5, 0.9, 1.0):
            mask = rng.random(universe) < density
            code = encode_hardware_event_set(mask)
            assert np.array_equal(code.decode(), mask)
            for block in code.blocks:
                if len(block) > 1:
                    assert max(np.diff(block)) <= 255
                assert len(block) <= 32


def test_hardware_selector_is_minimum():
    mask = np.zeros(1024, dtype=bool)
    mask[[1, 2, 4, 900]] = True
    code = encode_hardware_event_set(mask)
    assert code.selected_format == "FIXED_IDS"
    assert code.encoded_bits <= 2 + 1024
