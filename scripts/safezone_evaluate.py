#!/usr/bin/env python3
"""Recalculate headline cycles using the exact fixed-gap8 hardware stream."""
from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    traffic = pd.read_csv(ROOT / "results_final8/46_fp8_cache_traffic.csv")
    old_summary = pd.read_csv(ROOT / "results_final8/48_final8_summary.csv").set_index("config_id")
    rows = []
    summaries = []
    for cid in old_summary.index:
        support = np.load(ROOT / f"artifacts_safezone/streams/{cid}_fixed_gap8.npz")
        anchor_bits = int(support["anchor_bits"][0])
        layer_bits = support["layer_bits"]
        xor_width = min(
            int(old_summary.loc[cid, "best_slice_width"]),
            128 if "deepres" in cid else 64,
        )
        for cache_bytes in (256 * 1024, 512 * 1024, 1024 * 1024):
            scope = traffic[
                (traffic.config_id == cid)
                & (traffic.edge_order == "O0")
                & (traffic.feature_cache_bytes == cache_bytes)
            ]
            beicsr = float(
                scope[scope.format == "beicsr"]
                .groupby("slice_width").serialized_cycles.sum().min()
            )
            for bandwidth in (128, 256, 512):
                for decoder_width in (1024, 2048, 4096):
                    candidate_cycles = []
                    for physical_width, xrows in scope[
                        (scope.format == "xorflow")
                        & (scope.slice_width >= xor_width)
                    ].groupby("slice_width"):
                        cycles = 0
                        total_dram = 0
                        total_decode = 0
                        for row in xrows.itertuples():
                            offset = int(row.layer_id) - 4
                            metadata = (
                                anchor_bits // max(len(xrows), 1)
                                + int(layer_bits[offset])
                            ) // 8
                            dram = int(row.total_dram_bytes - row.metadata_dram_bytes + metadata)
                            decode = math.ceil(metadata * 8 / decoder_width)
                            cycles += math.ceil(dram / bandwidth) + decode + int(row.descriptor_cycles)
                            total_dram += dram
                            total_decode += decode
                        candidate_cycles.append(
                            (cycles, int(physical_width), total_dram, total_decode)
                        )
                    cycles, physical_width, total_dram, total_decode = min(candidate_cycles)
                    # Recompute the BEICSR reference at the same bandwidth.
                    bcycles = []
                    for _, group in scope[scope.format == "beicsr"].groupby("slice_width"):
                        bcycles.append(sum(
                            math.ceil(int(r.total_dram_bytes) / bandwidth)
                            + int(r.descriptor_cycles)
                            for r in group.itertuples()
                        ))
                    baseline = min(bcycles)
                    raw = baseline / cycles
                    rows.append({
                        "config_id": cid,
                        "feature_cache_bytes": cache_bytes,
                        "dram_bytes_per_cycle": bandwidth,
                        "aggregate_decode_width_bits": decoder_width,
                        "physical_slice_width": physical_width,
                        "fixed_gap8_xorflow_cycles": cycles,
                        "best_beicsr_cycles": baseline,
                        "raw_xorflow_speedup": raw,
                        "selected_speedup": max(1.0, raw),
                        "selected_representation": "XORFLOW" if raw > 1 else "BEICSR",
                        "xorflow_dram_bytes": total_dram,
                        "xorflow_decode_cycles": total_decode,
                    })
        principal = rows[-27:]
        headline = next(
            row for row in principal
            if row["feature_cache_bytes"] == 512 * 1024
            and row["dram_bytes_per_cycle"] == 256
            and row["aggregate_decode_width_bits"] == 2048
        )
        summaries.append({
            "config_id": cid,
            "fixed_gap8_support_bits": anchor_bits + int(layer_bits.sum()),
            "support_ratio_to_beicsr": (
                anchor_bits + int(layer_bits.sum())
            ) / float(
                pd.read_csv(ROOT / "results_final8/45_fp8_format_metadata.csv")
                .query("config_id == @cid and slice_width == @xor_width")
                .beicsr_support_bits.iloc[0]
            ),
            "raw_serialized_speedup": headline["raw_xorflow_speedup"],
            "selected_speedup": headline["selected_speedup"],
            "selected_representation": headline["selected_representation"],
            "accuracy_drop": float(old_summary.loc[cid, "test_accuracy_drop"]),
            "exactness_pass": bool(old_summary.loc[cid, "exactness_pass"]),
        })
    out = ROOT / "results_safezone"
    sensitivity = pd.DataFrame(rows)
    summary = pd.DataFrame(summaries)
    sensitivity.to_csv(out / "51_hardware_format_sensitivity.csv", index=False)
    summary.to_csv(out / "52_safezone_summary.csv", index=False)
    idx = summary.set_index("config_id")
    gm = math.sqrt(idx.loc["cora_gcnii16", "selected_speedup"]
                   * idx.loc["pubmed_gcnii16", "selected_speedup"])
    print(summary.to_string(index=False))
    print(f"principal_geomean={gm:.6f}")
    hashes = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(out.glob("*.csv"))
    }
    (out / "hashes.json").write_text(
        __import__("json").dumps(hashes, indent=2, sort_keys=True)
    )


if __name__ == "__main__":
    main()
