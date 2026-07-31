#!/usr/bin/env python3
"""Generate reviewer figures directly from frozen CSV rows."""
from __future__ import annotations

import csv
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"
FIG = V3 / "figures"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def save(name: str, fig: plt.Figure) -> None:
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", dpi=180)
    fig.savefig(FIG / f"{name}.pdf")
    plt.close(fig)


def headline() -> list[dict[str, str]]:
    return read(V3 / "report" / "paper_summary.csv")


def main() -> None:
    rows = headline()
    labels = [r["config_id"] for r in rows]
    support = [float(r["support_reduction"]) for r in rows]
    traffic = [float(r["exact_edge_traffic_reduction"]) for r in rows]
    speed = [float(r["event_speedup"]) for r in rows]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(range(len(labels)), support, color="#377eb8")
    ax.set_xticks(range(len(labels)), labels, rotation=80, ha="right", fontsize=7)
    ax.set_ylabel("Support-byte reduction")
    ax.set_title("Figure 1: causal online support reduction by workload")
    ax.axhline(0, color="black", linewidth=.7)
    save("figure1_support_reduction", fig)

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.scatter(traffic, speed, c=support, cmap="viridis", s=45)
    for x, y, label in zip(traffic, speed, labels):
        ax.annotate(label, (x, y), fontsize=6, xytext=(3, 3), textcoords="offset points")
    ax.axhline(1, color="black", linewidth=.7)
    ax.axvline(0, color="black", linewidth=.7)
    ax.set_xlabel("Exact edge-traffic reduction")
    ax.set_ylabel("Modeled event-driven speedup")
    ax.set_title("Figure 4: physical traffic and event-driven subsystem result")
    save("figure4_headline_breakdown", fig)

    char: list[dict[str, str]] = []
    for path in sorted((V3 / "characterization").glob("adjacent_support_*.csv")):
        char.extend(read(path))
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for row in char:
        if row.get("control_type") in {"real_adjacent", "row_permutation"}:
            grouped[row["run_id"]][row["control_type"]].append(float(row["xor_density"]))
    names = sorted(grouped)
    real = [statistics.median(grouped[n].get("real_adjacent", [0])) for n in names]
    shuffled = [statistics.median(grouped[n].get("row_permutation", [0])) for n in names]
    fig, ax = plt.subplots(figsize=(12, 5))
    x = list(range(len(names)))
    ax.plot(x, real, "o-", label="real adjacent")
    ax.plot(x, shuffled, "o-", label="row-permuted control")
    ax.set_xticks(x, names, rotation=80, ha="right", fontsize=7)
    ax.set_ylabel("Median XOR density")
    ax.set_title("Figure 1 control: learned temporal persistence versus row shuffle")
    ax.legend()
    save("figure1_persistence_control", fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(labels, speed, color=["#4daf4a" if s >= 1 else "#e41a1c" for s in speed])
    ax.axhline(1, color="black", linewidth=.8)
    ax.set_xticklabels(labels, rotation=80, ha="right", fontsize=7)
    ax.set_ylabel("Modeled event-driven speedup")
    ax.set_title("Figure 5: negative cases remain visible; fallback is local")
    save("figure5_negative_cases", fig)

    decoder = []
    for path in sorted((V3 / "decoder").glob("*/decoder_cluster_trace_b32.csv")):
        decoder.extend(read(path))
    dgroup: dict[str, list[float]] = defaultdict(list)
    for row in decoder:
        dgroup[row["run_id"]].append(float(row["achieved_encoded_bits_per_cycle"]))
    names = sorted(dgroup)
    vals = [statistics.median(dgroup[n]) for n in names]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.bar(range(len(names)), vals, color="#984ea3")
    ax.axhline(2048, color="black", linestyle="--", label="32×64-bit nominal width")
    ax.set_xticks(range(len(names)), names, rotation=80, ha="right", fontsize=7)
    ax.set_ylabel("Achieved encoded bits/cycle")
    ax.set_title("Decoder cluster: achieved stream throughput from finite model")
    ax.legend()
    save("figure3_decoder_throughput", fig)

    timing = []
    for path in sorted((ROOT / "results_hpca_xorflow" / "complete_suite" / "timing" / "ramulator").glob("*.csv")):
        timing.extend(read(path))
    tg: dict[str, list[float]] = defaultdict(list)
    for row in timing:
        if row.get("format") == "xorflow" and row.get("speedup_vs_beicsr"):
            tg[row["config_id"]].append(float(row["speedup_vs_beicsr"]))
    names = sorted(tg)
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(names, [statistics.median(tg[n]) for n in names], color="#ff7f00")
    ax.axhline(1, color="black", linewidth=.8)
    ax.set_ylabel("Ramulator pair-4 speedup versus BEICSR")
    ax.set_title("Independent timing evidence (pair microbenchmarks)")
    save("figure5_ramulator_pair_timing", fig)

    quality = read(ROOT / "results_hpca_xorflow" / "complete_suite" / "quality" / "primary_quality.csv")
    names = [r["config_id"] for r in quality]
    deltas = [float(r["value"]) - float(r["floor"]) for r in quality]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(range(len(names)), deltas, color=["#4daf4a" if d >= 0 else "#e41a1c" for d in deltas])
    ax.axhline(0, color="black", linewidth=.8)
    ax.set_xticks(range(len(names)), names, rotation=80, ha="right", fontsize=7)
    ax.set_ylabel("Quality value minus declared floor")
    ax.set_title("Model validity and borderline cases")
    save("figure2_quality", fig)

    # The method diagram is deliberately generated as a schematic, while all
    # numerical figures above come directly from CSVs.
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.axis("off")
    boxes = [(0.03, "post-ReLU support"), (0.27, "causal A0/A2\nanchor"), (0.51, "XOR / BEICSR\nselector"), (0.75, "finite decoder\n+ support cache")]
    for x, text in boxes:
        ax.text(x, .5, text, ha="center", va="center", bbox={"boxstyle": "round,pad=.8", "fc": "#d9edf7", "ec": "#31708f"})
    for x in [0.15, 0.39, 0.63]:
        ax.annotate("", xy=(x + .08, .5), xytext=(x, .5), arrowprops={"arrowstyle": "->", "lw": 1.5})
    ax.set_title("Figure 3: causal XORFLOW subsystem (schematic; not a full-chip claim)")
    save("figure3_architecture", fig)


if __name__ == "__main__":
    main()
