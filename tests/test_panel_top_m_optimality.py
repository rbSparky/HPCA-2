import itertools
import numpy as np

from mosaic_validation.panel_encoding import PanelCostConfig, optimize_fixed_panel


def test_top_m_is_best_subset_and_selected_prefix_is_global_minimum():
    window = np.array(
        [
            [[1, 1], [1, 0], [0, 0], [1, 1]],
            [[1, 1], [0, 0], [0, 1], [1, 1]],
        ],
        dtype=bool,
    )
    features = np.arange(2)
    lookup = lambda m, k, n: (float(4 * m + k), 20.0)
    config = PanelCostConfig(output_features=4)
    schedule = optimize_fixed_panel(window, features, config, lookup)
    assert schedule.total_cycles == schedule.objective_by_prefix.min()
    counts = window.sum(axis=(0, 2))
    for m in range(window.shape[1] + 1):
        top = set(np.lexsort((np.arange(4), -counts))[:m])
        best_saved = max(
            sum(counts[list(subset)])
            for subset in itertools.combinations(range(4), m)
        )
        assert sum(counts[list(top)]) == best_saved
