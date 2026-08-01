import torch

from mosaic_validation.hpca_sparse import deepres_csr_forward, normalized_csr_adjacency
from mosaic_validation.models import build_deepres_v2


def test_csr_deepres_matches_gcnconv_on_small_undirected_graph() -> None:
    torch.manual_seed(7)
    # Bidirectional graph with no existing self loops, matching the large-data
    # construction path.
    edges = torch.tensor([[0, 1, 1, 2, 2, 3], [1, 0, 2, 1, 3, 2]])
    model = build_deepres_v2(3, 5, 2, 2, 0.0, .2).eval()
    x = torch.randn(4, 3)
    csr = normalized_csr_adjacency(edges, 4, torch.device("cpu"))
    expected = model(x, edges)
    actual = deepres_csr_forward(model, x, csr)
    assert torch.allclose(actual, expected, rtol=1e-5, atol=1e-6)


def test_checkpointed_csr_backward_produces_gradients() -> None:
    torch.manual_seed(7)
    edges = torch.tensor([[0, 1, 1, 2], [1, 0, 2, 1]])
    model = build_deepres_v2(3, 5, 2, 2, 0.1, .2).train()
    x = torch.randn(3, 3)
    csr = normalized_csr_adjacency(edges, 3, torch.device("cpu"))
    loss = torch.nn.functional.cross_entropy(deepres_csr_forward(model, x, csr, checkpoint_blocks=True), torch.tensor([0, 1, 0]))
    loss.backward()
    assert all(parameter.grad is not None for parameter in model.parameters())
