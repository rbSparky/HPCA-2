import numpy as np


def _prefix_tree(gaps):
    stage = list(map(int, gaps))
    for distance in (1, 2, 4):
        old = stage.copy()
        for index in range(distance, 8):
            stage[index] = old[index] + old[index - distance]
    return stage


def test_rtl_parallel_prefix_matches_serial_reference():
    rng = np.random.default_rng(7)
    for _ in range(10000):
        gaps = rng.integers(0, 256, size=8)
        base = int(rng.integers(0, 1 << 14))
        expected = (base + np.cumsum(gaps)) & ((1 << 14) - 1)
        observed = (base + np.asarray(_prefix_tree(gaps))) & ((1 << 14) - 1)
        assert np.array_equal(observed, expected)
