import numpy as np
import pytest

from mosaic_validation.panel_encoding import (
    contiguous_panels,
    correlation_panels,
    density_sorted_panels,
    validate_partition,
)


def test_all_panel_builders_are_exact_partitions():
    rng = np.random.default_rng(7)
    window = rng.random((3, 5, 11)) < 0.4
    for panels in (
        contiguous_panels(11, 4),
        density_sorted_panels(window, 4),
        correlation_panels(window, 4),
    ):
        validate_partition(panels, 11)


def test_invalid_partition_is_rejected():
    with pytest.raises(ValueError):
        validate_partition([np.array([0, 1]), np.array([1, 2])], 3)
