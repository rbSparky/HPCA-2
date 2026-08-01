from __future__ import annotations

import random

import numpy as np

from xorflow.causal_schedule import (
    QueueConfig, _assert_stage_agreement, _record_services, _stage_event_list,
    _stage_recurrence,
)


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


def test_producer_recovery_chain_precedes_encoding() -> None:
    memory = _assert_stage_agreement([0, 0], [20, 0], workers=1, depth=2)
    decode = _assert_stage_agreement(memory.ends, [7, 0], workers=1, depth=2)
    encode = _assert_stage_agreement(decode.ends, [11, 11], workers=1, depth=2)
    assert encode.starts[0] >= decode.ends[0] >= memory.ends[0]
    assert encode.starts[1] >= decode.ends[1] >= memory.ends[1]


def test_producer_and_consumer_recovery_are_charged_separately() -> None:
    row = {
        "anchor_read_bytes": "128", "consumer_anchor_read_bytes": "128",
        "consumer_anchor_decode_cycles": "9", "payload_bits": "400",
        "header_bits": "16", "role": "target", "chosen_format": "DELTA",
        "input_support_bits": "16384", "padded_bytes": "64",
    }
    traffic = {
        "xorflow_feature_read_bytes": "256", "xorflow_metadata_bytes": "64",
        "xorflow_topology_bytes": "32", "xorflow_output_bytes": "128",
        "xorflow_writeback_bytes": "64",
    }
    services = _record_services(
        [row], np.asarray([1]), traffic, {"total_cycles": "10"},
        decoder_rate=64.0, variant="XORFLOW_ONLINE", cfg=QueueConfig(),
    )
    assert services["producer_anchor_parts"] == [128]
    assert services["consumer_anchor_parts"] == [128]
    assert services["producer_memory"][0] > 0
    assert services["producer_decode"][0] > 0
    assert services["memory"][0] > 0
    assert services["decode"][0] >= 9


def test_final_ablation_variants_share_coded_path_without_free_anchors() -> None:
    traffic = {
        "xorflow_feature_read_bytes": "256", "xorflow_metadata_bytes": "64",
        "xorflow_topology_bytes": "32", "xorflow_output_bytes": "128",
        "xorflow_writeback_bytes": "64",
    }
    independent = {
        "anchor_read_bytes": "128", "consumer_anchor_read_bytes": "128",
        "consumer_anchor_decode_cycles": "9", "payload_bits": "400",
        "header_bits": "16", "role": "target", "chosen_format": "A2",
        "input_support_bits": "16384", "padded_bytes": "64",
    }
    delta = dict(independent, chosen_format="DELTA")
    a2 = _record_services([independent], np.asarray([1]), traffic, {"total_cycles": "10"}, 64.0, "A2_ONLY", QueueConfig())
    forced = _record_services([delta], np.asarray([1]), traffic, {"total_cycles": "10"}, 64.0, "FORCED_XORFLOW", QueueConfig())
    assert a2["producer_anchor_parts"] == [0]
    assert a2["consumer_anchor_parts"] == [0]
    assert forced["producer_anchor_parts"] == [128]
    assert forced["consumer_anchor_parts"] == [128]
