import numpy as np
import torch

from mosaic_validation.hpca_sparse import IncomingCsrSampler


def test_incoming_sampler_is_deterministic_and_in_range() -> None:
    edge = torch.tensor([[0, 2, 3, 4, 1], [1, 1, 2, 2, 4]])
    sampler = IncomingCsrSampler(edge, 5)
    first = sampler.sample(np.array([1]), layers=3, fanout=2, rng=np.random.default_rng(7))
    second = sampler.sample(np.array([1]), layers=3, fanout=2, rng=np.random.default_rng(7))
    assert np.array_equal(first.nodes, second.nodes)
    assert torch.equal(first.edge_index, second.edge_index)
    assert int(first.edge_index.max()) < len(first.nodes)
    assert first.nodes[first.seed_local.numpy()].tolist() == [1]
