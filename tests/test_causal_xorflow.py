import numpy as np

from mosaic_validation.causal_xorflow import (
    beicsr_pair_support_bits,
    causal_pair_statistics,
    encode_causal_pair,
    encode_offline_majority_pair,
    select_causal_pair,
)


def test_causal_pair_roundtrip_and_independent_decode():
    x = np.random.default_rng(7).random((2, 9, 17)) > .55
    encoded = encode_causal_pair(x)
    assert np.array_equal(encoded.decode_anchor_layer(), x[0])
    assert np.array_equal(encoded.spatial_dictionary.decode(), x[0])
    assert np.array_equal(encoded.decode_exception_layer(), x[1])
    assert encoded.independently_decodable


def test_causal_anchor_is_first_completed_layer_not_future_majority():
    x = np.zeros((2, 2, 3), dtype=bool)
    x[0, 0, 0] = True
    x[1, 1, 2] = True
    encoded = encode_causal_pair(x)
    assert np.array_equal(encoded.anchor, x[0])


def test_causal_selector_never_worse_than_included_fallback():
    x = np.random.default_rng(17).random((2, 32, 64)) > .5
    selected = select_causal_pair(x)
    assert selected.support_bits <= beicsr_pair_support_bits(x)


def test_causal_statistics_are_exact_and_deterministic():
    x = np.random.default_rng(27).random((2, 8, 16)) > .7
    first = causal_pair_statistics(x)
    second = causal_pair_statistics(x)
    assert first == second
    assert first["exact_decode_pass"]


def test_independent_anchor_and_offline_majority_oracle_round_trip_exactly():
    layers = np.array([
        [[1, 0, 1, 0], [0, 1, 1, 0]],
        [[1, 1, 0, 0], [0, 1, 1, 1]],
    ], dtype=bool)
    a0 = encode_causal_pair(layers, dictionary_mode="a0")
    oracle = encode_offline_majority_pair(layers, dictionary_mode="a2")
    assert a0.anchor_variant == "A0_INDEPENDENT_ROWS"
    assert np.array_equal(a0.decode_anchor_layer(), layers[0])
    assert np.array_equal(a0.decode_exception_layer(), layers[1])
    assert np.array_equal(oracle.decode_layer(0), layers[0])
    assert np.array_equal(oracle.decode_layer(1), layers[1])
