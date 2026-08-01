"""CSV-derived plots and final Markdown reporting."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _markdown_table(frame: pd.DataFrame) -> str:
    values = frame.fillna("").astype(str)
    header = "| " + " | ".join(values.columns) + " |"
    divider = "| " + " | ".join("---" for _ in values.columns) + " |"
    rows = [
        "| " + " | ".join(value.replace("|", "\\|") for value in row) + " |"
        for row in values.itertuples(index=False, name=None)
    ]
    return "\n".join([header, divider, *rows])


def _save(fig, root: Path, name: str):
    fig.tight_layout()
    fig.savefig(root / f"{name}.png", dpi=160)
    fig.savefig(root / f"{name}.pdf")
    plt.close(fig)


def generate_plots(signal: pd.DataFrame, cohort: pd.DataFrame, temporal: pd.DataFrame, root: Path):
    trained = signal[signal.trace_state == "trained"]
    figures = [
        ("density_by_layer", trained, "layer", "density", None),
        ("spatial_mismatch_ratio_by_layer", trained, "layer", "local_to_random_ratio", 0.90),
        ("temporal_flip_by_layer", trained, "layer", "temporal_flip", 0.22),
    ]
    for name, frame, x, y, line in figures:
        fig, ax = plt.subplots(figsize=(7, 4))
        for config_id, group in frame.groupby("config_id"):
            ax.plot(group[x], group[y], marker=".", label=config_id)
        if line is not None:
            ax.axhline(line, color="black", linestyle="--", linewidth=1)
        ax.set(xlabel=x, ylabel=y)
        ax.legend(fontsize=7)
        _save(fig, root, name)
    rcm = cohort[(cohort.trace_state == "trained") & (cohort.grouping_method == "rcm_cost_cluster")]
    for name, y, line in (
        ("regular_capture_padding_by_layer", "regular_capture", 0.70),
        ("proxy_speedup_rho2_by_layer", "proxy_speedup_rho2", 1.15),
    ):
        fig, ax = plt.subplots(figsize=(7, 4))
        for config_id, group in rcm.groupby("config_id"):
            ax.plot(group.layer, group[y], marker=".", label=config_id)
        ax.axhline(line, color="black", linestyle="--", linewidth=1)
        ax.set(xlabel="layer", ylabel=y)
        ax.legend(fontsize=7)
        _save(fig, root, name)
    fig, ax = plt.subplots(figsize=(7, 4))
    for config_id, group in temporal.groupby("config_id"):
        ax.plot(group.to_layer, group.reuse_penalty, marker=".", label=config_id)
    ax.axhline(0.10, color="black", linestyle="--", linewidth=1)
    ax.set(xlabel="to_layer", ylabel="reuse_penalty")
    ax.legend(fontsize=7)
    _save(fig, root, "reuse_penalty_by_layer")
    fig, ax = plt.subplots(figsize=(8, 4))
    grouped = cohort[(cohort.trace_state == "trained") & (cohort.layer >= 4)].groupby(
        ["config_id", "grouping_method"]
    ).proxy_speedup_rho2.median().unstack()
    grouped.plot.bar(ax=ax)
    ax.set(ylabel="median analytical proxy speedup (rho=2)")
    _save(fig, root, "grouping_method_comparison")
    fig, ax = plt.subplots(figsize=(8, 4))
    compare = signal[signal.layer >= 4].groupby(
        ["config_id", "trace_state"]
    ).local_to_random_ratio.median().unstack()
    compare.plot.bar(ax=ax)
    ax.set(ylabel="median local/random mismatch ratio")
    _save(fig, root, "trained_vs_random_init")


def write_results(
    root: Path,
    decision: str,
    summary: pd.DataFrame,
    quality: pd.DataFrame,
    wall_seconds: float,
    gpu_active: bool,
    strongest_positive: str,
    strongest_negative: str,
):
    table = _markdown_table(summary[
        ["config_id", "model_valid", "spatial_gate", "temporal_gate", "cohort_gate",
         "control_gate", "config_decision"]
    ])
    quality_table = _markdown_table(quality[quality.trace_state == "trained"][
        ["config_id", "status", "test_accuracy", "best_epoch", "training_truncated"]
    ])
    text = f"""# MOSAIC-GNN Phase-0 results

## Executive decision

`{decision}`

Runtime was {wall_seconds:.1f} seconds. GPU execution active: `{str(gpu_active).lower()}`.

## Model validity

{quality_table}

## Configuration gates

{table}

## Controls and interpretation

Strongest positive signal: {strongest_positive}

Strongest negative signal: {strongest_negative}

The component-level conclusion follows the exact spatial, temporal, cohort, and
oracle gates in `05_config_summary.csv`. Failed configurations and invalid models
remain visible rather than being suppressed.

All values named `proxy_speedup_*` are analytical irregular-cost proxies. They
are **not measured hardware speedups**. The SCALE-Sim run is a dense GEMM
callability smoke test and does not evaluate MOSAIC.

## Next experiment

Use the failure-driven objective map: if the global oracle passes while RCM
fails, test a joint edge-locality/support partitioner; if temporal reuse fails,
rebuild templates per layer; if every oracle fails, pivot or kill templates.
"""
    (root / "RESULTS.md").write_text(text)
