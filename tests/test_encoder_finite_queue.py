from __future__ import annotations

from xorflow.encoder_sim import _simulate_layer


def _records(count: int):
    return [
        {
            "input_support_bits": "16384",
            "padded_bytes": str(64 * (1 + (index % 7))),
            "role": "anchor" if index % 2 == 0 else "target",
        }
        for index in range(count)
    ]


def test_encoder_queues_are_finite_and_accounted() -> None:
    result = _simulate_layer(_records(100), input_q_depth=2, working_buffers=1, output_fifo_lines=4, candidate_engines="shared")
    assert result["max_input_q"] <= 2
    assert result["max_output_q"] <= 4
    assert result["total_cycles"] > 0
    assert result["input_bits"] == 100 * 16384
    assert result["output_bits"] == sum(int(row["padded_bytes"]) * 8 for row in _records(100))


def test_parallel_candidate_engine_is_not_slower() -> None:
    shared = _simulate_layer(_records(40), input_q_depth=4, working_buffers=2, output_fifo_lines=8, candidate_engines="shared")
    parallel = _simulate_layer(_records(40), input_q_depth=4, working_buffers=2, output_fifo_lines=8, candidate_engines="parallel")
    assert parallel["total_cycles"] <= shared["total_cycles"]


def test_encoder_model_is_deterministic() -> None:
    a = _simulate_layer(_records(17), input_q_depth=4, working_buffers=2, output_fifo_lines=8, candidate_engines="parallel")
    b = _simulate_layer(_records(17), input_q_depth=4, working_buffers=2, output_fifo_lines=8, candidate_engines="parallel")
    assert a == b
