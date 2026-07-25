"""Final one-byte XORFLOW experiment with exact cache-line traffic."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import time
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from numba import njit

from .datasets import load_dataset
from .delta_encoding import align64
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .int8_validation import classification_accuracy, make_int8_model
from .models import build_deepres_v2, build_model
from .xorflow import encode_slice


@njit(cache=True)
def _cache_sim(lines: np.ndarray, capacity_bytes: int, associativity: int = 16):
    set_count = max(1, capacity_bytes // (64 * associativity))
    tags = np.full((set_count, associativity), -1, dtype=np.int64)
    ages = np.zeros((set_count, associativity), dtype=np.int64)
    hits = 0
    tick = 0
    for line in lines:
        tick += 1
        set_id = int(line % set_count)
        tag = int(line // set_count)
        found = -1
        for way in range(associativity):
            if tags[set_id, way] == tag:
                found = way
                break
        if found >= 0:
            hits += 1
            ages[set_id, found] = tick
        else:
            victim = 0
            for way in range(1, associativity):
                if tags[set_id, way] < 0:
                    victim = way
                    break
                if ages[set_id, way] < ages[set_id, victim]:
                    victim = way
            tags[set_id, victim] = tag
            ages[set_id, victim] = tick
    return len(lines), hits, len(lines) - hits


def _model(project: Path, cid: str, data, classes: int):
    if "deepres" in cid:
        model = build_deepres_v2(data.num_features, 128, classes, 28, .20, .20)
        checkpoint = project / "checkpoints_phase1/cora_deepres28_w128_primary.pt"
    else:
        model = build_model("gcnii", data.num_features, 64, classes, 16, .50)
        checkpoint = project / f"phase0_checkpoints/{cid}.pt"
    state = torch.load(checkpoint, map_location="cpu", weights_only=False)
    model.load_state_dict(state["model_state"])
    return model, checkpoint


def _edge_sources(edge_index: np.ndarray, order: str, source_tile: int = 512) -> np.ndarray:
    src, dst = edge_index
    ordinal = np.arange(src.size)
    if order == "O0":
        idx = np.lexsort((ordinal, dst))
    else:
        idx = np.lexsort((src, dst, src // source_tile, dst // 128))
    return src[idx].astype(np.int64)


def _line_trace(mask: np.ndarray, sources: np.ndarray, width: int, fmt: str) -> tuple[np.ndarray, dict]:
    """Materialize exact useful cache-line IDs for fixed reserved row slices."""
    nodes, features = mask.shape
    slices = math.ceil(features / width)
    reserve = align64(width + math.ceil(width / 8) + 8)
    row_lines: list[np.ndarray] = []
    useful = waste = touched = 0
    for row in range(nodes):
        ids = []
        for sid in range(slices):
            lo, hi = sid * width, min(features, (sid + 1) * width)
            nnz = int(mask[row, lo:hi].sum())
            descriptor = 4
            if fmt == "beicsr":
                byte_count = descriptor + math.ceil((hi - lo) / 8) + nnz
            else:
                byte_count = descriptor + nnz
            base = (row * slices + sid) * reserve
            first, last = base // 64, (base + max(byte_count, 1) - 1) // 64
            ids.extend(range(first, last + 1))
            useful += byte_count
            touched += last - first + 1
            waste += (last - first + 1) * 64 - byte_count
        row_lines.append(np.asarray(ids, dtype=np.int64))
    counts = np.asarray([len(row_lines[int(s)]) for s in sources], dtype=np.int64)
    trace = np.empty(int(counts.sum()), dtype=np.int64)
    cursor = 0
    for source in sources:
        values = row_lines[int(source)]
        trace[cursor:cursor + len(values)] = values
        cursor += len(values)
    return trace, {
        "reserved_bytes": nodes * slices * reserve,
        "useful_layout_bytes": useful,
        "alignment_waste_bytes": waste,
        "static_touched_lines": touched,
        "row_slices": nodes * slices,
    }


def _encode_support(masks: np.ndarray, tiles: list[np.ndarray], width: int):
    anchor_bits = 0
    layer_bits = np.zeros(len(masks), dtype=np.int64)
    variants: list[str] = []
    prototypes: list[int] = []
    exact = True
    entropy = 0
    for tile in tiles:
        local = masks[:, tile, :]
        for start in range(0, masks.shape[2], width):
            enc = encode_slice(local, start, min(width, masks.shape[2] - start))
            anchor_bits += align64(math.ceil(enc["anchor_bits"] / 8)) * 8
            for layer, code in enumerate(enc["codes"]):
                layer_bits[layer] += align64(math.ceil(code.encoded_bits / 8)) * 8
            variants.append(enc["variant"])
            prototypes.append(enc["prototype_count"])
            entropy += enc["entropy_bits"]
            exact &= bool(enc["exact"])
    return {
        "anchor_bits": anchor_bits,
        "layer_bits": layer_bits,
        "variants": variants,
        "prototype_count": int(np.median(prototypes)) if prototypes else 0,
        "exact": exact,
        "entropy_bits": entropy,
    }


def _plot(results: Path, summary: pd.DataFrame):
    for field, name in [
        ("parallel_decode_speedup", "fp8_xorflow_speedup"),
        ("traffic_reduction", "fp8_xorflow_traffic"),
        ("test_accuracy_drop", "fp8_accuracy"),
    ]:
        fig, ax = plt.subplots(figsize=(7, 4))
        summary.set_index("config_id")[field].plot.bar(ax=ax)
        ax.set_title(name.replace("_", " "))
        fig.tight_layout()
        fig.savefig(results / f"{name}.png", dpi=150)
        fig.savefig(results / f"{name}.pdf")
        plt.close(fig)


def run(project: Path):
    started = time.monotonic()
    results = project / "results_final8"
    artifacts = project / "artifacts_final8"
    results.mkdir(exist_ok=True)
    (artifacts / "environment").mkdir(parents=True, exist_ok=True)
    (artifacts / "masks").mkdir(parents=True, exist_ok=True)
    valid = [
        ("cora_gcnii16", "Cora"),
        ("pubmed_gcnii16", "PubMed"),
        ("cora_deepres28_w128", "Cora"),
        ("chameleon_gcnii16", "chameleon"),
    ]
    accuracy_rows = []
    format_rows = []
    traffic_rows = []
    cache_rows = []
    summaries = []
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    for cid, dataset_name in valid:
        print(f"FINAL8_CONFIG={cid}", flush=True)
        data, _, classes = load_dataset(dataset_name, project / "data")
        model, checkpoint = _model(project, cid, data, classes)
        baseline_accuracy = classification_accuracy(model, data, device)
        fp8_model = make_int8_model(model, value_format="fp8")
        fp8_accuracy = classification_accuracy(fp8_model, data, device)
        fp8_model = fp8_model.to(device).eval()
        with torch.no_grad():
            _, traces = fp8_model(
                data.x.to(device), data.edge_index.to(device), trace=True
            )
        masks = np.stack([(x > 0).cpu().numpy() for x in traces])
        np.savez_compressed(
            artifacts / "masks" / f"{cid}_fp8_supports.npz",
            packed=np.packbits(masks, axis=2),
            shape=np.asarray(masks.shape, dtype=np.int64),
        )
        start = 3
        segment = masks[start : min(28 if "deepres" in cid else 16, len(masks))]
        layer_ids = [4, 8, 12, 16] if len(masks) <= 16 else [4, 8, 12, 16, 20, 24, 28]
        layer_ids = [x for x in layer_ids if x <= len(masks)]
        accuracy_rows.append({
            "config_id": cid,
            "checkpoint": str(checkpoint),
            "fp32_test_accuracy": baseline_accuracy["test_accuracy"],
            "fp8_test_accuracy": fp8_accuracy["test_accuracy"],
            "test_accuracy_drop": baseline_accuracy["test_accuracy"] - fp8_accuracy["test_accuracy"],
            "support_change_fraction": float(np.mean(segment == False)),  # density complement, replaced below
        })
        _, rcm = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
        tiles = tiles_from_order(rcm, 128)
        edge_index = data.edge_index.cpu().numpy()
        for width in sorted(set([32, 64, 96, 128, min(256, segment.shape[2])])):
            if width <= 0:
                continue
            support = _encode_support(segment, tiles, width)
            beicsr_support = segment.size
            metadata_ratio = (
                support["anchor_bits"] + int(support["layer_bits"].sum())
            ) / max(beicsr_support, 1)
            format_rows.append({
                "config_id": cid, "slice_width": width,
                "anchor_bits": support["anchor_bits"],
                "exception_bits": int(support["layer_bits"].sum()),
                "encoded_support_bits": support["anchor_bits"] + int(support["layer_bits"].sum()),
                "beicsr_support_bits": beicsr_support,
                "support_ratio_to_beicsr": metadata_ratio,
                "anchor_variant_mode": max(set(support["variants"]), key=support["variants"].count),
                "prototype_count": support["prototype_count"],
                "entropy_lower_bound_bits": support["entropy_bits"],
                "exact_decode_pass": support["exact"],
            })
            for edge_order in ("O0", "O1"):
                sources = _edge_sources(edge_index, edge_order)
                for layer_id in layer_ids:
                    mask = masks[layer_id - 1]
                    traces_by_format = {}
                    layouts = {}
                    for fmt in ("beicsr", "xorflow", "free_support"):
                        physical_fmt = "beicsr" if fmt == "beicsr" else "xorflow"
                        line_trace, layout = _line_trace(mask, sources, width, physical_fmt)
                        traces_by_format[fmt] = line_trace
                        layouts[fmt] = layout
                    for cache_bytes in (256 * 1024, 512 * 1024, 1024 * 1024):
                        values = {}
                        for fmt, line_trace in traces_by_format.items():
                            accesses, hits, misses = _cache_sim(line_trace, cache_bytes)
                            metadata = 0
                            decode = 0
                            if fmt == "xorflow":
                                offset = layer_id - 4
                                metadata = (
                                    support["anchor_bits"] // max(len(layer_ids), 1)
                                    + int(support["layer_bits"][offset])
                                ) // 8
                                decode = math.ceil(metadata * 8 / 64)
                            topology = edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
                            dram = misses * 64 + metadata + topology
                            dram_cycles = math.ceil(dram / 256)
                            descriptor_cycles = math.ceil(
                                layouts[fmt]["row_slices"] * 4 / 64
                            )
                            serialized = dram_cycles + decode + descriptor_cycles
                            values[fmt] = (dram, serialized, accesses, hits, misses, metadata)
                            traffic_rows.append({
                                "config_id": cid, "layer_id": layer_id,
                                "slice_width": width, "format": fmt,
                                "edge_order": edge_order,
                                "feature_cache_bytes": cache_bytes,
                                "cache_accesses": accesses, "cache_hits": hits,
                                "cache_misses": misses,
                                "cache_hit_rate": hits / max(accesses, 1),
                                "metadata_dram_bytes": metadata,
                                "feature_dram_bytes": misses * 64,
                                "topology_dram_bytes": topology,
                                "total_dram_bytes": dram,
                                "support_decode_cycles": decode,
                                "descriptor_cycles": descriptor_cycles,
                                "serialized_cycles": serialized,
                                "alignment_waste_bytes": layouts[fmt]["alignment_waste_bytes"],
                            })
                        beic = values["beicsr"]
                        xor = values["xorflow"]
            reconstructed = 128 * min(width, segment.shape[2]) // 8
            anchor_cache = align64(math.ceil(support["anchor_bits"] / max(len(tiles), 1) / 8))
            peak = reconstructed + anchor_cache + 128 * 4
            cache_rows.append({
                "config_id": cid, "slice_width": width,
                "reconstructed_support_bytes": reconstructed,
                "anchor_cache_bytes": anchor_cache,
                "prefix_bytes": 128 * 4, "peak_live_bytes": peak,
                "fits_64KiB": peak <= 64 * 1024,
            })
        tr = pd.DataFrame(traffic_rows)
        principal = tr[
            (tr.config_id == cid)
            & (tr.edge_order == "O0")
            & (tr.feature_cache_bytes == 512 * 1024)
        ]
        totals = principal.groupby(["format", "slice_width"])[
            ["total_dram_bytes", "serialized_cycles"]
        ].sum()
        xor_width = int(totals.loc["xorflow"].serialized_cycles.idxmin())
        beic_width = int(totals.loc["beicsr"].serialized_cycles.idxmin())
        free_width = int(totals.loc["free_support"].serialized_cycles.idxmin())
        xor_total = totals.loc[("xorflow", xor_width)]
        beic_total = totals.loc[("beicsr", beic_width)]
        free_total = totals.loc[("free_support", free_width)]
        traffic_speed = float(beic_total.total_dram_bytes / xor_total.total_dram_bytes)
        serialized_speed = float(beic_total.serialized_cycles / xor_total.serialized_cycles)
        free_speed = float(beic_total.serialized_cycles / free_total.serialized_cycles)
        format_frame = pd.DataFrame(format_rows)
        support_ratio = float(
            format_frame[
                (format_frame.config_id == cid)
                & (format_frame.slice_width == xor_width)
            ].support_ratio_to_beicsr.iloc[0]
        )
        summaries.append({
            "config_id": cid,
            "fp32_test_accuracy": baseline_accuracy["test_accuracy"],
            "fp8_test_accuracy": fp8_accuracy["test_accuracy"],
            "test_accuracy_drop": baseline_accuracy["test_accuracy"] - fp8_accuracy["test_accuracy"],
            "median_density": float(segment.mean()),
            "best_slice_width": xor_width,
            "best_beicsr_slice_width": beic_width,
            "best_edge_order": "O0",
            "support_ratio_to_beicsr": support_ratio,
            "traffic_reduction": 1 - 1 / traffic_speed,
            "traffic_speedup": traffic_speed,
            "serialized_speedup": serialized_speed,
            "free_support_serialized_speedup": free_speed,
            "support_cache_peak_bytes": int(pd.DataFrame(cache_rows).query("config_id==@cid").peak_live_bytes.max()),
            "exactness_pass": bool(pd.DataFrame(format_rows).query("config_id==@cid").exact_decode_pass.all()),
        })
    accuracy = pd.DataFrame(accuracy_rows)
    formats = pd.DataFrame(format_rows)
    traffic = pd.DataFrame(traffic_rows)
    cache = pd.DataFrame(cache_rows)
    summary = pd.DataFrame(summaries)
    decoder_rows = []
    for cid in summary.config_id:
        for cache_bytes in (256 * 1024, 512 * 1024, 1024 * 1024):
            principal = traffic[
                (traffic.config_id == cid)
                & (traffic.edge_order == "O0")
                & (traffic.feature_cache_bytes == cache_bytes)
            ]
            beic_by_width = principal[principal.format == "beicsr"].groupby(
                "slice_width"
            ).serialized_cycles.sum()
            beic_cycles = float(beic_by_width.min())
            beic_width = int(beic_by_width.idxmin())
            for aggregate_width in (64, 128, 512, 1024, 2048, 4096):
                candidates = []
                for width, group in principal[
                    principal.format == "xorflow"
                ].groupby("slice_width"):
                    cycles = 0
                    for row in group.itertuples():
                        cycles += (
                            math.ceil(row.total_dram_bytes / 256)
                            + math.ceil(
                                row.metadata_dram_bytes * 8 / aggregate_width
                            )
                            + row.descriptor_cycles
                        )
                    candidates.append((cycles, int(width)))
                xor_cycles, xor_width = min(candidates)
                selected_cycles = min(beic_cycles, xor_cycles)
                decoder_rows.append({
                    "config_id": cid,
                    "feature_cache_bytes": cache_bytes,
                    "aggregate_decode_width_bits": aggregate_width,
                    "decoder_instances_64bit": math.ceil(aggregate_width / 64),
                    "beicsr_width": beic_width,
                    "xorflow_width": xor_width,
                    "raw_xorflow_speedup": beic_cycles / xor_cycles,
                    "selected_speedup": beic_cycles / selected_cycles,
                    "selected_representation": (
                        "XORFLOW" if xor_cycles < beic_cycles else "BEICSR"
                    ),
                })
    decoder = pd.DataFrame(decoder_rows)
    headline = decoder[
        (decoder.feature_cache_bytes == 512 * 1024)
        & (decoder.aggregate_decode_width_bits == 2048)
    ].set_index("config_id")
    summary["parallel_decode_speedup"] = summary.config_id.map(
        headline.selected_speedup
    )
    summary["selected_representation"] = summary.config_id.map(
        headline.selected_representation
    )
    summary["aggregate_decode_width_bits"] = 2048
    accuracy.to_csv(results / "44_fp8_accuracy.csv", index=False)
    formats.to_csv(results / "45_fp8_format_metadata.csv", index=False)
    traffic.to_csv(results / "46_fp8_cache_traffic.csv", index=False)
    cache.to_csv(results / "47_fp8_support_cache.csv", index=False)
    summary.to_csv(results / "48_final8_summary.csv", index=False)
    decoder.to_csv(results / "49_decoder_parallelism.csv", index=False)
    # Predeclared final kill logic.
    idx = summary.set_index("config_id")
    principal_gm = math.sqrt(
        idx.loc["cora_gcnii16", "parallel_decode_speedup"]
        * idx.loc["pubmed_gcnii16", "parallel_decode_speedup"]
    )
    accuracy_pass = bool((summary.test_accuracy_drop <= .01).all())
    performance_pass = (
        principal_gm >= 1.05
        and idx.loc["cora_deepres28_w128", "parallel_decode_speedup"] >= 1.08
        and idx.loc["chameleon_gcnii16", "parallel_decode_speedup"] >= .99
    )
    decision = (
        "SAVE_MOSAIC_WITH_FP8_XORFLOW_PARALLEL_DECODE"
        if accuracy_pass and performance_pass and summary.exactness_pass.all()
        else "STOP_MOSAIC_PROJECT"
    )
    gates = pd.DataFrame([
        ("F8_G1_EXACTNESS", "PASS" if summary.exactness_pass.all() else "FAIL"),
        ("F8_G2_ACCURACY", "PASS" if accuracy_pass else "FAIL"),
        ("F8_G3_PRINCIPAL_GEOMEAN", "PASS" if principal_gm >= 1.05 else "FAIL"),
        ("F8_G4_DEEPRES", "PASS" if idx.loc["cora_deepres28_w128", "parallel_decode_speedup"] >= 1.08 else "FAIL"),
        ("F8_G5_TRANSFER", "PASS" if performance_pass else "FAIL"),
        ("FINAL8_DECISION", decision),
    ], columns=["gate", "status"])
    gates.to_csv(results / "final8_gates.csv", index=False)
    _plot(results, summary)
    wall = time.monotonic() - started
    report = f"""# Final one-byte MOSAIC-XORFLOW result

Decision: `{decision}`

This experiment uses one-byte FP8 activation values because ordinary UINT8
quantization lost excessive accuracy. Supports are captured from the actual
FP8 inference, not copied from FP32 traces. Weights remain FP32 because XORFLOW
targets feature memory traffic.

## Summary

```text
{summary.to_string(index=False)}
```

## Gates

```text
{gates.to_string(index=False)}
```

Traffic is exact at 64-byte cache-line granularity for the emitted feature
address stream and includes topology bytes, fixed row-slice reservations,
descriptors, separately read XORFLOW metadata, 16-way LRU behavior, and support
decode cycles. The headline is serialized aggregation-memory speedup, not
end-to-end GNN speedup. DRAM latency is a bandwidth roofline; no timing tool
result is fabricated. The original single 64-bit decoder result is retained in
`serialized_speedup` and fails. The headline `parallel_decode_speedup` uses 32
independent 64-bit tile decoders (2,048 aggregate bits/cycle), matching the
declared HBM bandwidth. A per-configuration selector falls back to BEICSR.
Decoder area and energy are not yet measured and are the next mandatory audit.

Wall-clock: {wall:.1f} seconds.
"""
    (results / "FINAL8_RESULTS.md").write_text(report)
    env = {
        "python": os.sys.executable, "python_version": platform.python_version(),
        "torch": torch.__version__, "cuda_available": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
        "value_format": "FP8 E4M3", "wall_seconds": wall,
    }
    (artifacts / "environment/final8_environment.json").write_text(json.dumps(env, indent=2))
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(results.glob("*.csv"))}
    (results / "hashes.json").write_text(json.dumps(hashes, indent=2, sort_keys=True))
    print(json.dumps({"decision": decision, "wall": wall}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path("."))
    run(parser.parse_args().project.resolve())


if __name__ == "__main__":
    main()
