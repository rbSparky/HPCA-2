import numpy as np

from mosaic_validation.panel_encoding import (
    PanelCostConfig,
    contiguous_panels,
    encode_panel_segment,
)


def lookup(m, k, n):
    return float(max(m, 1) * k + n), 50.0


def test_dense_panels_plus_residual_reconstruct_support():
    rng = np.random.default_rng(7)
    window = rng.random((4, 9, 10)) < 0.45
    tiles = [np.arange(5), np.arange(5, 9)]
    encoding = encode_panel_segment(
        window, tiles, contiguous_panels(10, 4), PanelCostConfig(), lookup
    )
    assert encoding.metrics["exact_decode_pass"]
    for tile_id, tile in enumerate(tiles):
        rebuilt = np.zeros_like(window[:, tile])
        for schedule in encoding.schedules[tile_id]:
            rebuilt |= schedule.reconstruct(window[:, tile])
        assert np.array_equal(rebuilt, window[:, tile])
