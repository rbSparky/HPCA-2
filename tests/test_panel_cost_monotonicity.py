import numpy as np

from mosaic_validation.panel_encoding import cost_aware_swaps


def test_cost_aware_swap_history_is_monotone():
    panels = [np.array([0, 1]), np.array([2, 3])]
    target = [{0, 2}, {1, 3}]

    def cost(candidate):
        return sum(len(set(panel) ^ wanted) for panel, wanted in zip(candidate, target))

    _, history, _ = cost_aware_swaps(panels, cost)
    assert all(b <= a for a, b in zip(history, history[1:]))
