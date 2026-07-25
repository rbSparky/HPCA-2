#!/usr/bin/env python3
"""Exact cache traffic for an RCM-tile-packed immutable inference layout."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from mosaic_validation.datasets import load_dataset
from mosaic_validation.final8_cli import _cache_sim, _edge_sources
from mosaic_validation.graph_order import symmetrized_edges_and_rcm, tiles_from_order


ROOT = Path(__file__).resolve().parents[1]


def _load(path: Path):
    z = np.load(path)
    shape = tuple(int(x) for x in z["shape"])
    return np.unpackbits(z["packed"], axis=2)[:, :, :shape[2]].astype(bool)


def _packed_row_lines(mask, tiles, bitmap: bool):
    """Pack rows inside 4-KiB-independent topology tiles; return lines by node."""
    rows, features = mask.shape
    line_lists = [None] * rows
    cursor = 0
    useful = 0
    for tile in tiles:
        cursor = math.ceil(cursor / 64) * 64
        for node in tile:
            size = int(mask[node].sum()) + (math.ceil(features / 8) if bitmap else 0)
            size = max(size, 1)
            first = cursor // 64
            last = (cursor + size - 1) // 64
            line_lists[int(node)] = np.arange(first, last + 1, dtype=np.int64)
            cursor += size
            useful += size
        # A tile never shares a line with another tile.
        cursor = math.ceil(cursor / 64) * 64
    return line_lists, cursor, useful


def _trace(lines, sources):
    sizes = np.asarray([len(lines[int(node)]) for node in sources])
    result = np.empty(int(sizes.sum()), dtype=np.int64)
    cursor = 0
    for node in sources:
        values = lines[int(node)]
        result[cursor:cursor + len(values)] = values
        cursor += len(values)
    return result


def _analyze(cid, seed, masks, data, anchor_bits, layer_bits):
    _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    tiles = tiles_from_order(rcm, 128)
    sources = _edge_sources(data.edge_index.cpu().numpy(), "O0")
    layer_ids = [4, 8, 12, 16] if len(masks) == 16 else [4, 8, 12, 16, 20, 24, 28]
    topology = data.edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
    descriptor_bytes = data.num_nodes * 8
    beic_cycles = xor_cycles = xor_overlap = 0
    beic_dram_total = xor_dram_total = 0
    for layer_id in layer_ids:
        mask = masks[layer_id - 1]
        beic_lines, _, _ = _packed_row_lines(mask, tiles, True)
        xor_lines, _, _ = _packed_row_lines(mask, tiles, False)
        _, _, beic_misses = _cache_sim(_trace(beic_lines, sources), 512 * 1024)
        _, _, xor_misses = _cache_sim(_trace(xor_lines, sources), 512 * 1024)
        beic_dram = beic_misses * 64 + topology + descriptor_bytes
        offset = layer_id - 4
        metadata = (anchor_bits // len(layer_ids) + int(layer_bits[offset])) // 8
        xor_dram = xor_misses * 64 + topology + descriptor_bytes + metadata
        descriptor_cycles = math.ceil(descriptor_bytes / 64)
        decode = math.ceil(metadata * 8 / 2048)
        beic_cycles += math.ceil(beic_dram / 256) + descriptor_cycles
        xor_cycles += math.ceil(xor_dram / 256) + decode + descriptor_cycles
        xor_overlap += max(math.ceil(xor_dram / 256), decode) + descriptor_cycles
        beic_dram_total += beic_dram
        xor_dram_total += xor_dram
    return {
        "config_id": cid,
        "seed": seed,
        "packed_beicsr_dram_bytes": beic_dram_total,
        "packed_xorflow_dram_bytes": xor_dram_total,
        "packed_traffic_reduction": 1 - xor_dram_total / beic_dram_total,
        "packed_serialized_speedup": beic_cycles / xor_cycles,
        "packed_overlapped_speedup": beic_cycles / xor_overlap,
    }


def main():
    rows = []
    cases = [
        ("cora_gcnii16", 7, ROOT / "artifacts_final8/masks/cora_gcnii16_fp8_supports.npz"),
        ("pubmed_gcnii16", 7, ROOT / "artifacts_final8/masks/pubmed_gcnii16_fp8_supports.npz"),
        ("cora_deepres28_w128", 7, ROOT / "artifacts_final8/masks/cora_deepres28_w128_fp8_supports.npz"),
    ]
    for seed in (17, 27):
        for cid in ("cora_gcnii16", "pubmed_gcnii16", "cora_deepres28_w128"):
            cases.append((cid, seed, ROOT / f"artifacts_safezone/seeds/{cid}_seed{seed}_supports.npz"))
    for cid, seed, path in cases:
        dataset_name = "PubMed" if "pubmed" in cid else "Cora"
        data, _, _ = load_dataset(dataset_name, ROOT / "data")
        masks = _load(path)
        if seed == 7:
            support = np.load(ROOT / f"artifacts_safezone/streams/{cid}_fixed_gap8.npz")
            anchor_bits = int(support["anchor_bits"][0])
            layer_bits = support["layer_bits"]
        else:
            # These exact values were saved in the cross-seed table only as a
            # total, so reconstruct them with the shared helper.
            from safezone_seed_runs import _support
            _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
            anchor_bits, layer_bits, _ = _support(masks[3:], tiles_from_order(rcm, 128))
        rows.append(_analyze(cid, seed, masks, data, anchor_bits, layer_bits))
        print(rows[-1], flush=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results_safezone/54_packed_layout.csv", index=False)


if __name__ == "__main__":
    main()
