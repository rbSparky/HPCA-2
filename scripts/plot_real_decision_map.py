#!/usr/bin/env python3
"""Render the XORFLOW decision map from exact trained-mask records.

The axes are measured properties of each 128-row topology tile.  Point colors
come from the deployed, byte-exact serializer choices; no synthetic points or
post-hoc classifier is used.  The plot intentionally includes the first-layer
warm-up pair so the legal BEICSR fallback remains visible.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.ndimage import gaussian_filter1d
from scipy.sparse.csgraph import reverse_cuthill_mckee


PAIR_STARTS = tuple(range(0, 16, 2))


def unpack_masks(path: Path) -> np.ndarray:
    payload = np.load(path)
    shape = tuple(int(x) for x in payload["shape"])
    return np.unpackbits(payload["packed"], axis=2)[:, :, : shape[2]].astype(bool)


def arxiv_rcm(edge_path: Path, nodes: int) -> np.ndarray:
    edges = np.loadtxt(edge_path, delimiter=",", dtype=np.int64)
    rows = np.concatenate((edges[:, 0], edges[:, 1]))
    cols = np.concatenate((edges[:, 1], edges[:, 0]))
    graph = sparse.csr_matrix(
        (np.ones(rows.size, dtype=np.uint8), (rows, cols)), shape=(nodes, nodes)
    )
    return reverse_cuthill_mckee(graph, symmetric_mode=True).astype(np.int64)


def candidate(record: pd.Series, name: str) -> int:
    return int(json.loads(record.candidate_bytes_json)[name])


def build_table(masks: np.ndarray, order: np.ndarray, records: pd.DataFrame) -> pd.DataFrame:
    lookup = records.set_index(["layer", "tile", "slice"])
    output: list[dict[str, object]] = []
    for pair_start in PAIR_STARTS:
        if pair_start + 1 >= masks.shape[0]:
            continue
        for tile_id, start in enumerate(range(0, order.size, 128)):
            ids = order[start : start + 128]
            anchor = masks[pair_start, ids]
            target = masks[pair_start + 1, ids]
            residual_counts: list[np.ndarray] = []
            for cohort_start in range(0, len(ids), 32):
                cohort = anchor[cohort_start : cohort_start + 32]
                prototype = cohort.sum(axis=0) > (len(cohort) / 2)
                residual_counts.append(np.logical_xor(cohort, prototype).sum(axis=1))
            anchor_row_residual = np.concatenate(residual_counts)
            flips = np.logical_xor(anchor, target).sum(axis=1)
            a = lookup.loc[(pair_start, tile_id, 0)]
            t = lookup.loc[(pair_start + 1, tile_id, 0)]
            baseline = candidate(a, "BEICSR") + candidate(t, "BEICSR")
            selected = int(a.unpadded_bytes) + int(t.unpadded_bytes)
            anchor_fmt = str(a.chosen_format)
            target_fmt = str(t.chosen_format)
            if target_fmt == "BEICSR":
                decision = "BEICSR fallback"
            elif anchor_fmt == "A2":
                decision = "cohort prototype + XOR"
            else:
                decision = "bitmap anchor + XOR"
            output.append(
                {
                    "config_id": str(a.run_id),
                    "pair_start": pair_start + 1,
                    "pair_end": pair_start + 2,
                    "principal_pair": pair_start >= 3,
                    "tile_id": tile_id,
                    "rows": len(ids),
                    "mean_spatial_residual_indices_per_row": float(anchor_row_residual.mean()),
                    "mean_temporal_flip_indices_per_row": float(flips.mean()),
                    "median_spatial_residual_indices_per_row": float(np.median(anchor_row_residual)),
                    "median_temporal_flip_indices_per_row": float(np.median(flips)),
                    "anchor_format": anchor_fmt,
                    "target_format": target_fmt,
                    "decision_class": decision,
                    "selected_support_bytes": selected,
                    "beicsr_support_bytes": baseline,
                    "support_byte_reduction": 1.0 - selected / baseline,
                    "exact_selection_pass": selected <= baseline,
                }
            )
    return pd.DataFrame(output)


def render(table: pd.DataFrame, output: Path) -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.labelsize": 10,
            "axes.titlesize": 11,
            "pdf.fonttype": 42,
        }
    )
    colors = {
        "cohort prototype + XOR": "#E5AE25",
        "bitmap anchor + XOR": "#30343B",
        "BEICSR fallback": "#3676A8",
    }
    zorders = {
        "bitmap anchor + XOR": 1,
        "cohort prototype + XOR": 2,
        "BEICSR fallback": 3,
    }
    fig = plt.figure(figsize=(7.25, 5.65), constrained_layout=False)
    grid = fig.add_gridspec(
        2, 2, width_ratios=(5.4, 1.15), height_ratios=(1.15, 5.2),
        left=0.105, right=0.975, bottom=0.12, top=0.95, wspace=0.035, hspace=0.035,
    )
    ax = fig.add_subplot(grid[1, 0])
    top = fig.add_subplot(grid[0, 0], sharex=ax)
    right = fig.add_subplot(grid[1, 1], sharey=ax)
    fig.add_subplot(grid[0, 1]).axis("off")

    for name in ("bitmap anchor + XOR", "cohort prototype + XOR", "BEICSR fallback"):
        values = table[table.decision_class == name]
        ax.scatter(
            values.mean_spatial_residual_indices_per_row,
            values.mean_temporal_flip_indices_per_row,
            s=9 if name != "BEICSR fallback" else 20,
            c=colors[name], alpha=0.22 if name == "bitmap anchor + XOR" else 0.65,
            linewidths=0, rasterized=True, zorder=zorders[name],
        )

    # This transition is measured, not a fitted decision model: all selected
    # and all fallback records are separated at this exact empirical boundary.
    selected = table[table.target_format == "DELTA"].mean_temporal_flip_indices_per_row
    fallback = table[table.target_format == "BEICSR"].mean_temporal_flip_indices_per_row
    selected_max = float(selected.max())
    fallback_min = float(fallback.min())
    transition = (selected_max + fallback_min) / 2
    ax.axhline(transition, color="#54768D", lw=1.1, ls=(0, (4, 3)))
    ax.text(
        0.985, transition + 0.35,
        f"observed selector transition: {selected_max:.2f} → {fallback_min:.2f} flips/row",
        transform=ax.get_yaxis_transform(), ha="right", va="bottom", color="#355E78", fontsize=8,
    )

    # Smooth one-dimensional marginals.  Counts are divided by the total tile
    # count (not normalized independently per class), so curve area preserves
    # each deployed format's actual prevalence.  sigma=1.25 bins is fixed.
    def marginal(axis, column: str, bins: np.ndarray, vertical: bool) -> None:
        centers = (bins[:-1] + bins[1:]) / 2
        for name in colors:
            values = table.loc[table.decision_class == name, column].to_numpy()
            counts, _ = np.histogram(values, bins=bins)
            density = gaussian_filter1d(counts.astype(float), sigma=1.25)
            density /= len(table) * (bins[1] - bins[0])
            if vertical:
                axis.fill_betweenx(centers, 0, density, color=colors[name], alpha=0.32)
                axis.plot(density, centers, color=colors[name], lw=1.25)
            else:
                axis.fill_between(centers, 0, density, color=colors[name], alpha=0.32)
                axis.plot(centers, density, color=colors[name], lw=1.25)

    marginal(top, "mean_spatial_residual_indices_per_row", np.arange(0, 70.5, 0.5), False)
    marginal(right, "mean_temporal_flip_indices_per_row", np.arange(0, 26.25, 0.25), True)
    top.tick_params(axis="x", labelbottom=False)
    right.tick_params(axis="y", labelleft=False)
    top.set_ylabel("marginal\ndensity", labelpad=3)
    right.set_xlabel("marginal\ndensity", labelpad=3)
    for marginal in (top, right):
        marginal.spines[["top", "right"]].set_visible(False)
        marginal.grid(False)

    ax.set_xlim(0, max(70, np.ceil(table.mean_spatial_residual_indices_per_row.max() / 5) * 5))
    ax.set_ylim(0, 26)
    ax.set_xlabel(r"mean anchor-to-prototype residuals per row  $|r_v|$")
    ax.set_ylabel(r"mean adjacent-layer support flips per row  $|\delta_v|$")
    ax.grid(True, color="#D8DEE4", lw=0.55, alpha=0.8)
    ax.set_axisbelow(True)

    principal = table[table.principal_pair]
    all_delta = 100 * (table.target_format == "DELTA").mean()
    principal_delta = 100 * (principal.target_format == "DELTA").mean()
    a2 = 100 * (principal.anchor_format == "A2").mean()
    byte_reduction = 100 * (
        1 - principal.selected_support_bytes.sum() / principal.beicsr_support_bytes.sum()
    )
    message = (
        f"{principal_delta:.1f}% of principal tile-slices select exact XOR\n"
        f"{a2:.1f}% also reuse a spatial cohort prototype\n"
        f"{byte_reduction:.1f}% aggregate support-byte reduction"
    )
    ax.text(
        0.025, 0.965, message, transform=ax.transAxes, ha="left", va="top",
        bbox={"boxstyle": "round,pad=0.38", "facecolor": "white", "edgecolor": "#7A8790", "alpha": 0.94},
        fontsize=9,
    )
    fallback_rows = table[table.target_format == "BEICSR"]
    ax.annotate(
        "legal warm-up fallback",
        xy=(float(fallback_rows.mean_spatial_residual_indices_per_row.median()),
            float(fallback_rows.mean_temporal_flip_indices_per_row.median())),
        xytext=(52, 22.5), textcoords="data", ha="center", va="center", color="#24597C",
        arrowprops={"arrowstyle": "->", "color": "#24597C", "lw": 1.0},
    )
    handles = [
        Line2D([0], [0], marker="o", color="none", markerfacecolor=colors[name],
               markeredgecolor="none", markersize=6, label=name)
        for name in colors
    ]
    ax.legend(handles=handles, loc="lower right", frameon=True, framealpha=0.95, fontsize=8)
    fig.text(
        0.105, 0.982,
        f"Exact XORFLOW decision map — OGBN-Arxiv DeepRes-16 ({len(table):,} tile-pairs)",
        ha="left", va="top", fontsize=11, fontweight="bold",
    )
    ax.text(
        0, -0.19,
        f"Measured from trained FP8 supports; 128-row RCM tiles, 32-row cohorts, 128-feature slices. "
        f"Color is the byte-exact deployed selector ({all_delta:.1f}% XOR across all pairs).",
        transform=ax.transAxes, ha="left", va="top", fontsize=7.8, color="#41484D",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(output.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("results_hpca_xorflow/figures/xorflow_real_decision_map"))
    args = parser.parse_args()
    project = args.project.resolve()
    trace = project / "artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres16_w128_s7/fp8_supports.npz"
    records_path = project / "results_hpca_xorflow/reviewer_spec_v3/online_replay/support_records_ogbn_arxiv_deepres16_w128_s7_finite_retention.csv"
    edge_path = project / "../mosaic_validation/data/ogbn_arxiv/raw/edge.csv.gz"
    masks = unpack_masks(trace)
    order = arxiv_rcm(edge_path, masks.shape[1])
    table = build_table(masks, order, pd.read_csv(records_path))
    if not bool(table.exact_selection_pass.all()):
        raise AssertionError("deployed selector exceeded the legal BEICSR fallback")
    output = (project / args.output).resolve() if not args.output.is_absolute() else args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(output.with_suffix(".csv"), index=False)
    render(table, output)
    principal = table[table.principal_pair]
    summary = {
        "config_id": str(table.config_id.iloc[0]),
        "tile_pairs": int(len(table)),
        "principal_tile_pairs": int(len(principal)),
        "all_pair_delta_selection_fraction": float((table.target_format == "DELTA").mean()),
        "principal_delta_selection_fraction": float((principal.target_format == "DELTA").mean()),
        "principal_a2_selection_fraction": float((principal.anchor_format == "A2").mean()),
        "principal_support_byte_reduction": float(1 - principal.selected_support_bytes.sum() / principal.beicsr_support_bytes.sum()),
        "selected_max_mean_flips_per_row": float(table.loc[table.target_format == "DELTA", "mean_temporal_flip_indices_per_row"].max()),
        "fallback_min_mean_flips_per_row": float(table.loc[table.target_format == "BEICSR", "mean_temporal_flip_indices_per_row"].min()),
    }
    output.with_suffix(".json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
