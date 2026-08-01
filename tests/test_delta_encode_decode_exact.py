import numpy as np

from mosaic_validation.delta_encoding import reconstruct_support


def test_delta_roundtrip_all_small_shapes():
    rng = np.random.default_rng(7)
    for layers in (1, 2, 4, 8):
        for nodes in (1, 7, 32, 64, 256):
            masks = rng.random((layers, nodes, 8)) < 0.45
            groups = [np.arange(start, min(start + 16, nodes)) for start in range(0, nodes, 16)]
            decoded = reconstruct_support(masks, groups)
            assert np.array_equal(decoded, masks)
