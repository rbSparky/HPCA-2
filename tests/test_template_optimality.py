import itertools

import numpy as np

from mosaic_validation.cohorts import optimal_template


def _cost(rows, template):
    return 4 * len(rows) * template.sum() + 2 * template.sum() + 6 * np.logical_and(rows, ~template).sum()


def test_closed_form_template_is_globally_optimal():
    rng = np.random.default_rng(7)
    for width in range(1, 9):
        rows = rng.random((5, width)) > 0.45
        selected = optimal_template(rows)
        brute = min(
            _cost(rows, np.asarray(bits, dtype=bool))
            for bits in itertools.product((False, True), repeat=width)
        )
        assert _cost(rows, selected) == brute

