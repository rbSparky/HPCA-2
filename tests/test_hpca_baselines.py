"""Regression tests for exact common-format baseline accounting."""
from __future__ import annotations

import numpy as np

from mosaic_validation.hpca_baselines import baseline_names, build_baseline_layout, simulate_baseline_layout_lru
from mosaic_validation.memory_subsystem import validate_nonoverlap


def test_fixed_baselines_count_all_legal_metadata() -> None:
    mask = np.array([[1, 0, 1, 0, 0, 0, 0, 1], [0, 1, 0, 0, 1, 1, 0, 0]], dtype=bool)
    nnz = int(mask.sum())
    dense = build_baseline_layout(mask, name="DENSE", slice_width=4)
    csr32 = build_baseline_layout(mask, name="CSR32", slice_width=4)
    packed = build_baseline_layout(mask, name="CSR_PACKED", slice_width=4)
    beicsr = build_baseline_layout(mask, name="BEICSR", slice_width=4)

    assert dense.value_bytes == mask.size and dense.total_metadata_bytes == 0
    assert csr32.value_bytes == nnz and csr32.support_bytes == 4 * nnz
    assert csr32.row_pointer_bytes == (2 * 2 + 1) * 4
    # F=8 requires exactly three feature-ID bits per nonzero.
    assert packed.support_bytes == 4
    assert beicsr.support_bytes == 2 * 2 * 1
    assert beicsr.descriptor_bytes == 2 * 2 * 4
    for item in (dense, csr32, packed, beicsr):
        assert validate_nonoverlap(item.layout)
        assert item.layout.useful_layout_bytes == item.value_bytes + item.support_bytes + item.descriptor_bytes


def test_independent_best_has_a_single_exact_selector_stream() -> None:
    # The zero row may legally select packed CSR; a dense row selects dense.
    mask = np.array([[0, 0, 0, 0], [1, 1, 1, 1]], dtype=bool)
    best = build_baseline_layout(mask, name="INDEPENDENT_BEST", slice_width=4)
    assert best.selected_row_formats is not None
    assert best.selected_row_formats.shape == (2, 1)
    assert best.selected_row_formats[0, 0] in {"CSR32", "CSR_PACKED"}
    assert best.selected_row_formats[1, 0] == "DENSE"
    assert best.selector_bits == 4
    assert best.selector_bytes == 64
    assert best.row_pointer_bytes == (2 + 1) * 4
    assert validate_nonoverlap(best.layout)
    assert best.layout.useful_layout_bytes == best.value_bytes + best.support_bytes


def test_baseline_order_is_stable_for_artifact_tables() -> None:
    assert baseline_names() == ("DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST")


def test_streaming_baseline_cache_replays_pointer_selector_and_values_exactly() -> None:
    mask = np.array([[1, 0, 0, 1], [0, 1, 1, 0]], dtype=bool)
    sources = np.array([0, 1, 0, 1], dtype=np.int64)
    for name in ("DENSE", "CSR32", "CSR_PACKED", "BEICSR", "INDEPENDENT_BEST"):
        item = build_baseline_layout(mask, name=name, slice_width=4)
        reference = simulate_baseline_layout_lru(item, sources, capacity_bytes=1024, use_numba=False)
        accelerated = simulate_baseline_layout_lru(item, sources, capacity_bytes=1024, use_numba=True)
        assert (accelerated.accesses, accelerated.hits, accelerated.misses) == (reference.accesses, reference.hits, reference.misses)
