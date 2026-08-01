import numpy as np

from mosaic_validation.analytical_cost import representation_metrics
from mosaic_validation.cohorts import CohortSet


def test_exact_cost_accounting():
    mask = np.array([[1, 1, 0], [1, 0, 1]], dtype=bool)
    cohort = CohortSet([np.array([0, 1])], [np.array([1, 0, 0], dtype=bool)])
    metrics = representation_metrics(mask, cohort)
    assert metrics["total_nnz"] == 4
    assert metrics["core_true_nnz"] == 2
    assert metrics["core_slots"] == 2
    assert metrics["residual_nnz"] == 2
    assert metrics["holes"] == 0

