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


class DeepResV2(nn.Module):
    """Pre-activation residual GCN whose traced tensor feeds each convolution."""

    def __init__(
        self,
        in_channels: int,
        hidden: int,
        classes: int,
        layers: int,
        dropout: float,
        residual_scale: float,
    ):
        super().__init__()
        self.dropout = dropout
        self.residual_scale = residual_scale
        self.input = nn.Linear(in_channels, hidden)
        self.norms = nn.ModuleList(nn.LayerNorm(hidden) for _ in range(layers))
        self.convs = nn.ModuleList(
            GCNConv(
                hidden,
                hidden,
                cached=True,
                add_self_loops=True,
                normalize=True,
            )
            for _ in range(layers)
        )
        self.final_norm = nn.LayerNorm(hidden)
        self.output = nn.Linear(hidden, classes)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor, trace: bool = False):
        h = self.input(x)
        traces = []
        for norm, conv in zip(self.norms, self.convs, strict=True):
            z = torch.relu(norm(h))
            if trace:
                traces.append(z)
            z = nn.functional.dropout(z, self.dropout, self.training)
            h = h + self.residual_scale * conv(z, edge_index)
        z = torch.relu(self.final_norm(h))
        z = nn.functional.dropout(z, self.dropout, self.training)
        logits = self.output(z)
        return (logits, traces) if trace else logits


def build_model(kind: str, features: int, hidden: int, classes: int, layers: int, dropout: float):
    cls = GCNII if kind == "gcnii" else ResidualGCN
    return cls(features, hidden, classes, layers, dropout)


def build_deepres_v2(
    features: int,
    hidden: int,
    classes: int,
    layers: int,
    dropout: float,
    residual_scale: float,
) -> DeepResV2:
    return DeepResV2(
        features, hidden, classes, layers, dropout, residual_scale
    )
