"""Deep residual GNN models with explicit post-ReLU tracing."""

import torch
from torch import nn
from torch_geometric.nn import GCN2Conv, GCNConv


class GCNII(nn.Module):
    def __init__(self, in_channels: int, hidden: int, classes: int, layers: int, dropout: float):
        super().__init__()
        self.dropout = dropout
        self.input = nn.Linear(in_channels, hidden)
        self.convs = nn.ModuleList(
            GCN2Conv(hidden, alpha=0.1, theta=0.5, layer=i, shared_weights=True, cached=True)
            for i in range(1, layers + 1)
        )
        self.output = nn.Linear(hidden, classes)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, trace: bool = False):
        x = nn.functional.dropout(x, self.dropout, self.training)
        x0 = torch.relu(self.input(x))
        x = x0
        traces = []
        for conv in self.convs:
            x = nn.functional.dropout(x, self.dropout, self.training)
            x = torch.relu(conv(x, x0, edge_index))
            if trace:
                traces.append(x)
        logits = self.output(nn.functional.dropout(x, self.dropout, self.training))
        return (logits, traces) if trace else logits


class ResidualGCN(nn.Module):
    def __init__(self, in_channels: int, hidden: int, classes: int, layers: int, dropout: float):
        super().__init__()
        self.dropout = dropout
        self.input = nn.Linear(in_channels, hidden)
        self.norms = nn.ModuleList(nn.LayerNorm(hidden) for _ in range(layers))
        self.convs = nn.ModuleList(GCNConv(hidden, hidden, cached=True) for _ in range(layers))
        self.output = nn.Linear(hidden, classes)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, trace: bool = False):
        x = torch.relu(self.input(x))
        traces = []
        for norm, conv in zip(self.norms, self.convs, strict=True):
            z = torch.relu(norm(x))
            z = nn.functional.dropout(z, self.dropout, self.training)
            x = torch.relu(x + conv(z, edge_index))
            if trace:
                traces.append(x)
        logits = self.output(nn.functional.dropout(x, self.dropout, self.training))
        return (logits, traces) if trace else logits


def build_model(kind: str, features: int, hidden: int, classes: int, layers: int, dropout: float):
    cls = GCNII if kind == "gcnii" else ResidualGCN
    return cls(features, hidden, classes, layers, dropout)

