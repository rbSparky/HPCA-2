#!/usr/bin/env python3
"""Cache-capacity robustness with channel-colored fixed-gap8 rows."""
import math
from pathlib import Path

import numpy as np
import pandas as pd

from mosaic_validation.datasets import load_dataset
from mosaic_validation.delta_encoding import align64
from mosaic_validation.final8_cli import _cache_sim, _edge_sources, _line_trace


ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for cid in ("cora_gcnii16", "pubmed_gcnii16", "cora_deepres28_w128"):
        dataset_name = "PubMed" if "pubmed" in cid else "Cora"
        data, _, _ = load_dataset(dataset_name, ROOT / "data")
        z = np.load(ROOT / f"artifacts_final8/masks/{cid}_fp8_supports.npz")
        shape = tuple(int(x) for x in z["shape"])
        masks = np.unpackbits(z["packed"], axis=2)[:, :, :shape[2]].astype(bool)
        support = np.load(ROOT / f"artifacts_safezone/streams/{cid}_fixed_gap8.npz")
        anchor_bits = int(support["anchor_bits"][0])
        layer_bits = support["layer_bits"]
        sources = _edge_sources(data.edge_index.cpu().numpy(), "O0")
        layers = [4, 8, 12, 16] if len(masks) == 16 else [4, 8, 12, 16, 20, 24, 28]
        widths = (64, 96, 128) if masks.shape[2] == 64 else (128,)
        topology = data.edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
        for cache in (256 * 1024, 512 * 1024, 1024 * 1024):
            candidates = []
            for width in widths:
                beic = xor_serial = xor_overlap = 0
                minimum = align64(width + math.ceil(width / 8) + 8)
                colored = minimum + 64 if (minimum // 64) % 2 == 0 else minimum
                for layer_id in layers:
                    mask = masks[layer_id - 1]
                    bt, bl = _line_trace(mask, sources, width, "beicsr", colored)
                    xt, xl = _line_trace(mask, sources, width, "xorflow", colored)
                    _, _, bm = _cache_sim(bt, cache)
                    _, _, xm = _cache_sim(xt, cache)
                    descriptors = math.ceil(bl["row_slices"] * 4 / 64)
                    metadata = (
                        anchor_bits // len(layers) + int(layer_bits[layer_id - 4])
                    ) // 8
                    bc = math.ceil((bm * 64 + topology) / 256)
                    xc = math.ceil((xm * 64 + topology + metadata) / 256)
                    dc = math.ceil(metadata * 8 / 2048)
                    beic += bc + descriptors
                    xor_serial += xc + dc + descriptors
                    xor_overlap += max(xc, dc) + descriptors
                candidates.append((beic, xor_serial, xor_overlap, width))
            best_beic = min(x[0] for x in candidates)
            best_serial = min(x[1] for x in candidates)
            best_overlap = min(x[2] for x in candidates)
            rows.append({
                "config_id": cid,
                "cache_bytes": cache,
                "serialized_speedup": best_beic / best_serial,
                "double_buffered_speedup": best_beic / best_overlap,
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(ROOT / "results_safezone/57_cache_sensitivity.csv", index=False)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
