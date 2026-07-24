import numpy as np
from mosaic_validation.anchor_encoding import encode_anchor


def test_each_layer_decodes_without_predecessor():
    masks = np.random.default_rng(7).random((8, 7, 5)) < 0.4
    encoded = encode_anchor(masks)
    for layer in (7, 0, 4, 2):
        assert np.array_equal(encoded.decode_layer(layer), masks[layer])

