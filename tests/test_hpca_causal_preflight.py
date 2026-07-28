import numpy as np

from mosaic_validation.hpca_xorflow_cli import _output_writeback_traffic, _pair_starts, _sources, build_pair_format_plan


def test_short_depth_pair_starts_are_a_nonempty_diagnostic() -> None:
    assert _pair_starts(4, None) == [0, 2]
from mosaic_validation.memory_subsystem import build_mixed_sliced_layout, validate_nonoverlap


def test_pair_schedule_is_nonoverlapping_and_starts_at_hidden_layer_four():
    assert _pair_starts(8, None) == [3, 5]


def test_source_orders_preserve_exact_source_multiset():
    edges = np.array([[3, 0, 2, 1], [1, 0, 1, 0]], dtype=np.int64)
    assert sorted(_sources(edges, "O0").tolist()) == sorted(edges[0].tolist())
    assert sorted(_sources(edges, "O1").tolist()) == sorted(edges[0].tolist())


def test_mixed_selector_layout_has_no_overlap():
    mask = np.ones((3, 8), dtype=bool)
    formats = np.array([["BEICSR", "XORFLOW"], ["XORFLOW", "BEICSR"], ["BEICSR", "BEICSR"]], dtype=object)
    layout = build_mixed_sliced_layout(mask, slice_width=4, formats=formats, node_order=np.array([2, 0, 1]))
    assert validate_nonoverlap(layout)


def test_output_writeback_counts_rfo_and_dirty_eviction():
    mask = np.array([[1, 0, 0, 1]], dtype=bool)
    layout = build_mixed_sliced_layout(mask, slice_width=4, formats=np.array([["XORFLOW"]], dtype=object))
    assert _output_writeback_traffic([layout]) == 128


def test_pair_plan_has_selector_and_never_selects_an_illegal_format():
    pair = np.random.default_rng(7).random((2, 4, 8)) > .5
    plan = build_pair_format_plan(pair, [np.arange(4)], 8)
    assert plan["formats"].shape == (4, 1)
    assert plan["xor_support_bits"] > 0 and plan["beicsr_support_bits"] > 0
