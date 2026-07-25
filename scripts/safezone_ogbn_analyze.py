#!/usr/bin/env python3
"""Exact support and cache-line analysis for the valid OGBN-Arxiv transfer."""
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
from safezone_dram_traces import _misses
from safezone_seed_runs import _support


ROOT = Path(__file__).resolve().parents[1]


def main():
    original_load = torch.load
    def trusted_load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)
    torch.load = trusted_load
    dataset = PygNodePropPredDataset(
        name="ogbn-arxiv", root=str(ROOT / "data"), transform=T.ToUndirected()
    )
    torch.load = original_load
    data = dataset[0]
    z = np.load(ROOT / "artifacts_safezone/ogbn_arxiv/supports.npz")
    shape = tuple(int(x) for x in z["shape"])
    masks = np.unpackbits(z["packed"], axis=2)[:, :, :shape[2]].astype(bool)
    segment = masks[3:]
    _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    tiles = tiles_from_order(rcm, 128)
    anchor_bits, layer_bits, exact = _support(segment, tiles)
    np.savez_compressed(
        ROOT / "artifacts_safezone/ogbn_arxiv/fixed_gap8.npz",
        anchor_bits=np.asarray([anchor_bits]), layer_bits=layer_bits,
    )
    width = 128
    minimum = align64(width + math.ceil(width / 8) + 8)
    colored = minimum + 64 if (minimum // 64) % 2 == 0 else minimum
    sources = _edge_sources(data.edge_index.cpu().numpy(), "O0")
    layer_ids = (4, 8)
    topology = data.edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
    out = ROOT / "artifacts_safezone/dram"
    timings = {}
    for fmt in ("beicsr", "xorflow"):
        trace_path = out / f"ogbn_arxiv_deepres8_w128_{fmt}.trace"
        cache_misses = 0
        metadata_total = 0
        with trace_path.open("w") as handle:
            for index, layer_id in enumerate(layer_ids):
                physical = "beicsr" if fmt == "beicsr" else "xorflow"
                lines, layout = _line_trace(
                    masks[layer_id - 1], sources, width, physical, colored
                )
                missed = _misses(lines)
                cache_misses += len(missed)
                base = (index % 2) * 0x40000000
                for line in missed:
                    address = base + int(line) * 64
                    handle.write(f"LD 0x{address:x}\nLD 0x{address + 32:x}\n")
                for byte in range(0, topology, 64):
                    handle.write(f"LD 0x{0x100000000 + byte:x}\n")
                    handle.write(f"LD 0x{0x100000000 + byte + 32:x}\n")
                if fmt == "xorflow":
                    metadata = (
                        anchor_bits // len(layer_ids) + int(layer_bits[layer_id - 4])
                    ) // 8
                    metadata_total += metadata
                    for byte in range(0, metadata, 64):
                        address = 0x200000000 + index * 0x10000000 + byte
                        handle.write(f"LD 0x{address:x}\nLD 0x{address + 32:x}\n")
        descriptors = len(layer_ids) * math.ceil(data.num_nodes * 4 / 64)
        bytes_total = cache_misses * 64 + len(layer_ids) * topology + metadata_total
        decode = math.ceil(metadata_total * 8 / 2048)
        timings[fmt] = (bytes_total, decode, descriptors, trace_path)
    beic = timings["beicsr"]
    xor = timings["xorflow"]
    beic_cycles = math.ceil(beic[0] / 256) + beic[2]
    xor_serial = math.ceil(xor[0] / 256) + xor[1] + xor[2]
    xor_overlap = max(math.ceil(xor[0] / 256), xor[1]) + xor[2]
    result = {
        "config_id": "ogbn_arxiv_deepres8_w128",
        "support_bits": anchor_bits + int(layer_bits.sum()),
        "beicsr_support_bits": int(segment.size),
        "support_ratio_to_beicsr": (anchor_bits + int(layer_bits.sum())) / segment.size,
        "beicsr_bytes": beic[0],
        "xorflow_bytes": xor[0],
        "traffic_reduction": 1 - xor[0] / beic[0],
        "roofline_serialized_speedup": beic_cycles / xor_serial,
        "roofline_double_buffered_speedup": beic_cycles / xor_overlap,
        "exactness_pass": exact,
    }
    pd.DataFrame([result]).to_csv(
        ROOT / "results_safezone/60_ogbn_arxiv_xorflow.csv", index=False
    )
    print(result)


if __name__ == "__main__":
    main()
