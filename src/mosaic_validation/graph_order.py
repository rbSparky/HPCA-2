"""Sparse graph ordering utilities."""

import numpy as np
from scipy import sparse
from scipy.sparse.csgraph import reverse_cuthill_mckee
from torch_geometric.utils import to_undirected


def symmetrized_edges_and_rcm(edge_index, num_nodes: int) -> tuple[np.ndarray, np.ndarray]:
    undirected = to_undirected(edge_index, num_nodes=num_nodes).cpu().numpy()
    rows, cols = undirected
    adjacency = sparse.csr_matrix(
        (np.ones(rows.size, dtype=np.uint8), (rows, cols)),
        shape=(num_nodes, num_nodes),
    )
    assert sparse.issparse(adjacency), "Dense N x N adjacency is forbidden"
    order = reverse_cuthill_mckee(adjacency, symmetric_mode=True).astype(np.int64)
    keep = rows < cols
    unique_edges = np.stack((rows[keep], cols[keep]), axis=1).astype(np.int64)
    return unique_edges, order


def tiles_from_order(order: np.ndarray, tile_size: int = 128) -> list[np.ndarray]:
    return [order[start : start + tile_size] for start in range(0, order.size, tile_size)]

