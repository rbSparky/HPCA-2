import numpy as np

from mosaic_validation.panel_encoding import (
    PanelCostConfig,
    contiguous_panels,
    encode_panel_segment,
)


def test_scatter_initialization_and_adds_are_counted():
    window = np.ones((2, 4, 8), dtype=bool)
    encoding = encode_panel_segment(
        window,
        [np.arange(4)],
        contiguous_panels(8, 4),
        PanelCostConfig(output_features=8, accumulator_width_values=4),
        lambda m, k, n: (1.0, 50.0),
    )
    assert encoding.metrics["output_init_cycles"] == 2 * 4 * 2
    assert encoding.metrics["output_add_cycles"] >= 2 * 4 * 2
