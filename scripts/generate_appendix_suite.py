#!/usr/bin/env python3
"""Build the deterministic XORFLOW reviewer appendix from frozen artifacts.

The script never trains a model or rewrites an earlier result.  Every numerical
panel is backed by a CSV emitted by the corrected reviewer campaign.  Older
host-model sensitivity files are used only for exact byte/cache-line evidence;
they are never presented as corrected finite-queue cycle results.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import OrderedDict
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"
COMPLETE = ROOT / "results_hpca_xorflow" / "complete_suite"
OUT = ROOT / "results_hpca_xorflow" / "appendix"
FIG = OUT / "figures"
TAB = OUT / "tables"
PRIMARY = [
    "ogbn_arxiv_deepres8_w128_s7",
    "ogbn_arxiv_deepres8_w128_s17",
    "ogbn_arxiv_deepres8_w128_s27",
    "reddit_deepres8_w128_s7_native",
    "reddit_deepres8_w128_s17_native",
    "reddit_deepres8_w128_s27_native",
    "yelp_deepres8_w128_s7_balanced_fallback",
]
FORMAT_ORDER = ["BEICSR", "A0", "A2", "DELTA"]


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _short(run_id: str) -> str:
    text = run_id.replace("ogbn_arxiv", "Arxiv").replace("deepres", "DR")
    text = text.replace("_native", "").replace("_balanced_fallback", "")
    text = text.replace("graphsage", "SAGE").replace("gcnii", "GCNII")
    return text.replace("_", " ")


def _write(df: pd.DataFrame, name: str) -> Path:
    path = TAB / name
    df.to_csv(path, index=False, lineterminator="\n")
    return path


def _save(fig: plt.Figure, stem: str) -> None:
    fig.tight_layout()
    fig.savefig(FIG / f"{stem}.png", dpi=220, bbox_inches="tight")
    # Suppress wall-clock PDF metadata so cached reruns are byte reproducible.
    fig.savefig(FIG / f"{stem}.pdf", bbox_inches="tight",
                metadata={"Creator": "XORFLOW appendix generator", "CreationDate": None, "ModDate": None})
    plt.close(fig)


def _heatmap(
    ax: plt.Axes, data: np.ndarray, rows: list[str], cols: list[str], title: str,
    *, cmap: str = "viridis", fmt: str = ".2f", center: float | None = None,
) -> None:
    masked = np.ma.masked_invalid(np.asarray(data, dtype=float))
    palette = plt.get_cmap(cmap).copy()
    palette.set_bad("#d9d9d9")
    if center is None:
        image = ax.imshow(masked, aspect="auto", cmap=palette)
    else:
        bound = max(abs(np.nanmin(data) - center), abs(np.nanmax(data) - center))
        image = ax.imshow(masked, aspect="auto", cmap=palette, vmin=center - bound, vmax=center + bound)
    ax.set_xticks(range(len(cols)), cols, rotation=45, ha="right")
    ax.set_yticks(range(len(rows)), rows)
    ax.set_title(title)
    if len(rows) * len(cols) <= 160:
        for i in range(len(rows)):
            for j in range(len(cols)):
                value = data[i, j]
                ax.text(j, i, "—" if not np.isfinite(value) else format(value, fmt),
                        ha="center", va="center", fontsize=6)
    plt.colorbar(image, ax=ax, fraction=.035, pad=.02)


def _pivot(df: pd.DataFrame, row: str, col: str, value: str, rows: list, cols: list) -> np.ndarray:
    table = df.pivot_table(index=row, columns=col, values=value, aggfunc="median")
    return table.reindex(index=rows, columns=cols).to_numpy(dtype=float)


def persistence_and_controls() -> list[Path]:
    source = V3 / "characterization" / "adjacent_support.csv"
    use = ["run_id", "layer", "target_layer", "control_type", "xor_density",
           "jaccard_similarity", "delta_bytes", "beicsr_target_bytes", "fallback"]
    data = pd.read_csv(source, usecols=use)
    data["metadata_ratio"] = data["delta_bytes"] / data["beicsr_target_bytes"].replace(0, np.nan)
    real = data[data.control_type == "real_adjacent"]
    layer = real.groupby(["run_id", "target_layer"], as_index=False).agg(
        jaccard=("jaccard_similarity", "median"), xor_density=("xor_density", "median"),
        metadata_ratio=("metadata_ratio", "median"), fallback_fraction=("fallback", "mean"),
    )
    p1 = _write(layer, "A1_layerwise_persistence.csv")
    runs = sorted(layer.run_id.unique())
    layers = sorted(layer.target_layer.unique())
    fig, axes = plt.subplots(1, 3, figsize=(18, max(6, .27 * len(runs))))
    for ax, metric, title, cmap in zip(
        axes, ["jaccard", "xor_density", "metadata_ratio"],
        ["Adjacent support Jaccard", "XOR exception density", "Delta/BEICSR metadata"],
        ["YlGn", "magma_r", "viridis_r"],
    ):
        _heatmap(ax, _pivot(layer, "run_id", "target_layer", metric, runs, layers),
                 [_short(x) for x in runs], [str(x) for x in layers], title, cmap=cmap)
    fig.suptitle("A1. Layerwise support persistence (median over topology tiles/slices)")
    _save(fig, "A1_layerwise_persistence")

    controls = data.groupby(["run_id", "control_type"], as_index=False).agg(
        jaccard=("jaccard_similarity", "median"), exception_density=("xor_density", "median"),
        metadata_ratio=("metadata_ratio", "median"), fallback_fraction=("fallback", "mean"),
    )
    p2 = _write(controls, "A2_learned_structure_controls.csv")
    control_order = ["real_adjacent", "exact_count_independent", "row_permutation",
                     "feature_permutation", "nonadjacent_l_plus_2"]
    shown = [x for x in PRIMARY if x in set(controls.run_id)]
    fig, axes = plt.subplots(1, 3, figsize=(17, max(4, .55 * len(shown))))
    for ax, metric, title, cmap in zip(
        axes, ["jaccard", "exception_density", "metadata_ratio"],
        ["Support Jaccard", "Exception density", "Metadata ratio"],
        ["YlGn", "magma_r", "viridis_r"],
    ):
        _heatmap(ax, _pivot(controls, "run_id", "control_type", metric, shown, control_order),
                 [_short(x) for x in shown], [x.replace("_", "\n") for x in control_order], title, cmap=cmap)
    fig.suptitle("A2. Learned-structure controls at matched support counts")
    _save(fig, "A2_learned_structure_controls")
    return [source, p1, p2]


def format_map() -> list[Path]:
    chunks: list[pd.DataFrame] = []
    for path in sorted((V3 / "online_replay").glob("support_records_*_reread.csv")):
        df = pd.read_csv(path, usecols=["run_id", "layer", "role", "chosen_format", "padded_bytes", "anchor_read_bytes"])
        chunks.append(df)
    raw = pd.concat(chunks, ignore_index=True)
    grouped = raw.groupby(["run_id", "layer", "chosen_format"], as_index=False).agg(
        records=("role", "size"), physical_support_bytes=("padded_bytes", "sum"),
        anchor_reread_bytes=("anchor_read_bytes", "sum"),
    )
    totals = grouped.groupby(["run_id", "layer"])["records"].transform("sum")
    grouped["record_fraction"] = grouped.records / totals
    p = _write(grouped, "A3_format_fallback_map.csv")
    dominant = grouped.loc[grouped.groupby(["run_id", "layer"])["records"].idxmax()].copy()
    runs = sorted(dominant.run_id.unique())
    layers = sorted(dominant.layer.unique())
    codes = {name: i for i, name in enumerate(FORMAT_ORDER)}
    dominant["code"] = dominant.chosen_format.map(codes)
    matrix = _pivot(dominant, "run_id", "layer", "code", runs, layers)
    fig, ax = plt.subplots(figsize=(15, max(6, .3 * len(runs))))
    palette = matplotlib.colors.ListedColormap(["#777777", "#377eb8", "#984ea3", "#4daf4a"])
    palette.set_bad("#d9d9d9")
    image = ax.imshow(np.ma.masked_invalid(matrix), aspect="auto", cmap=palette, vmin=-.5, vmax=3.5)
    ax.set_xticks(range(len(layers)), layers, rotation=45)
    ax.set_yticks(range(len(runs)), [_short(x) for x in runs])
    ax.set_title("A3. Dominant exact format by layer (fallback remains visible)")
    cbar = plt.colorbar(image, ax=ax, ticks=range(4), fraction=.025, pad=.02)
    cbar.ax.set_yticklabels(FORMAT_ORDER)
    _save(fig, "A3_format_fallback_map")
    return [p]


def ablations() -> list[Path]:
    source = V3 / "ablation" / "ablation_decomposition.csv"
    data = pd.read_csv(source)
    base = data[data.component == "optimized_BEICSR"][["config_id", "cycles", "total_physical_bytes"]].rename(
        columns={"cycles": "baseline_cycles", "total_physical_bytes": "baseline_bytes"})
    data = data.merge(base, on="config_id", how="left")
    data["speedup"] = data.baseline_cycles / data.cycles
    data["byte_ratio"] = data.total_physical_bytes / data.baseline_bytes
    p = _write(data, "A4_component_ablation.csv")
    components = list(dict.fromkeys(data.component))
    runs = [x for x in PRIMARY if x in set(data.config_id)]
    fig, axes = plt.subplots(1, 2, figsize=(17, max(4, .55 * len(runs))))
    _heatmap(axes[0], _pivot(data, "config_id", "component", "speedup", runs, components),
             [_short(x) for x in runs], [x.replace("_", "\n") for x in components],
             "Cycles: baseline / variant", cmap="RdYlGn", center=1)
    _heatmap(axes[1], _pivot(data, "config_id", "component", "byte_ratio", runs, components),
             [_short(x) for x in runs], [x.replace("_", "\n") for x in components],
             "Physical bytes / baseline", cmap="RdYlGn_r", center=1)
    fig.suptitle("A4. Equal-accounting component decomposition")
    _save(fig, "A4_component_ablation")
    return [source, p]


def corrected_schedule() -> list[Path]:
    source = V3 / "schedule" / "causal_event_schedule.csv"
    cycles = pd.read_csv(source)
    xor = cycles[cycles.variant == "XORFLOW_ONLINE"].copy()
    p = _write(xor, "A5_corrected_finite_queue_cycles.csv")
    components = ["memory_cycles", "decode_cycles", "aggregation_cycles", "combination_cycles",
                  "encode_cycles", "writeback_cycles", "fill_cycles", "drain_cycles"]
    shown = [x for x in PRIMARY if x in set(xor.run_id)]
    view = xor.set_index("run_id").reindex(shown)
    fractions = view[components].div(view[components].sum(axis=1), axis=0)
    parity = pd.read_csv(V3 / "schedule" / "causal_recurrence_check.csv")
    p2 = _write(parity, "A5_event_recurrence_parity.csv")
    fig, axes = plt.subplots(1, 2, figsize=(16, 5))
    bottom = np.zeros(len(view))
    for component in components:
        vals = fractions[component].to_numpy()
        axes[0].bar(range(len(view)), vals, bottom=bottom, label=component.replace("_cycles", ""))
        bottom += vals
    axes[0].set_xticks(range(len(view)), [_short(x) for x in shown], rotation=70, ha="right")
    axes[0].set_ylabel("Fraction of reported component work")
    axes[0].set_title("Finite queues, dependencies, barriers, fill/drain")
    axes[0].legend(fontsize=7, ncol=2)
    axes[1].scatter(parity.recurrence_layer_cycles, parity.event_layer_cycles, s=10, alpha=.45)
    hi = max(parity.recurrence_layer_cycles.max(), parity.event_layer_cycles.max())
    axes[1].plot([0, hi], [0, hi], "k--", linewidth=1)
    axes[1].set_xlabel("Independent recurrence cycles")
    axes[1].set_ylabel("Event scheduler cycles")
    axes[1].set_title(f"Cross-validation; max error={parity.relative_error.max():.3g}")
    fig.suptitle("A5. Corrected causal finite-queue schedule")
    _save(fig, "A5_corrected_schedule")
    return [source, V3 / "schedule" / "causal_recurrence_check.csv", p, p2]


def _align64(value: int) -> int:
    return ((value + 63) // 64) * 64 if value else 0


def _retention(rows: pd.DataFrame, capacity: int) -> dict[str, float]:
    entries: OrderedDict[tuple[int, int, int], tuple[int, int]] = OrderedDict()
    used = hits = misses = delta_targets = reread = fallback = 0
    for row in rows.sort_values(["layer", "tile", "slice"]).itertuples(index=False):
        key = (int(row.pair_id), int(row.tile), int(row.slice))
        if row.role == "anchor":
            size = _align64(math.ceil(int(row.input_support_bits) / 8))
            while entries and used + size > capacity:
                _, (evicted, _) = entries.popitem(last=False); used -= evicted
            if size <= capacity:
                entries[key] = (size, int(row.padded_bytes)); used += size
        else:
            entry = entries.pop(key, None)
            if entry is not None:
                used -= entry[0]
            if row.chosen_format == "DELTA":
                delta_targets += 1
                if entry is not None:
                    hits += 1
                else:
                    misses += 1
                    # The compressed anchor record is reread, not the raw bitmap.
                    reread += int(row.anchor_source_bytes)
            else:
                fallback += 1
    return {"delta_targets": delta_targets, "delta_anchor_hits": hits,
            "delta_anchor_recoveries": misses, "delta_anchor_hit_rate": hits / max(1, delta_targets),
            "compressed_anchor_reread_bytes": reread, "fallback_targets": fallback}


def retention_sweep() -> list[Path]:
    capacities = [16, 64, 256, 1024, 4096, 16384]
    output: list[dict] = []
    default_cycles = pd.read_csv(V3 / "schedule" / "causal_event_schedule.csv")
    default_speed = default_cycles[default_cycles.variant == "XORFLOW_ONLINE"].set_index("run_id").speedup_vs_selected_baseline
    for run in PRIMARY:
        path = V3 / "online_replay" / f"support_records_{run}_reread.csv"
        if not path.exists():
            continue
        rows = pd.read_csv(path, usecols=["layer", "tile", "slice", "pair_id", "role", "chosen_format",
                                               "input_support_bits", "padded_bytes"])
        anchors = rows[rows.role == "anchor"][["pair_id", "tile", "slice", "padded_bytes"]].rename(
            columns={"padded_bytes": "anchor_source_bytes"})
        rows = rows.merge(anchors, on=["pair_id", "tile", "slice"], how="left")
        for kib in capacities:
            item = {"run_id": run, "capacity_kib": kib, **_retention(rows, kib * 1024)}
            item["corrected_speedup"] = float(default_speed.get(run, np.nan)) if kib == 16 else np.nan
            item["speedup_status"] = "measured_corrected_schedule" if kib == 16 else "not_rerun"
            output.append(item)
    table = pd.DataFrame(output)
    p = _write(table, "A6_anchor_retention_capacity.csv")
    runs = [x for x in PRIMARY if x in set(table.run_id)]
    fig, axes = plt.subplots(1, 3, figsize=(18, max(4, .55 * len(runs))))
    _heatmap(axes[0], _pivot(table, "run_id", "capacity_kib", "delta_anchor_hit_rate", runs, capacities),
             [_short(x) for x in runs], [f"{x} KiB" if x < 1024 else f"{x//1024} MiB" for x in capacities],
             "True DELTA-target anchor hit rate", cmap="YlGn", fmt=".1%")
    _heatmap(axes[1], _pivot(table, "run_id", "capacity_kib", "compressed_anchor_reread_bytes", runs, capacities) / 2**20,
             [_short(x) for x in runs], [f"{x} KiB" if x < 1024 else f"{x//1024} MiB" for x in capacities],
             "Compressed anchor rereads (MiB)", cmap="magma_r", fmt=".1f")
    _heatmap(axes[2], _pivot(table, "run_id", "capacity_kib", "corrected_speedup", runs, capacities),
             [_short(x) for x in runs], [f"{x} KiB" if x < 1024 else f"{x//1024} MiB" for x in capacities],
             "Corrected schedule speedup (gray = not rerun)", cmap="RdYlGn", center=1)
    fig.suptitle("A6. Anchor retention: fallback targets are excluded from hit rate")
    _save(fig, "A6_anchor_retention_capacity")
    return [p]


def encoder_decoder() -> list[Path]:
    enc_source = V3 / "encoder" / "encoder_trace.csv"
    enc = pd.read_csv(enc_source)
    parsed = enc.queue_config.str.extract(r"iq(?P<input_depth>\d+)_work(?P<workers>\d+)_of(?P<outstanding>\d+)")
    enc = pd.concat([enc, parsed.astype(int)], axis=1)
    enc["throughput"] = enc.input_bits / enc.total_cycles
    surface = enc.groupby(["input_depth", "workers", "outstanding"], as_index=False).agg(
        input_bits_per_cycle=("throughput", "median"), producer_stall_fraction=("producer_stall_cycles", lambda x: float(x.sum()) / max(1, enc.loc[x.index, "total_cycles"].sum())),
        max_staging_bytes=("max_staging_bytes", "max"),
    )
    p7 = _write(surface, "A7_encoder_queue_surface.csv")
    worker_labels = sorted({f"w{r.workers}/o{r.outstanding}" for r in surface.itertuples()})
    surface["worker_cfg"] = [f"w{r.workers}/o{r.outstanding}" for r in surface.itertuples()]
    depths = sorted(surface.input_depth.unique())
    fig, axes = plt.subplots(1, 2, figsize=(15, 4.8))
    _heatmap(axes[0], _pivot(surface, "input_depth", "worker_cfg", "input_bits_per_cycle", depths, worker_labels),
             [str(x) for x in depths], worker_labels, "Encoder input bits/cycle", cmap="YlGn")
    _heatmap(axes[1], _pivot(surface, "input_depth", "worker_cfg", "producer_stall_fraction", depths, worker_labels),
             [str(x) for x in depths], worker_labels, "Producer stall fraction", cmap="magma_r", fmt=".1%")
    fig.suptitle("A7. Capacity-enforcing encoder queues")
    _save(fig, "A7_encoder_queue_surface")

    dec_source = V3 / "decoder" / "decoder_cluster_trace.csv"
    dec = pd.read_csv(dec_source)
    bank = dec.groupby("banks", as_index=False).agg(
        encoded_bits_per_cycle=("achieved_encoded_bits_per_cycle", "median"),
        bank_conflicts=("bank_conflicts", "median"), sram_port_utilization=("sram_port_utilization", "median"),
        downstream_stalls=("downstream_backpressure_cycles", "median"), lane_utilization=("lane_utilization", "median"),
    )
    p8 = _write(bank, "A8_decoder_banking.csv")
    metrics = ["encoded_bits_per_cycle", "bank_conflicts", "sram_port_utilization", "downstream_stalls"]
    vals = bank.set_index("banks")[metrics].T.to_numpy(float)
    normalized = vals / np.maximum(np.nanmax(vals, axis=1, keepdims=True), 1e-12)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
    _heatmap(axes[0], normalized, [x.replace("_", "\n") for x in metrics], [str(x) for x in bank.banks],
             "Normalized decoder metrics", cmap="viridis")
    axes[1].plot(bank.banks, bank.encoded_bits_per_cycle, "o-", label="achieved")
    axes[1].axhline(2048, color="black", linestyle="--", label="32×64-bit target")
    axes[1].set_xlabel("Support-cache banks"); axes[1].set_ylabel("Encoded bits/cycle")
    axes[1].set_title("Measured finite-cluster throughput"); axes[1].legend()
    fig.suptitle("A8. Decoder banking, conflicts, and backpressure")
    _save(fig, "A8_decoder_banking")
    return [enc_source, dec_source, p7, p8]


def sensitivity() -> list[Path]:
    fmt_source = V3 / "ablation" / "format_selection.csv"
    formats = pd.read_csv(fmt_source)
    formats["selected_bytes"] = formats["bytes"] * formats["fraction"]
    fallback = formats[formats.format == "BEICSR"][["run_id", "variant", "slice_width", "fraction"]].rename(
        columns={"fraction": "fallback_fraction"})
    width = formats.groupby(["run_id", "variant", "slice_width"], as_index=False).agg(
        selected_bytes=("selected_bytes", "sum"))
    width = width.merge(fallback, on=["run_id", "variant", "slice_width"], how="left")
    width["fallback_fraction"] = width.fallback_fraction.fillna(0.0)
    base = width[width.variant == "BEICSR_OPT"][["run_id", "slice_width", "selected_bytes"]].rename(columns={"selected_bytes": "beicsr_bytes"})
    width = width.merge(base, on=["run_id", "slice_width"], how="left")
    width["byte_ratio"] = width.selected_bytes / width.beicsr_bytes
    p9a = _write(width, "A9_slice_width.csv")

    cached: list[pd.DataFrame] = []
    for path in sorted((COMPLETE / "sensitivity").glob("*cache*.csv")):
        df = pd.read_csv(path)
        xf = df[df.format == "X1_CAUSAL_AUTO"].copy()
        if not xf.empty:
            xf["source_file"] = str(path.relative_to(ROOT)); cached.append(xf)
    cache = pd.concat(cached, ignore_index=True) if cached else pd.DataFrame()
    p9b = _write(cache, "A9_feature_cache_exact_traffic.csv")
    shown = [x for x in PRIMARY if x in set(width.run_id)]
    widths = [64, 96, 128, 256]
    candidate = width[width.variant == "FULL_ONLINE_EVENT"]
    fig, axes = plt.subplots(1, 2, figsize=(15, max(4, .5 * len(shown))))
    _heatmap(axes[0], _pivot(candidate, "run_id", "slice_width", "byte_ratio", shown, widths),
             [_short(x) for x in shown], [str(x) for x in widths], "Corrected-serializer bytes / BEICSR", cmap="RdYlGn_r", center=1)
    if not cache.empty:
        cagg = cache.groupby(["config_id", "feature_cache_bytes"], as_index=False).traffic_reduction_vs_beicsr.median()
        cruns = sorted(cagg.config_id.unique())
        ccols = sorted(cagg.feature_cache_bytes.unique())
        _heatmap(axes[1], _pivot(cagg, "config_id", "feature_cache_bytes", "traffic_reduction_vs_beicsr", cruns, ccols),
                 [_short(x) for x in cruns], [f"{x//1024} KiB" for x in ccols],
                 "Exact traffic reduction (cached; not cycle result)", cmap="RdYlGn", center=0)
    fig.suptitle("A9. Slice width and feature-cache sensitivity")
    _save(fig, "A9_slice_cache_sensitivity")

    order_rows: list[pd.DataFrame] = []
    for path in sorted((COMPLETE / "sensitivity").glob("*source_tiled.csv")):
        df = pd.read_csv(path); df["source_file"] = str(path.relative_to(ROOT)); order_rows.append(df[df.format == "X1_CAUSAL_AUTO"])
    order = pd.concat(order_rows, ignore_index=True) if order_rows else pd.DataFrame()
    p10 = _write(order, "A10_edge_order_exact_traffic.csv")
    # Bandwidth does not change exact traffic. Plot the conservative byte-roofline
    # sensitivity explicitly as a projection, never as a corrected schedule run.
    base_traffic = pd.read_csv(V3 / "physical_traffic" / "physical_traffic_ogbn_arxiv_deepres8_w128_s7.csv")
    bw_rows = []
    for bw in [128, 256, 512, 1024]:
        bytes_per_cycle = bw
        for r in base_traffic.itertuples():
            bw_rows.append({"run_id": r.run_id, "layer": r.layer, "bandwidth_gbs": bw,
                            "roofline_speedup": r.baseline_total_bytes / max(1, r.xorflow_total_bytes),
                            "baseline_roofline_cycles": math.ceil(r.baseline_total_bytes / bytes_per_cycle),
                            "xorflow_roofline_cycles": math.ceil(r.xorflow_total_bytes / bytes_per_cycle),
                            "scope": "byte_roofline_projection_not_corrected_schedule"})
    bw = pd.DataFrame(bw_rows)
    p10b = _write(bw, "A10_bandwidth_roofline_projection.csv")
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.5))
    b = bw.groupby("bandwidth_gbs").agg(baseline=("baseline_roofline_cycles", "sum"), xorflow=("xorflow_roofline_cycles", "sum"))
    axes[0].plot(b.index, b.baseline / b.xorflow, "o-")
    axes[0].axhline(1, color="black", linewidth=.8); axes[0].set_xlabel("HBM bandwidth (GB/s)")
    axes[0].set_ylabel("Byte-roofline speedup"); axes[0].set_title("Projection (not event-schedule timing)")
    if not order.empty:
        o = order.groupby(["config_id", "edge_order"], as_index=False).traffic_reduction_vs_beicsr.median()
        for name, group in o.groupby("config_id"):
            axes[1].plot(group.edge_order, group.traffic_reduction_vs_beicsr, "o-", label=_short(name))
        axes[1].axhline(0, color="black", linewidth=.8); axes[1].legend(fontsize=7)
    axes[1].set_ylabel("Exact traffic reduction"); axes[1].set_title("O0/O1 edge-order sensitivity")
    fig.suptitle("A10. Bandwidth and edge ordering")
    _save(fig, "A10_bandwidth_edge_order")
    return [fmt_source, p9a, p9b, p10, p10b]


def generalization_quality_hardware() -> list[Path]:
    cycles = pd.read_csv(V3 / "schedule" / "causal_event_schedule.csv")
    x = cycles[cycles.variant == "XORFLOW_ONLINE"][["run_id", "total_cycles", "speedup_vs_selected_baseline"]].copy()
    x["family"] = np.select([
        x.run_id.str.contains("graphsage"), x.run_id.str.contains("gin"), x.run_id.str.contains("gcnii")],
        ["GraphSAGE", "GIN", "GCNII"], default="DeepRes")
    x["depth"] = x.run_id.str.extract(r"(?:deepres|gin|graphsage)(\d+)", expand=False).fillna(16).astype(int)
    x["width"] = x.run_id.str.extract(r"_w(\d+)", expand=False).fillna(128).astype(int)
    x["residual"] = np.where(x.run_id.str.contains("residual|deepres|gcnii"), "residual", "plain")
    p11 = _write(x, "A11_architecture_generalization.csv")
    arch = x[x.run_id.str.contains("ogbn_arxiv")].copy()
    arch["architecture"] = arch.family + "\n" + arch.residual
    depths = sorted(arch.depth.unique()); widths = sorted(arch.width.unique())
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    d = arch[arch.width == 128]
    families = sorted(d.architecture.unique())
    _heatmap(axes[0], _pivot(d, "architecture", "depth", "speedup_vs_selected_baseline", families, depths),
             families, [str(v) for v in depths], "Depth / backbone corrected speedup", cmap="RdYlGn", center=1)
    w = arch[(arch.family == "DeepRes") & (arch.depth == 8)]
    _heatmap(axes[1], _pivot(w, "family", "width", "speedup_vs_selected_baseline", ["DeepRes"], widths),
             ["DeepRes-8"], [str(v) for v in widths], "Width corrected speedup", cmap="RdYlGn", center=1)
    fig.suptitle("A11. Architecture generalization (corrected finite-queue scheduler)")
    _save(fig, "A11_architecture_generalization")

    quality_source = V3 / "quality" / "paired_quality.csv"
    quality = pd.read_csv(quality_source)
    dec = pd.read_csv(V3 / "decoder" / "decoder_cluster_trace.csv")
    required = pd.read_csv(V3 / "schedule" / "causal_resource_audit.csv")
    achieved = dec[dec.banks == 16].groupby("run_id", as_index=False).achieved_encoded_bits_per_cycle.median()
    # Schedule's explicit decoder service width is 2,048 bit/cycle.
    achieved["schedule_required_bits_per_cycle"] = 2048.0
    achieved["throughput_margin"] = achieved.achieved_encoded_bits_per_cycle / 2048.0
    public_quality = quality.drop(columns=["checkpoint_fp32", "checkpoint_quantized"], errors="ignore")
    p12a = _write(public_quality, "A12_quantized_quality.csv")
    p12b = _write(achieved, "A12_decoder_throughput_margin.csv")
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))
    axes[0].scatter(quality.fp32, quality.fp8_fp16, c=quality.paired_delta, cmap="coolwarm", s=35)
    lo = min(quality.fp32.min(), quality.fp8_fp16.min()); hi = max(quality.fp32.max(), quality.fp8_fp16.max())
    axes[0].plot([lo, hi], [lo, hi], "k--"); axes[0].set_xlabel("FP32 quality")
    axes[0].set_ylabel("FP8 activation / FP16 weight quality"); axes[0].set_title("Paired quality")
    axes[1].scatter(np.full(len(achieved), 2048), achieved.achieved_encoded_bits_per_cycle, alpha=.6)
    lim = max(2200, achieved.achieved_encoded_bits_per_cycle.max() * 1.05)
    axes[1].plot([0, lim], [0, lim], "k--"); axes[1].set_xlim(0, 2200); axes[1].set_ylim(0, lim)
    axes[1].set_xlabel("Schedule-required bits/cycle"); axes[1].set_ylabel("Finite decoder achieved bits/cycle")
    axes[1].set_title("Throughput contract")
    fig.suptitle("A12. Numerical quality and hardware throughput validation")
    _save(fig, "A12_quality_hardware_validation")
    return [quality_source, V3 / "decoder" / "decoder_cluster_trace.csv", p11, p12a, p12b]


def supporting_tables() -> list[Path]:
    outputs: list[Path] = []
    cycles = pd.read_csv(V3 / "schedule" / "causal_event_schedule.csv")
    summary = pd.read_csv(V3 / "report" / "paper_summary.csv")
    merged = summary.merge(cycles[cycles.variant == "XORFLOW_ONLINE"], left_on="config_id", right_on="run_id", how="left")
    outputs.append(_write(merged, "S1_full_corrected_results.csv"))
    ppa_source = COMPLETE / "ppa" / "20260729T_local_ppa_reroute" / "ppa_summary.csv"
    if ppa_source.exists():
        outputs.append(_write(pd.read_csv(ppa_source), "S2_ppa.csv"))
    cacti = V3 / "hardware" / "cacti" / "support_cache_cacti.csv"
    outputs.append(_write(pd.read_csv(cacti), "S3_support_cache_cacti.csv"))
    negative = merged[(merged.speedup_vs_selected_baseline < 1) | (merged.support_reduction < 0)]
    outputs.append(_write(negative, "S4_negative_cases.csv"))
    tools = []
    for path in [V3 / "encoder" / "encoder_synth.json", V3 / "decoder" / "decoder_cluster_openroad_summary.json"]:
        payload = json.loads(path.read_text())
        tools.append({"artifact": str(path.relative_to(ROOT)), "status": payload.get("status", ""),
                      "tool": payload.get("tool", "Yosys/Verilator"), "sha256": _sha(path)})
    outputs.append(_write(pd.DataFrame(tools), "S5_tool_validation.csv"))
    return outputs


def _manifest(sources: Iterable[Path]) -> None:
    rows = []
    for path in sorted(set(Path(p) for p in sources if Path(p).exists())):
        rows.append({"artifact": str(path.relative_to(ROOT)), "kind": "source" if V3 in path.parents or COMPLETE in path.parents else "derived_table",
                     "sha256": _sha(path), "bytes": path.stat().st_size})
    for path in sorted(FIG.glob("*")):
        rows.append({"artifact": str(path.relative_to(ROOT)), "kind": "figure", "sha256": _sha(path), "bytes": path.stat().st_size})
    for path in sorted(TAB.glob("*.csv")):
        if not any(r["artifact"] == str(path.relative_to(ROOT)) for r in rows):
            rows.append({"artifact": str(path.relative_to(ROOT)), "kind": "derived_table", "sha256": _sha(path), "bytes": path.stat().st_size})
    for path in sorted(OUT.glob("*.md")):
        rows.append({"artifact": str(path.relative_to(ROOT)), "kind": "documentation",
                     "sha256": _sha(path), "bytes": path.stat().st_size})
    pd.DataFrame(rows).to_csv(OUT / "RESULT_MANIFEST.csv", index=False, lineterminator="\n")


def _index() -> None:
    text = """# XORFLOW Appendix Figure Index

All cycle panels use the corrected causal finite-queue scheduler. Older cached
sensitivity artifacts are used only where the caption says **exact traffic** or
**byte-roofline projection**. They are not substituted for corrected cycle runs.
Gray heatmap cells mean “not measured”; values are never interpolated.

| ID | Figure | Reviewer question | Source table |
|---|---|---|---|
| A1 | Layerwise persistence | Where and when does temporal structure occur? | `tables/A1_layerwise_persistence.csv` |
| A2 | Learned-structure controls | Is the effect more than density alone? | `tables/A2_learned_structure_controls.csv` |
| A3 | Format/fallback map | When does the exact selector fall back? | `tables/A3_format_fallback_map.csv` |
| A4 | Component ablation | Independent codec, spatial prototype, temporal XOR, fallback contributions | `tables/A4_component_ablation.csv` |
| A5 | Corrected schedule | Finite queues, dependencies, barriers, fill/drain, independent recurrence parity | `tables/A5_corrected_finite_queue_cycles.csv` |
| A6 | Anchor retention | True DELTA-target hits and compressed-anchor recovery traffic | `tables/A6_anchor_retention_capacity.csv` |
| A7 | Encoder queues | Backpressure and queue saturation | `tables/A7_encoder_queue_surface.csv` |
| A8 | Decoder banks | Conflicts, ports, throughput and downstream stalls | `tables/A8_decoder_banking.csv` |
| A9 | Slice/cache | Robustness to slice width and feature-cache capacity | `tables/A9_slice_width.csv` |
| A10 | Bandwidth/order | Byte-roofline and exact O0/O1 traffic sensitivity | `tables/A10_bandwidth_roofline_projection.csv` |
| A11 | Generalization | Depth, width, backbone and residual variants | `tables/A11_architecture_generalization.csv` |
| A12 | Quality/hardware | Quantized quality and decoder throughput contract | `tables/A12_quantized_quality.csv` |

## Interpretation contract

- Anchor hit rate counts only target records whose selected format is `DELTA`.
  A BEICSR fallback neither hits nor misses an anchor because it does not need one.
- A6 capacity points beyond 16 KiB are exact retention/recovery-byte replays. Their
  corrected cycle cells remain gray because the event scheduler was not rerun for
  those capacities.
- A9 cache and A10 ordering panels report exact physical traffic. A10 bandwidth is
  explicitly a byte-roofline projection, not event-driven or end-to-end timing.
- “Speedup” elsewhere means modeled aggregation+combination subsystem speedup,
  never measured full-GNN speedup.
"""
    (OUT / "APPENDIX_FIGURE_INDEX.md").write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    FIG.mkdir(parents=True, exist_ok=True); TAB.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 8, "axes.grid": False, "figure.dpi": 120})
    sources: list[Path] = []
    sources += persistence_and_controls()
    sources += format_map()
    sources += ablations()
    sources += corrected_schedule()
    sources += retention_sweep()
    sources += encoder_decoder()
    sources += sensitivity()
    sources += generalization_quality_hardware()
    sources += supporting_tables()
    _index(); _manifest(sources)
    print(json.dumps({"figures": len(list(FIG.glob('*.png'))), "tables": len(list(TAB.glob('*.csv'))),
                      "output": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
