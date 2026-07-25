#!/usr/bin/env python3
"""Measure format-aware throughput of the RTL decoder on saved real streams."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

from mosaic_validation.datasets import load_dataset
from mosaic_validation.graph_order import symmetrized_edges_and_rcm, tiles_from_order
from mosaic_validation.delta_encoding import align64
from mosaic_validation.hardware_gap import (
    encode_hardware_event_set,
    select_hardware_dictionary,
)
from mosaic_validation.xorflow import encode_slice


ROOT = Path(__file__).resolve().parents[1]


def _unpack(path: Path) -> np.ndarray:
    z = np.load(path)
    shape = tuple(int(x) for x in z["shape"])
    return np.unpackbits(z["packed"], axis=2)[:, :, : shape[2]].astype(bool)


def _code_cycles(code) -> tuple[int, list[int]]:
    """Return conservative lane cycles and observed block gap widths."""
    k = len(code.events)
    header_cycles = 1
    if code.selected_format == "DENSE_XOR":
        return header_cycles + math.ceil(code.universe / 64), []
    if code.selected_format in ("FIXED_IDS", "ZERO_IDS"):
        return header_cycles + math.ceil(k / 4), []
    events = np.asarray(code.events, dtype=np.int64)
    widths: list[int] = []
    event_cycles = 0
    block = int(code.gap_block_events)
    for start in range(0, k, block):
        values = events[start : start + block]
        if len(values) > 1:
            widths.append(max(1, int(math.ceil(math.log2(int(np.diff(values).max()) + 1)))))
        else:
            widths.append(1)
        # One absolute base plus at most eight reconstructed events per cycle.
        event_cycles += math.ceil(len(values) / 8)
    return header_cycles + event_cycles, widths


def _lpt_cycles(jobs: list[int], lanes: int = 32) -> int:
    load = [0] * lanes
    for job in sorted(jobs, reverse=True):
        lane = min(range(lanes), key=lambda i: (load[i], i))
        load[lane] += job
    return max(load, default=0)


def _fixed_gap8_bits(code) -> tuple[int, int]:
    """Hardware-friendly exact code: dense, fixed IDs, or <=32-event gap8 blocks."""
    events = np.asarray(code.events, dtype=np.int64)
    universe = int(code.universe)
    count_bits = max(1, math.ceil(math.log2(universe + 1)))
    id_bits = max(1, math.ceil(math.log2(max(universe, 2))))
    dense = 2 + universe
    fixed = 2 + count_bits + len(events) * id_bits
    # Start a new independently dispatchable block on a >8-bit gap or at 32
    # events. Each block carries an absolute ID and a five-bit event count.
    blocks: list[np.ndarray] = []
    start = 0
    for i in range(1, len(events)):
        if i - start >= 32 or events[i] - events[i - 1] > 255:
            blocks.append(events[start:i])
            start = i
    if len(events):
        blocks.append(events[start:])
    gap8 = 2 + 2 + count_bits + 8  # format, block selector/count, event count
    gap8 += sum(id_bits + 5 + 8 * max(0, len(block) - 1) for block in blocks)
    selected = min((dense, "dense"), (fixed, "fixed"), (gap8, "gap8"))
    bits, fmt = selected
    if fmt == "dense":
        cycles = math.ceil(universe / 64)
    elif fmt == "fixed":
        cycles = math.ceil(len(events) / 4)
    else:
        cycles = sum(math.ceil(len(block) / 8) for block in blocks)
    # Header parsing overlaps the bit reservoir; encoded bits remain the hard
    # lower throughput bound at the bank input.
    return int(bits), int(cycles)


def main() -> None:
    summary = pd.read_csv(ROOT / "results_final8/48_final8_summary.csv")
    datasets = {
        "cora_gcnii16": "Cora",
        "pubmed_gcnii16": "PubMed",
        "cora_deepres28_w128": "Cora",
        "chameleon_gcnii16": "chameleon",
    }
    rows = []
    for cid, dataset_name in datasets.items():
        masks = _unpack(ROOT / f"artifacts_final8/masks/{cid}_fp8_supports.npz")
        width = min(
            masks.shape[2],
            int(summary.loc[summary.config_id == cid, "best_slice_width"].iloc[0]),
        )
        segment = masks[3:]
        data, _, _ = load_dataset(dataset_name, ROOT / "data")
        _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(rcm, 128)
        jobs_by_layer: list[list[int]] = [[] for _ in range(len(segment))]
        bits_by_layer = np.zeros(len(segment), dtype=np.int64)
        formats: dict[str, int] = {}
        format_bits: dict[str, int] = {}
        gap_widths: list[int] = []
        constrained_bits_by_layer = np.zeros(len(segment), dtype=np.int64)
        constrained_event_work_by_layer = np.zeros(len(segment), dtype=np.int64)
        constrained_aligned_by_layer = np.zeros(len(segment), dtype=np.int64)
        constrained_anchor_bits = 0
        original_anchor_bits = 0
        exact = True
        for tile in tiles:
            local = segment[:, tile, :]
            for start in range(0, masks.shape[2], width):
                enc = encode_slice(local, start, min(width, masks.shape[2] - start))
                exact &= bool(enc["exact"])
                _, _, hardware_anchor_bits = select_hardware_dictionary(enc["anchor"])
                constrained_anchor_bits += align64(
                    math.ceil(hardware_anchor_bits / 8)
                ) * 8
                original_anchor_bits += align64(
                    math.ceil(enc["anchor_bits"] / 8)
                ) * 8
                for layer, code in enumerate(enc["codes"]):
                    cycles, widths = _code_cycles(code)
                    jobs_by_layer[layer].append(cycles)
                    bits_by_layer[layer] += code.encoded_bits
                    formats[code.selected_format] = formats.get(code.selected_format, 0) + 1
                    format_bits[code.selected_format] = (
                        format_bits.get(code.selected_format, 0) + code.encoded_bits
                    )
                    gap_widths.extend(widths)
                    fixed_bits, fixed_work = _fixed_gap8_bits(code)
                    constrained_bits_by_layer[layer] += fixed_bits
                    constrained_event_work_by_layer[layer] += fixed_work
                    constrained_aligned_by_layer[layer] += align64(
                        math.ceil(fixed_bits / 8)
                    ) * 8
        actual = sum(_lpt_cycles(jobs) for jobs in jobs_by_layer)
        ideal = sum(math.ceil(int(bits) / 2048) for bits in bits_by_layer)
        total_bits = int(bits_by_layer.sum())
        constrained_bits = int(constrained_bits_by_layer.sum())
        constrained_cycles = sum(
            max(
                math.ceil(int(bits) / 2048),
                math.ceil(int(work) / 32),
            )
            for bits, work in zip(
                constrained_bits_by_layer, constrained_event_work_by_layer
            )
        )
        rows.append(
            {
                "config_id": cid,
                "slice_width": width,
                "exception_streams": sum(len(x) for x in jobs_by_layer),
                "exception_bits": total_bits,
                "ideal_2048bit_cycles": ideal,
                "format_aware_32lane_cycles": actual,
                "decoder_efficiency": ideal / max(actual, 1),
                "effective_bits_per_cycle": total_bits / max(actual, 1),
                "fixed_gap8_exception_bits": constrained_bits,
                "fixed_gap8_bit_inflation": constrained_bits / max(total_bits, 1),
                "fixed_gap8_32lane_cycles": constrained_cycles,
                "fixed_gap8_effective_bits_per_cycle": constrained_bits
                / max(constrained_cycles, 1),
                "fixed_gap8_aligned_exception_bits": int(
                    constrained_aligned_by_layer.sum()
                ),
                "fixed_gap8_aligned_anchor_bits": constrained_anchor_bits,
                "original_aligned_anchor_bits": original_anchor_bits,
                "dense_stream_fraction": formats.get("DENSE_XOR", 0)
                / max(sum(formats.values()), 1),
                "fixed_stream_fraction": formats.get("FIXED_IDS", 0)
                / max(sum(formats.values()), 1),
                "gap_stream_fraction": formats.get("BLOCK_FOR_GAPS", 0)
                / max(sum(formats.values()), 1),
                "dense_bit_fraction": format_bits.get("DENSE_XOR", 0)
                / max(total_bits, 1),
                "gap_width_p50": float(np.median(gap_widths)) if gap_widths else 0,
                "gap_width_p90": float(np.percentile(gap_widths, 90)) if gap_widths else 0,
                "gap_width_max": max(gap_widths, default=0),
                "exact_decode_pass": exact,
            }
        )
        safe_artifacts = ROOT / "artifacts_safezone/streams"
        safe_artifacts.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            safe_artifacts / f"{cid}_fixed_gap8.npz",
            layer_bits=constrained_aligned_by_layer,
            anchor_bits=np.asarray([constrained_anchor_bits], dtype=np.int64),
        )
    out = ROOT / "results_safezone"
    out.mkdir(exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(out / "50_decoder_stream_audit.csv", index=False)
    print(frame.to_string(index=False))


if __name__ == "__main__":
    main()
