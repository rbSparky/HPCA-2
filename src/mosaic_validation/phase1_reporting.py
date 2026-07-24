"""Phase-1 CSV-derived plots and human-readable report."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _save(fig, root: Path, name: str):
    fig.tight_layout()
    fig.savefig(root / f"{name}.png", dpi=160)
    fig.savefig(root / f"{name}.pdf")
    plt.close(fig)


def generate_phase1_plots(
    summary: pd.DataFrame,
    encoding: pd.DataFrame,
    modes: pd.DataFrame,
    rebase: pd.DataFrame,
    controls: pd.DataFrame,
    sensitivity: pd.DataFrame,
    root: Path,
) -> None:
    principal = summary[summary.model_valid].set_index("config_id")
    fig, ax = plt.subplots(figsize=(8, 4))
    principal[["phase0_proxy_speedup", "median_proxy_speedup_rho1_25"]].plot.bar(ax=ax)
    ax.set(ylabel="analytical proxy")
    _save(fig, root, "phase0_vs_delta_proxy")

    fig, ax = plt.subplots(figsize=(8, 4))
    principal.metadata_reduction.plot.bar(ax=ax)
    ax.set(ylabel="metadata reduction")
    _save(fig, root, "metadata_reduction_by_model")

    fig, ax = plt.subplots(figsize=(8, 4))
    rho = sensitivity[sensitivity.parameter == "rho_delta"]
    for config_id, group in rho.groupby("config_id"):
        ax.plot(group.value, group.proxy_speedup, marker="o", label=config_id)
    ax.set(xlabel="rho_delta", ylabel="analytical proxy", title="Residual-path sensitivity")
    ax.legend(fontsize=7)
    _save(fig, root, "rho_delta_sensitivity")

    fig, ax = plt.subplots(figsize=(8, 4))
    windows = sensitivity[sensitivity.parameter == "window_length"]
    for config_id, group in windows.groupby("config_id"):
        ax.plot(group.value, group.proxy_speedup, marker="o", label=config_id)
    ax.set(xlabel="window length", ylabel="analytical proxy")
    ax.legend(fontsize=7)
    _save(fig, root, "window_length_sensitivity")

    fig, ax = plt.subplots(figsize=(8, 4))
    rb = rebase[rebase.rebase_cost_fraction == 0.01].pivot(
        index="config_id", columns="policy", values="total_proxy_cost"
    )
    rb.plot.bar(ax=ax)
    ax.set(ylabel="total analytical proxy cost")
    _save(fig, root, "rebase_vs_oracle")

    fig, ax = plt.subplots(figsize=(8, 4))
    control_plot = controls.pivot(
        index="config_id", columns="control_type", values="metadata_reduction"
    )
    control_plot.plot.bar(ax=ax)
    ax.set(ylabel="metadata reduction")
    _save(fig, root, "real_vs_null")

    fig, ax = plt.subplots(figsize=(8, 4))
    breakdown = modes[modes.grouping_method == "window_cost_cluster"].groupby(
        "config_id"
    )[["fraction_absent", "fraction_regular", "fraction_delta"]].mean()
    breakdown.plot.bar(stacked=True, ax=ax)
    ax.set(ylabel="feature-plane fraction")
    _save(fig, root, "feature_mode_breakdown")


def _markdown(frame: pd.DataFrame) -> str:
    values = frame.fillna("").astype(str)
    lines = [
        "| " + " | ".join(values.columns) + " |",
        "| " + " | ".join("---" for _ in values.columns) + " |",
    ]
    lines.extend(
        "| " + " | ".join(str(value).replace("|", "\\|") for value in row) + " |"
        for row in values.itertuples(index=False, name=None)
    )
    return "\n".join(lines)


def write_phase1_report(
    root: Path,
    decision: str,
    wall_seconds: float,
    device: str,
    summary: pd.DataFrame,
    quality: pd.DataFrame,
    gates: pd.DataFrame,
    controls: pd.DataFrame,
    sensitivity: pd.DataFrame,
) -> None:
    valid = summary[summary.model_valid]
    best = valid.loc[valid.median_proxy_speedup_rho1_25.idxmax()]
    worst = valid.loc[valid.median_proxy_speedup_rho1_25.idxmin()]
    text = f"""# MOSAIC-Delta Phase-1 results

## Executive decision

`{decision}`

Wall-clock: {wall_seconds:.1f} seconds. Actual device: `{device}`.

## Model validity

{_markdown(quality)}

## Principal results

{_markdown(summary)}

## Gate table

{_markdown(gates)}

## Null controls

{_markdown(controls)}

## Sensitivity

The full bounded Cartesian sweep and all A0-A5 ablations are in
`13_phase1_sensitivity.csv`. Fixed-setting rho and window excerpts:

{_markdown(sensitivity[sensitivity.parameter.isin(["rho_delta", "window_length"])])}

## Exact stream layout

Bytes are accounted in six cohort-window stream families, each aligned once to
64 bytes: regular feature IDs; regular values per layer; delta feature IDs;
delta initial masks; delta XOR transitions per transition; and delta active
values per layer. No feature is aligned independently. Delta transitions choose
exactly between a dense lane-bitmask and a counted list of flipped lane IDs.
Decoded support was checked bit-for-bit.

## Interpretation

Strongest positive signal: `{best.config_id}` reached a rho=1.25 analytical
proxy of {best.median_proxy_speedup_rho1_25:.3f}.

Strongest negative signal: `{worst.config_id}` reached only
{worst.median_proxy_speedup_rho1_25:.3f}; failed gates remain visible above.

The dense SCALE-Sim run remains a callability smoke test and does not evaluate
MOSAIC-Delta. Every `proxy_speedup` value is an analytical proxy, not a measured
hardware speedup.
"""
    (root / "PHASE1_RESULTS.md").write_text(text)
