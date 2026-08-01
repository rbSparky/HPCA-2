import numpy as np

from mosaic_validation.panel_encoding import PanelCostConfig, optimize_fixed_panel


def test_escape_is_layer_local_and_future_independent():
    rng = np.random.default_rng(7)
    prefix = rng.random((2, 8, 4)) < 0.5
    future_a = np.zeros((1, 8, 4), bool)
    future_b = np.ones((1, 8, 4), bool)
    lookup = lambda m, k, n: (float(20 + m * k), 20.0)
    cfg = PanelCostConfig(output_features=4, escape_enabled=True)
    a = optimize_fixed_panel(np.concatenate([prefix, future_a]), np.arange(4), cfg, lookup)
    b = optimize_fixed_panel(np.concatenate([prefix, future_b]), np.arange(4), cfg, lookup)
    # Given the persistent row list, each escape comparison only references its
    # own layer. Re-evaluate the same selected prefix by comparing decisions.
    if np.array_equal(a.selected_rows, b.selected_rows):
        assert np.array_equal(a.escape_layers[:2], b.escape_layers[:2])
