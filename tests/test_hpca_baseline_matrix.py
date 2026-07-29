"""Tests for the common B0–B4 paper baseline matrix."""
from __future__ import annotations

import numpy as np

from mosaic_validation.hpca_baseline_matrix import _external_metadata_output_bytes
from mosaic_validation.hpca_baselines import build_baseline_layout


def test_external_pointer_and_selector_writes_are_not_free() -> None:
    mask = np.array([[1, 0, 1, 0]], dtype=bool)
    csr = build_baseline_layout(mask, name="CSR_PACKED", slice_width=4)
    best = build_baseline_layout(mask, name="INDEPENDENT_BEST", slice_width=4)
    assert _external_metadata_output_bytes(csr) == 2 * csr.row_pointer_stream_bytes
    assert _external_metadata_output_bytes(best) == 2 * (best.row_pointer_stream_bytes + best.selector_bytes)

