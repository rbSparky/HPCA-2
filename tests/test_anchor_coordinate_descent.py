import numpy as np
from mosaic_validation.anchor_encoding import encode_anchor


def test_anchor_objective_monotone_and_tiny_exhaustive():
    masks = np.random.default_rng(7).random((3, 2, 3)) < 0.5
    encoded = encode_anchor(masks)
    assert all(b <= a + 1e-12 for a, b in zip(encoded.objective_history, encoded.objective_history[1:]))

