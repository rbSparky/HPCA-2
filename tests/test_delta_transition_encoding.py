import numpy as np

from mosaic_validation.delta_encoding import TransitionCode, decode_transition, encode_transition


def test_dense_and_sparse_transition_decoders_agree():
    rng = np.random.default_rng(7)
    previous = rng.random(32) < 0.5
    current = previous.copy()
    current[[1, 9, 25]] ^= True
    selected = encode_transition(previous, current)
    assert np.array_equal(decode_transition(previous, selected), current)
    xor = np.logical_xor(previous, current)
    dense = TransitionCode(True, np.packbits(xor, bitorder="little").tobytes(), 3)
    sparse = TransitionCode(False, bytes([3, 1, 9, 25]), 3)
    assert np.array_equal(decode_transition(previous, dense), current)
    assert np.array_equal(decode_transition(previous, sparse), current)

