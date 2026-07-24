import numpy as np

from mosaic_validation.rebase import exhaustive_rebase, offline_dp_rebase


def test_dp_equals_exhaustive_segmentation():
    rng = np.random.default_rng(7)
    for layers in range(1, 9):
        costs = {}
        for start in range(layers):
            running = 0.0
            for end in range(start + 1, layers + 1):
                running += float(rng.uniform(1, 5))
                costs[(start, end)] = running + 0.2 * (end - start) ** 2
        dp = offline_dp_rebase(layers, costs, control_cost=0.7, max_window=4)
        brute = exhaustive_rebase(layers, costs, control_cost=0.7, max_window=4)
        assert np.isclose(dp.total_cost, brute.total_cost)

