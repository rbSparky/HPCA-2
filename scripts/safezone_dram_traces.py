#!/usr/bin/env python3
"""Emit post-cache HBM2 traces for the principal fixed-gap8 comparison."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from numba import njit

from mosaic_validation.datasets import load_dataset
from mosaic_validation.final8_cli import _edge_sources, _line_trace


ROOT = Path(__file__).resolve().parents[1]


@njit(cache=True)
def _misses(lines, capacity_bytes=512 * 1024, associativity=16):
    sets = max(1, capacity_bytes // (64 * associativity))
    tags = np.full((sets, associativity), -1, dtype=np.int64)
    ages = np.zeros((sets, associativity), dtype=np.int64)
    output = np.empty(len(lines), dtype=np.int64)
    count = tick = 0
    for line in lines:
        tick += 1
        set_id = int(line % sets)
        tag = int(line // sets)
        found = -1
        for way in range(associativity):
            if tags[set_id, way] == tag:
                found = way
                break
        if found >= 0:
            ages[set_id, found] = tick
        else:
            output[count] = line
            count += 1
            victim = 0
            for way in range(1, associativity):
                if tags[set_id, way] < 0:
                    victim = way
                    break
                if ages[set_id, way] < ages[set_id, victim]:
                    victim = way
            tags[set_id, victim] = tag
            ages[set_id, victim] = tick
    return output[:count]


def _load(cid):
    z = np.load(ROOT / f"artifacts_final8/masks/{cid}_fp8_supports.npz")
    shape = tuple(int(x) for x in z["shape"])
    return np.unpackbits(z["packed"], axis=2)[:, :, :shape[2]].astype(bool)


def main():
    out = ROOT / "artifacts_safezone/dram"
    out.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(ROOT / "results_final8/48_final8_summary.csv").set_index("config_id")
    safe = pd.read_csv(ROOT / "results_safezone/51_hardware_format_sensitivity.csv")
    manifest = []
    cases = []
    for cid in ("cora_gcnii16", "pubmed_gcnii16", "cora_deepres28_w128"):
        cases.append((cid, 7, ROOT / f"artifacts_final8/masks/{cid}_fp8_supports.npz"))
        for seed in (17, 27):
            cases.append((
                cid, seed,
                ROOT / f"artifacts_safezone/seeds/{cid}_seed{seed}_supports.npz",
            ))
    for cid, seed, mask_path in cases:
        dataset_name = "PubMed" if "pubmed" in cid else "Cora"
        data, _, _ = load_dataset(dataset_name, ROOT / "data")
        z = np.load(mask_path)
        shape = tuple(int(x) for x in z["shape"])
        masks = np.unpackbits(z["packed"], axis=2)[:, :, :shape[2]].astype(bool)
        sources = _edge_sources(data.edge_index.cpu().numpy(), "O0")
        layer_ids = [4, 8, 12, 16] if len(masks) == 16 else [4, 8, 12, 16, 20, 24, 28]
        beic_width = int(summary.loc[cid, "best_beicsr_slice_width"])
        principal = safe[
            (safe.config_id == cid)
            & (safe.feature_cache_bytes == 512 * 1024)
            & (safe.dram_bytes_per_cycle == 256)
            & (safe.aggregate_decode_width_bits == 2048)
        ].iloc[0]
        xor_width = int(principal.physical_slice_width)
        if seed == 7:
            support = np.load(ROOT / f"artifacts_safezone/streams/{cid}_fixed_gap8.npz")
            anchor_bits = int(support["anchor_bits"][0])
            layer_bits = support["layer_bits"]
        else:
            from safezone_seed_runs import _support
            from mosaic_validation.graph_order import symmetrized_edges_and_rcm, tiles_from_order
            _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
            anchor_bits, layer_bits, _ = _support(
                masks[3:], tiles_from_order(rcm, 128)
            )
        topology_bytes = data.edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
        sampled_metadata_bytes = sum(
            (
                anchor_bits // len(layer_ids)
                + int(layer_bits[layer_id - 4])
            ) // 8
            for layer_id in layer_ids
        )
        sampled_decode_cycles = sum(
            math.ceil(
                (
                    anchor_bits // len(layer_ids)
                    + int(layer_bits[layer_id - 4])
                ) / 2048
            )
            for layer_id in layer_ids
        )
        for fmt, width in (("beicsr", beic_width), ("xorflow", xor_width)):
            stem = cid if seed == 7 else f"{cid}_seed{seed}"
            trace_path = out / f"{stem}_{fmt}.trace"
            request_count = 0
            with trace_path.open("w") as handle:
                for layer_index, layer_id in enumerate(layer_ids):
                    physical = "beicsr" if fmt == "beicsr" else "xorflow"
                    minimum_reserve = math.ceil(
                        (width + math.ceil(width / 8) + 8) / 64
                    ) * 64
                    colored_reserve = (
                        minimum_reserve + 64
                        if (minimum_reserve // 64) % 2 == 0
                        else minimum_reserve
                    )
                    line_trace, _ = _line_trace(
                        masks[layer_id - 1], sources, width, physical,
                        colored_reserve,
                    )
                    miss_lines = _misses(line_trace)
                    feature_base = (layer_index % 2) * 0x40000000
                    for line in miss_lines:
                        address = feature_base + int(line) * 64
                        handle.write(f"LD 0x{address:x}\n")
                        handle.write(f"LD 0x{address + 32:x}\n")
                    request_count += 2 * len(miss_lines)
                    topology_base = 0x100000000
                    for byte in range(0, topology_bytes, 64):
                        handle.write(f"LD 0x{topology_base + byte:x}\n")
                        handle.write(f"LD 0x{topology_base + byte + 32:x}\n")
                        request_count += 2
                    if fmt == "xorflow":
                        offset = layer_id - 4
                        metadata = (
                            anchor_bits // len(layer_ids) + int(layer_bits[offset])
                        ) // 8
                        metadata_base = 0x200000000 + layer_index * 0x100000
                        for byte in range(0, metadata, 64):
                            handle.write(f"LD 0x{metadata_base + byte:x}\n")
                            handle.write(f"LD 0x{metadata_base + byte + 32:x}\n")
                            request_count += 2
            manifest.append({
                "config_id": cid,
                "seed": seed,
                "format": fmt,
                "slice_width": width,
                "requests": request_count,
                "sampled_metadata_bytes": (
                    sampled_metadata_bytes if fmt == "xorflow" else 0
                ),
                "sampled_decode_cycles": (
                    sampled_decode_cycles if fmt == "xorflow" else 0
                ),
                "descriptor_cycles": len(layer_ids)
                * math.ceil(
                    data.num_nodes * math.ceil(masks.shape[2] / width) * 4 / 64
                ),
                "trace_path": str(trace_path),
            })
            print(manifest[-1], flush=True)
    pd.DataFrame(manifest).to_csv(out / "manifest.csv", index=False)


if __name__ == "__main__":
    main()
