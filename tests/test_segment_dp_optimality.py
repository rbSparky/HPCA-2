from mosaic_validation.rebase import exhaustive_rebase, offline_dp_rebase
import math


def test_segment_dp_against_exhaustive():
    costs = {(s, e): (e - s) ** 2 + 1 for s in range(6) for e in range(s + 1, 7)}
    assert math.isclose(
        offline_dp_rebase(6, costs, .2, 4).total_cost,
        exhaustive_rebase(6, costs, .2, 4).total_cost,
    )
