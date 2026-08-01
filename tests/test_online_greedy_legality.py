from mosaic_validation.anchor_runtime import online_greedy


def test_online_greedy_is_contiguous_and_forward_only():
    costs = {(s, e): (e - s) * 10 for s in range(5) for e in range(s + 1, 6)}
    segments = online_greedy(costs, 5, 4, .05)
    assert segments[0][0] == 0 and segments[-1][1] == 5
    assert all(a[1] == b[0] for a, b in zip(segments, segments[1:]))

