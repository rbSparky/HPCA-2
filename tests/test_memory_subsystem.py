import numpy as np

from mosaic_validation.memory_subsystem import (
    build_sliced_layout,
    simulate_set_associative_lru,
    simulate_layout_source_lru,
    materialize_cache_miss_lines,
    source_line_trace,
    touched_lines,
    validate_nonoverlap,
)


def test_physical_layout_is_nonoverlapping_and_tail_is_not_fetched():
    mask = np.array([[1, 0, 0, 1], [0, 0, 1, 0]], dtype=bool)
    layout = build_sliced_layout(mask, slice_width=4, format_name="XORFLOW")
    assert validate_nonoverlap(layout)
    assert layout.reserved_capacity_bytes > layout.useful_layout_bytes
    assert touched_lines(0, 5).tolist() == [0]


def test_beicsr_embeds_bitmap_while_xorflow_does_not():
    mask = np.array([[1, 0, 0, 1]], dtype=bool)
    beicsr = build_sliced_layout(mask, slice_width=4, format_name="BEICSR")
    xorflow = build_sliced_layout(mask, slice_width=4, format_name="XORFLOW")
    assert beicsr.useful_layout_bytes == xorflow.useful_layout_bytes + 1


def test_source_trace_and_reference_lru_are_deterministic():
    mask = np.array([[1, 1, 0, 0], [0, 1, 0, 1]], dtype=bool)
    layout = build_sliced_layout(mask, slice_width=4, format_name="XORFLOW")
    trace = source_line_trace(layout, np.array([0, 1, 0], dtype=np.int64))
    first = simulate_set_associative_lru(trace, capacity_bytes=64 * 16)
    second = simulate_set_associative_lru(trace, capacity_bytes=64 * 16)
    assert first == second
    assert first.hits == 1 and first.misses == 2


def test_streaming_numba_cache_matches_reference_trace():
    mask = np.array([[1, 1, 0, 0], [0, 1, 0, 1]], dtype=bool)
    layout = build_sliced_layout(mask, slice_width=4, format_name="XORFLOW")
    sources = np.array([0, 1, 0], dtype=np.int64)
    reference = simulate_set_associative_lru(source_line_trace(layout, sources), capacity_bytes=64 * 16)
    streamed = simulate_layout_source_lru(layout, sources, capacity_bytes=64 * 16)
    assert (streamed.accesses, streamed.hits, streamed.misses) == (reference.accesses, reference.hits, reference.misses)


def test_ordered_materialized_misses_match_lru_reference_count():
    mask = np.array([[1, 1, 0, 0], [0, 1, 0, 1]], dtype=bool)
    layout = build_sliced_layout(mask, slice_width=4, format_name="XORFLOW")
    sources = np.array([0, 1, 0, 1], dtype=np.int64)
    reference = simulate_set_associative_lru(source_line_trace(layout, sources), capacity_bytes=64 * 16)
    assert len(materialize_cache_miss_lines(layout, sources, capacity_bytes=64 * 16)) == reference.misses
