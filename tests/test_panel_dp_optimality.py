import itertools

from mosaic_validation.rebase import offline_dp_rebase


def test_panel_segment_dp_matches_exhaustive():
    layers = 5
    costs = {(s, e): (e - s) ** 2 + 1 for s in range(layers) for e in range(s + 1, layers + 1)}
    result = offline_dp_rebase(layers, costs, 0.0, layers)
    brute = float("inf")
    for mask in range(1 << (layers - 1)):
        cuts = [0] + [i + 1 for i in range(layers - 1) if mask & (1 << i)] + [layers]
        brute = min(brute, sum(costs[(a, b)] for a, b in zip(cuts, cuts[1:])))
    assert result.total_cost == brute
