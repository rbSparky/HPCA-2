from __future__ import annotations

import random

from xorflow.causal_schedule import QueueConfig, _assert_stage_agreement, _stage_event_list, _stage_recurrence


def test_finite_stage_recurrence_agrees_on_random_workloads() -> None:
    rng = random.Random(7)
    for _ in range(20):
        releases = sorted(rng.randrange(30) for _ in range(24))
        services = [rng.randrange(1, 20) for _ in releases]
        result = _assert_stage_agreement(releases, services, workers=3, depth=4)
        assert result.max_queue <= 4
        assert result.ends == _stage_recurrence(releases, services, 3, 4)


def test_queue_saturation_is_explicit_and_not_premature() -> None:
    result = _stage_event_list([0, 0, 0, 0, 0], [10, 10, 10, 10, 10], workers=1, queue_depth=2)
    assert result.max_queue <= 2
    assert result.queue_wait > 0
    assert all(a >= b for a, b in zip(result.ends[1:], result.ends[:-1]))


def test_queue_config_has_separate_resource_limits() -> None:
    cfg = QueueConfig(input_depth=2, decode_depth=3, aggregation_depth=4, combination_depth=5, writeback_depth=6)
    assert cfg.name == "iq2_dq3_aq4_cq5_wq6_m8"
    assert cfg.support_decode_width_bits == 2048
