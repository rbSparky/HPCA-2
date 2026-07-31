from __future__ import annotations

import numpy as np

from xorflow.system_schedule import Pool, _partition


def test_integer_traffic_partition_is_exact_and_deterministic() -> None:
    weights = np.asarray([1, 3, 0, 7], dtype=np.int64)
    first = _partition(10_003, weights)
    second = _partition(10_003, weights)
    assert np.array_equal(first, second)
    assert int(first.sum()) == 10_003
    assert first[2] == 0


def test_finite_server_pool_serializes_affined_requests() -> None:
    pool = Pool(2, 4)
    _, a = pool.issue(0, 10, affinity=0)
    start_b, b = pool.issue(2, 5, affinity=0)
    start_c, c = pool.issue(2, 5, affinity=1)
    assert (a, start_b, b) == (10, 10, 15)
    assert (start_c, c) == (2, 7)
    assert pool.stall_cycles == 8
