import numpy as np
from mosaic_validation.anchor_encoding import encode_anchor


def test_anchor_roundtrip():
    masks = np.random.default_rng(7).random((4, 12, 8)) < 0.55
    encoded = encode_anchor(masks)
    assert encoded.metrics["exact_decode_pass"]
    assert np.array_equal(np.stack([encoded.decode_layer(i) for i in range(4)]), masks)

