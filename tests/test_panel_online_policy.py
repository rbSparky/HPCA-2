from mosaic_validation.anchor_runtime import online_greedy


def test_panel_online_policy_uses_only_observed_prefixes():
    layers = 6
    costs = {(s, e): float(e - s) for s in range(layers) for e in range(s + 1, min(layers, s + 4) + 1)}
    segments = online_greedy(costs, layers, 4, 0.05)
    assert segments[0][0] == 0
    assert segments[-1][1] == layers
    assert all(e - s <= 4 for s, e in segments)
