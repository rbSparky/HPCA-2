import numpy as np

from mosaic_validation.window_cohorts import window_cost_cluster


def test_window_objective_never_increases():
    rng = np.random.default_rng(7)
    masks = rng.random((4, 96, 12)) < 0.5
    result = window_cost_cluster(masks, [np.arange(96)], 32)
    assert all(b <= a + 1e-9 for a, b in zip(result.objective_history, result.objective_history[1:]))
    assert sorted(np.concatenate(result.groups).tolist()) == list(range(96))
    assert max(map(len, result.groups)) <= 32

