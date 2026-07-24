import numpy as np

from mosaic_validation.delta_encoding import encode_window


def test_selected_cost_is_bounded_by_each_fallback_plus_selector():
    rng = np.random.default_rng(7)
    masks = rng.random((4, 64, 16)) < 0.6
    result = encode_window(
        masks, [np.arange(32), np.arange(32, 64)],
        rebase_fraction=0.0, selector_fraction=0.001,
    )
    selected = result.metrics["proxy_cycles_rho1_25"]
    overhead = 0.001 * masks.size
    dense = masks.size
    independent = 2 * masks.sum()
    assert selected <= dense + overhead + 1e-9
    assert selected <= independent + overhead + 1e-9

