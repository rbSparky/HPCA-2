#!/usr/bin/env python3
"""Train independent seeds and rerun the principal hardware-format experiment."""
from __future__ import annotations

import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import torch

from mosaic_validation.datasets import load_dataset
from mosaic_validation.delta_encoding import align64
from mosaic_validation.final8_cli import _cache_sim, _edge_sources, _line_trace
from mosaic_validation.graph_order import symmetrized_edges_and_rcm, tiles_from_order
from mosaic_validation.hardware_gap import encode_hardware_event_set, select_hardware_dictionary
from mosaic_validation.int8_validation import classification_accuracy, make_int8_model
from mosaic_validation.models import build_deepres_v2, build_model
from mosaic_validation.reproducibility import seed_everything
from mosaic_validation.training import train_model
from mosaic_validation.xorflow import majority_anchor


ROOT = Path(__file__).resolve().parents[1]
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _support(masks: np.ndarray, tiles: list[np.ndarray]) -> tuple[int, np.ndarray, bool]:
    anchor_bits = 0
    layer_bits = np.zeros(len(masks), dtype=np.int64)
    exact = True
    width = masks.shape[2]
    for tile in tiles:
        local = masks[:, tile, :]
        anchor = majority_anchor(local)
        _, _, bits = select_hardware_dictionary(anchor)
        anchor_bits += align64(math.ceil(bits / 8)) * 8
        for layer, mask in enumerate(local):
            code = encode_hardware_event_set((mask ^ anchor).reshape(-1))
            layer_bits[layer] += align64(math.ceil(code.encoded_bits / 8)) * 8
            exact &= np.array_equal(code.decode().reshape(anchor.shape) ^ anchor, mask)
    return anchor_bits, layer_bits, exact


def _performance(cid, masks, data, anchor_bits, layer_bits):
    sources = _edge_sources(data.edge_index.cpu().numpy(), "O0")
    layer_ids = [4, 8, 12, 16] if len(masks) == 16 else [4, 8, 12, 16, 20, 24, 28]
    physical_widths = (64, 96, 128) if masks.shape[2] == 64 else (128,)
    topology = data.edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
    best_beic = float("inf")
    best_xor = float("inf")
    best_xor_overlapped = float("inf")
    for width in physical_widths:
        beic_cycles = xor_cycles = xor_overlapped = 0
        for layer_id in layer_ids:
            mask = masks[layer_id - 1]
            minimum_reserve = align64(width + math.ceil(width / 8) + 8)
            colored_reserve = (
                minimum_reserve + 64
                if (minimum_reserve // 64) % 2 == 0
                else minimum_reserve
            )
            beic_trace, beic_layout = _line_trace(
                mask, sources, width, "beicsr", colored_reserve
            )
            xor_trace, xor_layout = _line_trace(
                mask, sources, width, "xorflow", colored_reserve
            )
            _, _, beic_misses = _cache_sim(beic_trace, 512 * 1024)
            _, _, xor_misses = _cache_sim(xor_trace, 512 * 1024)
            descriptor = math.ceil(beic_layout["row_slices"] * 4 / 64)
            beic_dram = beic_misses * 64 + topology
            beic_cycles += math.ceil(beic_dram / 256) + descriptor
            offset = layer_id - 4
            metadata = (
                anchor_bits // len(layer_ids) + int(layer_bits[offset])
            ) // 8
            xor_dram = xor_misses * 64 + topology + metadata
            dram_cycles = math.ceil(xor_dram / 256)
            decode_cycles = math.ceil(metadata * 8 / 2048)
            xor_cycles += dram_cycles + decode_cycles + descriptor
            xor_overlapped += max(dram_cycles, decode_cycles) + descriptor
        best_beic = min(best_beic, beic_cycles)
        best_xor = min(best_xor, xor_cycles)
        best_xor_overlapped = min(best_xor_overlapped, xor_overlapped)
    return (
        best_beic / best_xor,
        max(1.0, best_beic / best_xor),
        best_beic / best_xor_overlapped,
    )


def main() -> None:
    out = ROOT / "artifacts_safezone/seeds"
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    configs = (
        ("cora_gcnii16", "Cora", "gcnii"),
        ("pubmed_gcnii16", "PubMed", "gcnii"),
        ("cora_deepres28_w128", "Cora", "deepres"),
    )
    for seed in (17, 27):
        for cid, dataset_name, kind in configs:
            print(f"SAFEZONE_SEED={seed} CONFIG={cid}", flush=True)
            seed_everything(seed)
            data, _, classes = load_dataset(dataset_name, ROOT / "data")
            if kind == "gcnii":
                model = build_model("gcnii", data.num_features, 64, classes, 16, .50)
                cfg = SimpleNamespace(
                    learning_rate=.01, weight_decay=.0005, max_epochs=120,
                    min_epochs=40, validation_interval=2, patience_checks=20,
                )
                cap = 18
            else:
                model = build_deepres_v2(data.num_features, 128, classes, 28, .20, .20)
                cfg = SimpleNamespace(
                    learning_rate=.005, weight_decay=.0005, max_epochs=220,
                    min_epochs=60, validation_interval=2, patience_checks=30,
                )
                cap = 12
            checkpoint = out / f"{cid}_seed{seed}.pt"
            trained = train_model(model, data, DEVICE, cfg, cap, checkpoint)
            fp32 = classification_accuracy(model, data, DEVICE)
            fp8_model = make_int8_model(model, value_format="fp8").to(DEVICE).eval()
            fp8 = classification_accuracy(fp8_model, data, DEVICE)
            with torch.no_grad():
                _, traces = fp8_model(
                    data.x.to(DEVICE), data.edge_index.to(DEVICE), trace=True
                )
            masks = np.stack([(trace > 0).cpu().numpy() for trace in traces])
            segment = masks[3:]
            _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
            tiles = tiles_from_order(rcm, 128)
            anchor_bits, layer_bits, exact = _support(segment, tiles)
            raw_speed, selected_speed, overlapped_speed = _performance(
                cid, masks, data, anchor_bits, layer_bits
            )
            np.savez_compressed(
                out / f"{cid}_seed{seed}_supports.npz",
                packed=np.packbits(masks, axis=2),
                shape=np.asarray(masks.shape),
            )
            rows.append({
                "config_id": cid,
                "seed": seed,
                "epochs": trained.epochs_completed,
                "best_epoch": trained.best_epoch,
                "train_seconds": trained.train_seconds,
                "fp32_test_accuracy": fp32["test_accuracy"],
                "fp8_test_accuracy": fp8["test_accuracy"],
                "accuracy_drop": fp32["test_accuracy"] - fp8["test_accuracy"],
                "median_density": float(np.median(segment.mean(axis=(1, 2)))),
                "fixed_gap8_support_bits": anchor_bits + int(layer_bits.sum()),
                "raw_serialized_speedup": raw_speed,
                "selected_speedup": selected_speed,
                "overlapped_speedup": max(1.0, overlapped_speed),
                "exactness_pass": exact,
            })
    results = ROOT / "results_safezone"
    frame = pd.DataFrame(rows)
    frame.to_csv(results / "53_cross_seed_validation.csv", index=False)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
