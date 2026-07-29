"""Determinism and preservation tests for traffic-level structure controls."""
from __future__ import annotations

import numpy as np

from mosaic_validation.hpca_format_controls import construct_controls, node_permutation_within_tiles


def test_tiled_node_permutation_preserves_row_count_multiset_and_tile_membership() -> None:
    masks = np.random.default_rng(7).random((3, 8, 5)) < 0.4
    tiles = [np.array([0, 1, 2, 3]), np.array([4, 5, 6, 7])]
    permuted = node_permutation_within_tiles(masks, tiles, 7007)
    for layer in range(masks.shape[0]):
        for tile in tiles:
            assert np.array_equal(np.sort(masks[layer, tile].sum(axis=1)), np.sort(permuted[layer, tile].sum(axis=1)))


def test_controls_are_deterministic_and_real_control_is_identity() -> None:
    masks = np.random.default_rng(11).random((4, 6, 7)) < 0.3
    tiles = [np.arange(3), np.arange(3, 6)]
    first = construct_controls(masks, tiles, 7007)
    second = construct_controls(masks, tiles, 7007)
    assert np.array_equal(first["real_trained"], masks)
    assert tuple(first) == ("real_trained", "density_matched_independent", "node_permuted_within_rcm_tile", "temporally_shuffled")
    assert all(np.array_equal(first[key], second[key]) for key in first)
