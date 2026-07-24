import numpy as np

from mosaic_validation.analytical_cost import representation_metrics
from mosaic_validation.cohorts import rcm_cost_cluster


def test_cohorts_are_balanced_partition_and_known_metrics():
    mask = np.ones((70, 8), dtype=bool)
    tiles = [np.arange(70)]
    result = rcm_cost_cluster(mask, tiles, 32)
    nodes = np.concatenate(result.groups)
    assert sorted(nodes.tolist()) == list(range(70))
    assert len(set(nodes.tolist())) == 70
    assert max(map(len, result.groups)) <= 24
    metrics = representation_metrics(mask, result)
    assert metrics["regular_capture"] == 1
    assert metrics["padding_fraction"] == 0


def test_zero_mask_has_no_division_errors():
    mask = np.zeros((8, 4), dtype=bool)
    result = rcm_cost_cluster(mask, [np.arange(8)], 32)
    metrics = representation_metrics(mask, result)
    assert metrics["regular_capture"] == 0
    assert metrics["padding_fraction"] == 0

