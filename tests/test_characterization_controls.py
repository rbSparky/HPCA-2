from __future__ import annotations

import numpy as np

from xorflow.characterization import _exact_count_null


def test_exact_count_null_preserves_every_row_density() -> None:
    rng = np.random.default_rng(7)
    source = rng.random((128, 96)) < rng.random((128, 1))
    control = _exact_count_null(source, np.random.default_rng(7007))
    assert np.array_equal(control.sum(axis=1), source.sum(axis=1))
    assert control.shape == source.shape


def test_exact_count_null_is_deterministic() -> None:
    source = np.eye(32, 64, dtype=bool)
    a = _exact_count_null(source, np.random.default_rng(7007))
    b = _exact_count_null(source, np.random.default_rng(7007))
    assert np.array_equal(a, b)
