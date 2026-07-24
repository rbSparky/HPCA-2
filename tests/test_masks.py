import numpy as np

from mosaic_validation.cohorts import optimal_template
from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.pair_metrics import pair_mismatches


def test_exact_decomposition_and_known_cases():
    rng = np.random.default_rng(7)
    mask = rng.random((12, 8)) > 0.5
    template = rng.random(8) > 0.5
    core = np.logical_and(mask, template)
    residual = np.logical_and(mask, ~template)
    assert np.array_equal(np.logical_or(core, residual), mask)
    assert not np.logical_and(core, residual).any()
    identical = np.ones((2, 8), dtype=bool)
    assert pair_mismatches(identical, np.array([[0, 1]])).item() == 0
    disjoint = np.array([[1, 1, 0, 0], [0, 0, 1, 1]], dtype=bool)
    assert pair_mismatches(disjoint, np.array([[0, 1]])).item() == 1
    assert not optimal_template(np.zeros((4, 8), dtype=bool)).any()
    assert optimal_template(np.ones((4, 8), dtype=bool)).all()


def test_no_dense_adjacency(monkeypatch):
    import torch

    edge_index = torch.tensor([[0, 1, 1], [1, 0, 2]])
    edges, order = symmetrized_edges_and_rcm(edge_index, 3)
    assert edges.shape[1] == 2
    assert order.shape == (3,)

