import numpy as np
from mosaic_validation.global_gap import candidate_event_bits, encode_event_set


def test_selector_is_minimum_candidate():
    ids = np.array([1, 2, 9, 80, 81])
    code = encode_event_set(ids, 128)
    assert code.encoded_bits == min(candidate_event_bits(ids, 128).values())

