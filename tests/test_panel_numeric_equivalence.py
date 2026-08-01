import numpy as np

from mosaic_validation.panel_encoding import (
    PanelCostConfig,
    contiguous_panels,
    encode_panel_segment,
    numeric_decomposition,
)


def test_panel_numeric_equivalence():
    rng = np.random.default_rng(7)
    support = rng.random((3, 7, 8)) < 0.5
    values = rng.normal(size=support.shape).astype(np.float32) * support
    weights = rng.normal(size=(3, 8, 6)).astype(np.float32)
    tiles = [np.arange(4), np.arange(4, 7)]
    encoding = encode_panel_segment(
        support,
        tiles,
        contiguous_panels(8, 4),
        PanelCostConfig(output_features=6),
        lambda m, k, n: (float(m * k + n), 25.0),
    )
    reference, actual = numeric_decomposition(values, weights, encoding, tiles)
    np.testing.assert_allclose(actual, reference, rtol=1e-5, atol=1e-6)
