"""Exact normalized-CSR execution for large full-graph HPCA workloads.

PyG's edge-index ``GCNConv`` normalization materializes an edge-sized message
tensor.  That is appropriate for small graphs but cannot fit Reddit's 115M
edges on the 8 GiB evaluation GPU.  This module expresses the same GCN
normalization as a sparse CSR matrix multiplication: it never forms an
``N x N`` dense matrix and is used for *both* training and full-neighbour
inference when the edge-index path is not viable.
"""
from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

import numpy as np
import torch
from scipy import sparse

from .int8_validation import fake_quant_fp8


def normalized_csr_adjacency(edge_index: torch.Tensor, nodes: int, device: torch.device) -> torch.Tensor:
    """Return GCN-style ``D^-1/2 (A+I) D^-1/2`` as a torch CSR matrix.

    Entries are stored as destination-row/source-column, matching GCNConv's
    source-to-target convention.  The input is deliberately kept on CPU while
    constructing the matrix so large edge lists do not consume GPU memory.
    """
    edges = edge_index.detach().cpu().numpy()
    source = edges[0].astype(np.int64, copy=False)
    destination = edges[1].astype(np.int64, copy=False)
    values = np.ones(source.size, dtype=np.float32)
    adjacency = sparse.csr_matrix((values, (destination, source)), shape=(nodes, nodes), dtype=np.float32)
    # Datasets used here have no self loops.  ``maximum`` keeps this legal for
    # a future dataset that already does: add one self-loop rather than two.
    diagonal = adjacency.diagonal()
    missing = np.flatnonzero(diagonal == 0)
    if missing.size:
        adjacency = adjacency + sparse.csr_matrix((np.ones(missing.size, dtype=np.float32), (missing, missing)), shape=(nodes, nodes))
    degrees = np.asarray(adjacency.sum(axis=1)).ravel().astype(np.float32)
    inverse = np.zeros_like(degrees)
    np.power(degrees, -0.5, out=inverse, where=degrees > 0)
    adjacency = sparse.diags(inverse, format="csr") @ adjacency @ sparse.diags(inverse, format="csr")
    adjacency.sort_indices()
    return torch.sparse_csr_tensor(
        torch.from_numpy(adjacency.indptr.astype(np.int64, copy=False)),
        torch.from_numpy(adjacency.indices.astype(np.int64, copy=False)),
        torch.from_numpy(adjacency.data.astype(np.float32, copy=False)),
        size=(nodes, nodes), device=device,
    )


def deepres_csr_forward(model, x: torch.Tensor, adjacency: torch.Tensor, *, trace: bool = False, fp8: bool = False, checkpoint_blocks: bool = False):
    """Run ``DeepResV2`` with exact full-neighbour CSR aggregation.

    Weight ordering, residuals, normalization, and traced pre-convolution
    tensors match ``DeepResV2.forward``.  FP8 is applied after every ReLU only,
    which is the stated stored-activation inference contract.
    """
    h = model.input(x)
    traces: list[torch.Tensor] = []
    for norm, conv in zip(model.norms, model.convs, strict=True):
        def block(state: torch.Tensor, norm=norm, conv=conv) -> torch.Tensor:
            z = torch.relu(norm(state))
            if fp8:
                z = fake_quant_fp8(z)
            z = torch.nn.functional.dropout(z, model.dropout, model.training)
            # GCNConv applies its linear transformation before normalized SpMM.
            update = torch.sparse.mm(adjacency, conv.lin(z))
            if conv.bias is not None:
                update = update + conv.bias
            return state + model.residual_scale * update
        if trace:
            # Tracing is inference-only in this project, so this branch avoids
            # keeping duplicate checkpoint activations.
            traces.append(fake_quant_fp8(torch.relu(norm(h))) if fp8 else torch.relu(norm(h)))
        h = torch.utils.checkpoint.checkpoint(block, h, use_reentrant=False) if checkpoint_blocks and torch.is_grad_enabled() else block(h)
    z = torch.relu(model.final_norm(h))
    if fp8:
        z = fake_quant_fp8(z)
    z = torch.nn.functional.dropout(z, model.dropout, model.training)
    logits = model.output(z)
    return (logits, traces) if trace else logits


@dataclass(frozen=True)
class SampledSubgraph:
    """One deterministic sampled full-homogeneous GCN training subgraph."""

    nodes: np.ndarray
    edge_index: torch.Tensor
    seed_local: torch.Tensor


class IncomingCsrSampler:
    """Memory-bounded deterministic inbound-neighbour sampler.

    Unlike ``NeighborLoader``, this keeps only integer CSR neighbours and does
    not materialize a second edge-index/CSC copy of a 100M-edge graph.  It is
    used *only* for the explicitly allowed sampled-training phase.  Exact
    support capture always uses :func:`normalized_csr_adjacency`.
    """

    def __init__(self, edge_index: torch.Tensor, nodes: int) -> None:
        edges = edge_index.detach().cpu().numpy()
        source = edges[0].astype(np.int32, copy=False)
        destination = edges[1].astype(np.int64, copy=False)
        # scipy performs the needed destination ordering without constructing
        # a dense adjacency.  Values are discarded immediately afterwards.
        matrix = sparse.csr_matrix((np.ones(source.size, dtype=np.uint8), (destination, source)), shape=(nodes, nodes), dtype=np.uint8)
        matrix.sort_indices()
        self.indptr = matrix.indptr.astype(np.int64, copy=True)
        self.indices = matrix.indices.astype(np.int32, copy=True)

    def sample(self, seeds: np.ndarray, *, layers: int, fanout: int, rng: np.random.Generator) -> SampledSubgraph:
        """Sample inbound edges without looking at labels or activation masks."""
        frontier = np.asarray(seeds, dtype=np.int64)
        all_nodes: set[int] = {int(node) for node in frontier}
        source_edges: list[int] = []
        destination_edges: list[int] = []
        for _ in range(layers):
            next_nodes: list[int] = []
            for destination in frontier:
                begin, end = int(self.indptr[destination]), int(self.indptr[destination + 1])
                degree = end - begin
                if degree <= 0:
                    continue
                count = min(fanout, degree)
                if count == degree:
                    chosen = self.indices[begin:end]
                else:
                    chosen = self.indices[begin + rng.choice(degree, size=count, replace=False)]
                for source in chosen:
                    source_i = int(source)
                    source_edges.append(source_i)
                    destination_edges.append(int(destination))
                    next_nodes.append(source_i)
                    all_nodes.add(source_i)
            if not next_nodes:
                break
            frontier = np.unique(np.asarray(next_nodes, dtype=np.int64))
        node_ids = np.asarray(sorted(all_nodes), dtype=np.int64)
        source_local = np.searchsorted(node_ids, np.asarray(source_edges, dtype=np.int64))
        destination_local = np.searchsorted(node_ids, np.asarray(destination_edges, dtype=np.int64))
        edge_index = torch.from_numpy(np.stack([source_local, destination_local]).astype(np.int64, copy=False))
        seed_local = torch.from_numpy(np.searchsorted(node_ids, np.asarray(seeds, dtype=np.int64)).astype(np.int64, copy=False))
        return SampledSubgraph(node_ids, edge_index, seed_local)
