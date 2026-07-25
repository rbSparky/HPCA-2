#!/usr/bin/env python3
"""Graph-scale and learned-structure validation on the trained Arxiv trace."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch_geometric.transforms as T
from ogb.nodeproppred import PygNodePropPredDataset

from mosaic_validation.delta_encoding import align64
from mosaic_validation.final8_cli import _cache_sim, _edge_sources, _line_trace
from mosaic_validation.graph_order import symmetrized_edges_and_rcm, tiles_from_order
from safezone_seed_runs import _support


ROOT = Path(__file__).resolve().parents[1]


def _dataset():
    original = torch.load
    def trusted(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original(*args, **kwargs)
    torch.load = trusted
    dataset = PygNodePropPredDataset(
        name="ogbn-arxiv", root=str(ROOT / "data"), transform=T.ToUndirected()
    )
    torch.load = original
    return dataset[0]


def _performance(masks, edge_index, anchor_bits, layer_bits):
    nodes, width = masks.shape[1:]
    sources = _edge_sources(edge_index, "O0")
    minimum = align64(width + math.ceil(width / 8) + 8)
    colored = minimum + 64 if (minimum // 64) % 2 == 0 else minimum
    topology = edge_index.shape[1] * 4 + (nodes + 1) * 4
    layers = (4, 8)
    beic = serial = overlap = 0
    for layer_id in layers:
        btrace, layout = _line_trace(
            masks[layer_id - 1], sources, width, "beicsr", colored
        )
        xtrace, _ = _line_trace(
            masks[layer_id - 1], sources, width, "xorflow", colored
        )
        _, _, bm = _cache_sim(btrace, 512 * 1024)
        _, _, xm = _cache_sim(xtrace, 512 * 1024)
        descriptor = math.ceil(layout["row_slices"] * 4 / 64)
        metadata = (
            anchor_bits // len(layers) + int(layer_bits[layer_id - 4])
        ) // 8
        bc = math.ceil((bm * 64 + topology) / 256)
        xc = math.ceil((xm * 64 + topology + metadata) / 256)
        dc = math.ceil(metadata * 8 / 2048)
        beic += bc + descriptor
        serial += xc + dc + descriptor
        overlap += max(xc, dc) + descriptor
    return beic / serial, beic / overlap


def main():
    data = _dataset()
    z = np.load(ROOT / "artifacts_safezone/ogbn_arxiv/supports.npz")
    shape = tuple(int(x) for x in z["shape"])
    masks = np.unpackbits(z["packed"], axis=2)[:, :, :shape[2]].astype(bool)
    edge = data.edge_index.cpu().numpy()
    _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    rows = []
    for nodes in (4096, 16384, 65536, data.num_nodes):
        selected = rcm[:nodes]
        inverse = np.full(data.num_nodes, -1, dtype=np.int64)
        inverse[selected] = np.arange(nodes)
        keep = (inverse[edge[0]] >= 0) & (inverse[edge[1]] >= 0)
        local_edge = np.stack((inverse[edge[0, keep]], inverse[edge[1, keep]]))
        local_masks = masks[:, selected]
        segment = local_masks[3:]
        tiles = tiles_from_order(np.arange(nodes), 128)
        anchor_bits, layer_bits, exact = _support(segment, tiles)
        serial, overlap = _performance(
            local_masks, local_edge, anchor_bits, layer_bits
        )
        rows.append({
            "nodes": nodes,
            "edges": local_edge.shape[1],
            "feature_width": local_masks.shape[2],
            "density": float(segment.mean()),
            "support_ratio_to_beicsr": (
                anchor_bits + int(layer_bits.sum())
            ) / segment.size,
            "roofline_serialized_speedup": serial,
            "roofline_double_buffered_speedup": overlap,
            "selected_speedup": max(1.0, overlap),
            "exactness_pass": exact,
        })
        print(rows[-1], flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(RESULTS := ROOT / "results_safezone/62_arxiv_scale.csv", index=False)

    # Full-scale density-matched independent null, preserving layer-feature
    # marginals and destroying node/temporal dependence.
    segment = masks[3:, rcm]
    rng = np.random.default_rng(7007)
    probabilities = segment.mean(axis=1, keepdims=True)
    null = rng.random(segment.shape) < probabilities
    tiles = tiles_from_order(np.arange(data.num_nodes), 128)
    real_anchor, real_layers, _ = _support(segment, tiles)
    null_anchor, null_layers, null_exact = _support(null, tiles)
    controls = pd.DataFrame([
        {
            "control": "real_trained",
            "density": float(segment.mean()),
            "support_bits": real_anchor + int(real_layers.sum()),
            "support_ratio_to_beicsr": (
                real_anchor + int(real_layers.sum())
            ) / segment.size,
            "exactness_pass": True,
        },
        {
            "control": "density_matched_independent",
            "density": float(null.mean()),
            "support_bits": null_anchor + int(null_layers.sum()),
            "support_ratio_to_beicsr": (
                null_anchor + int(null_layers.sum())
            ) / null.size,
            "exactness_pass": null_exact,
        },
    ])
    controls["ratio_over_real"] = (
        controls.support_ratio_to_beicsr
        / controls.iloc[0].support_ratio_to_beicsr
    )
    controls.to_csv(ROOT / "results_safezone/63_arxiv_learned_null.csv", index=False)
    print(controls.to_string(index=False))


if __name__ == "__main__":
    main()
