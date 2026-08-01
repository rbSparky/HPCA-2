import numpy as np

from mosaic_validation.cohorts import CohortSet
from mosaic_validation.temporal import match_cohorts


def test_permuted_labels_match_perfectly():
    groups = [np.array([0, 1]), np.array([2, 3])]
    templates = [np.array([1, 0], dtype=bool), np.array([0, 1], dtype=bool)]
    previous = CohortSet(groups, templates)
    current = CohortSet(groups[::-1], templates[::-1])
    stability, jaccard, _ = match_cohorts(previous, current, 4)
    assert stability == 1
    assert jaccard == 1

