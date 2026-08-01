"""Exact plan tests for the full common-format matrix."""
from __future__ import annotations

import numpy as np

from mosaic_validation.hpca_format_matrix import _free_support_plan, _offline_plan


def test_oracle_and_free_support_plans_have_legal_tile_shapes() -> None:
    pair = np.random.default_rng(7).random((2, 5, 9)) > 0.5
    tiles = [np.array([0, 1, 2]), np.array([3, 4])]
    offline = _offline_plan(pair, tiles, 4)
    free = _free_support_plan(pair, 4)
    assert offline["formats"].shape == (5, 3)
    assert free["formats"].shape == (5, 3)
    assert set(np.unique(offline["formats"]).tolist()).issubset({"BEICSR", "XORFLOW"})
    assert set(np.unique(free["formats"]).tolist()) == {"XORFLOW"}
    assert free["support_bits"] == 0 and free["decode_cycles"] == 0
