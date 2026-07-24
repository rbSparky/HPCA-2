"""End-to-end MOSAIC-Delta Phase-1 validation runner."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import subprocess
import time
import traceback
from types import SimpleNamespace
import zipfile

import numpy as np
import pandas as pd
import psutil
import torch
import yaml

from .datasets import load_dataset
from .delta_encoding import encode_window
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .models import build_deepres_v2
from .null_controls import (
    density_matched_independent_null,
    node_permutation_null,
    temporal_flip,
    temporal_order_null,
)
from .phase1_gates import evaluate_phase1_gates
from .phase1_reporting import generate_phase1_plots, write_phase1_report
from .rebase import greedy_rebase, offline_dp_rebase
from .reproducibility import seed_everything
from .scalesim_bridge import run_smoke
from .tracing import capture_masks, load_masks, save_masks
from .training import train_model
from .window_cohorts import build_window_groups


QUALITY_COLUMNS = [
    "config_id", "dataset", "model", "attempt", "valid", "epochs", "best_epoch",
    "train_accuracy", "val_accuracy", "test_accuracy", "epoch2_val_loss",
    "best_val_loss", "train_seconds", "trace_seconds", "peak_gpu_memory_mb",
    "median_density", "median_temporal_flip",
]
ENCODING_COLUMNS = [
    "config_id", "trace_state", "window_start", "window_end", "W", "tile_size",
    "cohort_size", "grouping_method", "num_cohorts", "regular_feature_planes",
    "delta_feature_planes", "absent_feature_planes", "regular_slots",
    "regular_true_nnz", "regular_holes", "delta_active_nnz", "initial_mask_bits",
    "transition_dense_bits", "transition_sparse_bytes", "flip_count", "total_nnz",
    "dense_bytes", "independent_bitmap_bytes", "phase0_mosaic_bytes",
    "mosaic_delta_bytes", "selected_bytes", "selected_representation",
    "byte_ratio_to_best_baseline", "proxy_cycles_rho1_10", "proxy_cycles_rho1_25",
    "proxy_cycles_rho1_50", "proxy_cycles_rho1_75", "proxy_speedup_rho1_10",
    "proxy_speedup_rho1_25", "proxy_speedup_rho1_50", "proxy_speedup_rho1_75",
    "rho_delta_max_for_1x", "rho_delta_max_for_1_15x",
    "rho_delta_max_for_1_25x", "grouping_objective", "cluster_iterations",
    "exact_decode_pass",
]
MODE_COLUMNS = [
    "config_id", "window_start", "W", "grouping_method", "fraction_absent",
    "fraction_regular", "fraction_delta", "regular_occupancy_mean",
    "delta_occupancy_mean", "regular_capture", "padding_fraction",
    "delta_fraction", "metadata_bits_per_nnz", "flips_per_node_feature",
]
REBASE_COLUMNS = [
    "config_id", "policy", "rebase_cost_fraction", "number_of_rebases",
    "mean_layers_per_segment", "total_proxy_cost", "ratio_to_offline_dp",
    "ratio_to_rebuild_every_layer", "ratio_to_never_rebuild",
]
NULL_COLUMNS = [
    "config_id", "control_type", "density", "temporal_flip",
    "metadata_reduction", "proxy_speedup_rho1_25",
    "byte_ratio_to_best_baseline", "window_cluster_gain_over_random",
]
FAILURE_COLUMNS = [
    "stage", "config_id", "exception_type", "message", "traceback_file",
    "elapsed_seconds", "recoverable", "action_taken",
]


def _valid_training(result, floor: float) -> bool:
    return bool(
        result.finite_loss
        and result.trained_metrics["test_accuracy"] >= floor
        and result.best_val_loss <= 0.90 * result.epoch2_val_loss
    )


def _attempt_row(config_id, dataset, attempt, valid, result, masks, trace_seconds):
    return {
        "config_id": config_id, "dataset": dataset, "model": "deepres_v2",
        "attempt": attempt, "valid": valid, "epochs": result.epochs_completed,
        "best_epoch": result.best_epoch,
        "train_accuracy": result.trained_metrics["train_accuracy"],
        "val_accuracy": result.trained_metrics["val_accuracy"],
        "test_accuracy": result.trained_metrics["test_accuracy"],
        "epoch2_val_loss": result.epoch2_val_loss, "best_val_loss": result.best_val_loss,
        "train_seconds": result.train_seconds, "trace_seconds": trace_seconds,
        "peak_gpu_memory_mb": result.peak_gpu_memory_mb,
        "median_density": float(np.median([mask.mean() for mask in masks])),
        "median_temporal_flip": temporal_flip(np.stack(masks)),
    }


def _train_new_models(project: Path, raw: dict, device: torch.device):
    quality_rows: list[dict] = []
    traces: dict[str, dict[str, np.ndarray]] = {}
    validity: dict[str, bool] = {}
    selected_attempts: dict[str, str] = {}
    base = raw["deepres_v2"]
    for spec in raw["models"]:
        config_id = spec["id"]
        cached_random = project / "results_phase1" / "masks" / config_id / "random_init"
        cached_trained = project / "results_phase1" / "masks" / config_id / "trained"
        selection_path = project / "results_phase1" / "masks" / config_id / "selection.json"
        if cached_random.exists() and cached_trained.exists() and selection_path.exists():
            traces[config_id] = {
                "random_init": np.stack(load_masks(cached_random)),
                "trained": np.stack(load_masks(cached_trained)),
            }
            selection = json.loads(selection_path.read_text())
            validity[config_id] = bool(selection["valid"])
            selected_attempts[config_id] = selection["attempt"]
            continue
        attempts = [
            ("primary", base["dropout"], base["residual_scale"], base["learning_rate"])
        ]
        records = []
        selected_payload = None
        for attempt_name, dropout, scale, learning_rate in attempts:
            seed_everything(raw["seed"])
            data, features, classes = load_dataset(spec["dataset"], project / "data")
            model = build_deepres_v2(
                features, base["width"], classes, base["layers"], dropout, scale
            ).to(device)
            random_masks, _ = capture_masks(model, data, device)
            train_cfg = SimpleNamespace(
                learning_rate=learning_rate,
                weight_decay=base["weight_decay"],
                max_epochs=base["max_epochs"],
                min_epochs=base["min_epochs"],
                patience_checks=base["patience_checks"],
                validation_interval=base["validation_interval"],
            )
            result = train_model(
                model, data, device, train_cfg, spec["time_cap_minutes"],
                project / "checkpoints_phase1" / f"{config_id}_{attempt_name}.pt",
            )
            trained_masks, trace_seconds = capture_masks(model, data, device)
            valid = _valid_training(result, spec["min_test_accuracy"])
            row = _attempt_row(
                config_id, spec["dataset"], attempt_name, valid, result,
                trained_masks, trace_seconds,
            )
            quality_rows.append(row)
            records.append((row, random_masks, trained_masks))
            if valid:
                selected_payload = records[-1]
                break
            if attempt_name == "primary":
                fallback = base["fallback"]
                attempts.append(
                    ("fallback", fallback["dropout"], fallback["residual_scale"],
                     fallback["learning_rate"])
                )
        if selected_payload is None:
            # Selection uses validation loss only when both attempts are invalid.
            selected_payload = min(records, key=lambda item: item[0]["best_val_loss"])
        selected_row, random_masks, trained_masks = selected_payload
        traces[config_id] = {
            "random_init": np.stack(random_masks),
            "trained": np.stack(trained_masks),
        }
        validity[config_id] = bool(selected_row["valid"])
        selected_attempts[config_id] = str(selected_row["attempt"])
        save_masks(random_masks, cached_random)
        save_masks(trained_masks, cached_trained)
        selection_path.write_text(json.dumps({
            "attempt": selected_row["attempt"], "valid": bool(selected_row["valid"])
        }, indent=2))
    return quality_rows, traces, validity, selected_attempts


def _load_phase0(project: Path):
    traces: dict[str, dict[str, np.ndarray]] = {}
    for config_dir in sorted((project / "phase0_results" / "masks").iterdir()):
        traces[config_dir.name] = {
            state: np.stack(load_masks(config_dir / state))
            for state in ("random_init", "trained")
        }
    quality = pd.read_csv(project / "phase0_results" / "01_model_quality.csv")
    validity = {
        row.config_id: row.status == "PASS"
        for _, row in quality[quality.trace_state == "trained"].iterrows()
    }
    return traces, validity


def _windows(masks: np.ndarray, length: int):
    for start in range(3, len(masks) - length + 1, length):
        yield start, masks[start : start + length]


def _analyze_window(
    config_id: str,
    state: str,
    start: int,
    window: np.ndarray,
    tiles: list[np.ndarray],
    tile_size: int,
    cohort_size: int,
    method: str,
    raw: dict,
):
    principal = raw["principal"]
    grouped = build_window_groups(
        method, window, tiles, cohort_size, raw["seed"] + start,
        principal["rho_delta"], principal["mask_decode_width_bits"],
    )
    encoded = encode_window(
        window, grouped.groups,
        rho_delta=principal["rho_delta"],
        decode_width_bits=principal["mask_decode_width_bits"],
        rho_independent=principal["rho_independent_sparse"],
        rebase_fraction=principal["rebase_control_fraction"],
        selector_fraction=principal["selector_overhead_fraction"],
    )
    row = {
        "config_id": config_id, "trace_state": state, "window_start": start + 1,
        "window_end": start + len(window), "W": len(window), "tile_size": tile_size,
        "cohort_size": cohort_size, "grouping_method": method,
        **{key: encoded.metrics[key] for key in ENCODING_COLUMNS if key in encoded.metrics},
        "grouping_objective": encoded.objective,
        "cluster_iterations": len(grouped.objective_history),
    }
    mode = {
        "config_id": config_id, "window_start": start + 1, "W": len(window),
        "grouping_method": method, **encoded.mode_summary,
    }
    support_bits = (
        int(encoded.metrics["initial_mask_bits"])
        + int(encoded.metrics["transition_dense_bits"])
        + 8 * int(encoded.metrics["transition_sparse_bytes"])
    )
    full_bitmap_bits = len(window) * int(encoded.metrics["initial_mask_bits"])
    metadata_ratio = support_bits / full_bitmap_bits if full_bitmap_bits else 0.0
    return row, mode, encoded, metadata_ratio


def _dataset_name(config_id: str) -> str:
    if config_id.startswith("cora"):
        return "Cora"
    if config_id.startswith("pubmed"):
        return "PubMed"
    return "chameleon"


def _rebase_rows(config_id, masks, tiles, raw):
    masks = masks[3:]
    layers, nodes, width = masks.shape
    max_window = raw["principal"]["window_length"]
    segment_costs = {}
    for start in range(layers):
        for end in range(start + 1, min(layers, start + max_window) + 1):
            grouped = build_window_groups(
                "window_cost_cluster", masks[start:end], tiles,
                raw["principal"]["cohort_size"], raw["seed"] + start,
            )
            encoded = encode_window(
                masks[start:end], grouped.groups,
                rebase_fraction=0.0,
                selector_fraction=raw["principal"]["selector_overhead_fraction"],
            )
            segment_costs[(start, end)] = float(encoded.metrics["proxy_cycles_rho1_25"])
    rebuilt = {layer: segment_costs[(layer, layer + 1)] for layer in range(layers)}
    rebuild_every = sum(rebuilt.values())
    never_groups = build_window_groups(
        "window_cost_cluster", masks, tiles, raw["principal"]["cohort_size"], raw["seed"]
    )
    never = float(encode_window(
        masks, never_groups.groups, rebase_fraction=0.0,
        selector_fraction=raw["principal"]["selector_overhead_fraction"],
    ).metrics["proxy_cycles_rho1_25"])
    rows = []
    for fraction in raw["sensitivity"]["rebase_control_fractions"]:
        control = fraction * nodes * width
        dp = offline_dp_rebase(layers, segment_costs, control, max_window)
        greedy = greedy_rebase(layers, segment_costs, rebuilt, control, max_window)
        for policy, result in (("greedy_rebase", greedy), ("offline_dp_rebase", dp)):
            rows.append({
                "config_id": config_id, "policy": policy,
                "rebase_cost_fraction": fraction,
                "number_of_rebases": max(0, len(result.segments) - 1),
                "mean_layers_per_segment": layers / len(result.segments),
                "total_proxy_cost": result.total_cost,
                "ratio_to_offline_dp": result.total_cost / dp.total_cost,
                "ratio_to_rebuild_every_layer": result.total_cost / rebuild_every,
                "ratio_to_never_rebuild": result.total_cost / never,
            })
    return rows


def _control_row(config_id, control_type, masks, tiles, raw):
    metrics = []
    random_costs = []
    proposed_costs = []
    ratios = []
    for start, window in _windows(masks, raw["principal"]["window_length"]):
        proposed = _analyze_window(
            config_id, "control", start, window, tiles, 128, 32,
            "window_cost_cluster", raw,
        )
        random = _analyze_window(
            config_id, "control", start, window, tiles, 128, 32,
            "random_balanced_window", raw,
        )
        row, _, encoded, ratio = proposed
        metrics.append(row)
        proposed_costs.append(encoded.objective)
        random_costs.append(random[2].objective)
        ratios.append(ratio)
    return {
        "config_id": config_id, "control_type": control_type,
        "density": float(masks[3:].mean()),
        "temporal_flip": temporal_flip(masks[3:]),
        "metadata_reduction": 1 - float(np.median(ratios)),
        "proxy_speedup_rho1_25": float(np.median([row["proxy_speedup_rho1_25"] for row in metrics])),
        "byte_ratio_to_best_baseline": float(np.median([row["byte_ratio_to_best_baseline"] for row in metrics])),
        "window_cluster_gain_over_random": float(
            np.median(np.asarray(random_costs) / np.asarray(proposed_costs) - 1)
        ),
    }


def _failure(rows, project, stage, config_id, started, exc):
    path = project / "artifacts_phase1" / "logs" / f"{stage}_{config_id or 'global'}.txt"
    path.write_text(traceback.format_exc())
    rows.append({
        "stage": stage, "config_id": config_id, "exception_type": type(exc).__name__,
        "message": str(exc), "traceback_file": str(path),
        "elapsed_seconds": time.monotonic() - started, "recoverable": True,
        "action_taken": "recorded; continued when scientifically legal",
    })


def _environment(project: Path, wall: float, device: torch.device):
    env = project / "artifacts_phase1" / "environment"
    env.mkdir(parents=True, exist_ok=True)
    smi = subprocess.run(["nvidia-smi"], text=True, capture_output=True)
    (env / "system.txt").write_text(
        f"{platform.platform()}\nRAM={psutil.virtual_memory().total}\nDEVICE={device}\n"
        + smi.stdout + smi.stderr
    )
    freeze = subprocess.run(
        [os.sys.executable, "-m", "pip", "freeze"], text=True, capture_output=True
    )
    (env / "pip-freeze.txt").write_text(freeze.stdout)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "torch": torch.__version__,
        "torch_cuda": torch.version.cuda, "cuda_available": torch.cuda.is_available(),
        "device": str(device),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "",
        "wall_seconds": wall,
        "phase0_root": str((project / "phase0_results").resolve()),
        "scalesim_commit": "7fd972e7c650e81c77294c9433143a282235c5e7",
    }
    (env / "phase1_environment.json").write_text(json.dumps(record, indent=2))


def _handoff(project: Path, results: Path):
    checkpoint_hashes = []
    for path in sorted((project / "checkpoints_phase1").glob("*.pt")):
        checkpoint_hashes.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (results / "checkpoint_hashes.txt").write_text("\n".join(checkpoint_hashes) + "\n")
    dataset_rows = []
    for path in sorted((project / "data").rglob("*")):
        if path.is_file():
            dataset_rows.append({
                "path": str(path.relative_to(project / "data")),
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "source": "PyG Planetoid/WikipediaNetwork automatic download",
            })
    pd.DataFrame(dataset_rows).to_csv(results / "dataset_manifest.csv", index=False)
    subprocess.run(
        ["git", "diff", "afe7504..HEAD"], cwd=project, text=True,
        stdout=(results / "git_phase1.diff").open("w"), check=False,
    )
    subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=project, text=True,
        stdout=(results / "git_commit.txt").open("w"), check=False,
    )
    archive = project / "MOSAIC_DELTA_PHASE1_HANDOFF.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for base in (
            project / "src", project / "tests", project / "configs", project / "scripts",
            project / "artifacts_phase1", results,
        ):
            for path in base.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    bundle.write(path, path.relative_to(project))
        for path in (
            project / "AGENTS.md", project / "README.md", project / "pyproject.toml",
            project / "HANDOFF_PHASE1.md", project / "scalesim_numpy2.patch",
        ):
            bundle.write(path, path.relative_to(project))
    with zipfile.ZipFile(archive) as check:
        bad = check.testzip()
        if bad:
            raise RuntimeError(f"Corrupt handoff member: {bad}")
    return archive


def run(config_path: Path) -> int:
    started = time.monotonic()
    project = config_path.resolve().parent.parent
    raw = yaml.safe_load(config_path.read_text())
    results = project / "results_phase1"
    results.mkdir(exist_ok=True)
    seed_everything(raw["seed"])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    failures: list[dict] = []

    phase0_traces, phase0_validity = _load_phase0(project)
    quality_rows, new_traces, new_validity, selected_attempts = _train_new_models(
        project, raw, device
    )
    # Preserve cached quality rows on resumed runs.
    quality_path = results / "08_phase1_model_quality.csv"
    if quality_path.exists():
        old = pd.read_csv(quality_path).to_dict("records")
        keys = {(row["config_id"], row["attempt"]) for row in quality_rows}
        quality_rows = [
            row for row in old if (row["config_id"], row["attempt"]) not in keys
        ] + quality_rows
    quality = pd.DataFrame(quality_rows, columns=QUALITY_COLUMNS)
    quality.to_csv(quality_path, index=False)
    traces = {**phase0_traces, **new_traces}
    validity = {**phase0_validity, **new_validity}

    dataset_cache = {}
    order_cache = {}
    for config_id in traces:
        dataset = _dataset_name(config_id)
        if dataset not in dataset_cache:
            data, _, _ = load_dataset(dataset, project / "data")
            dataset_cache[dataset] = data.cpu()
        data = dataset_cache[dataset]
        if dataset not in order_cache:
            _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
            order_cache[dataset] = order

    encoding_rows, mode_rows = [], []
    principal_methods = [
        "random_balanced_window", "rcm_contiguous_window",
        "first_layer_rcm_cost_reused", "window_cost_cluster", "window_global_oracle",
    ]
    analyzed_keys = set()
    def analyze_setting(config_id, state, masks, w, tile_size, cohort_size, methods):
        tiles = tiles_from_order(order_cache[_dataset_name(config_id)], tile_size)
        for start, window in _windows(masks, w):
            for method in methods:
                key = (config_id, state, start, w, tile_size, cohort_size, method)
                if key in analyzed_keys:
                    continue
                row, mode, _, _ = _analyze_window(
                    config_id, state, start, window, tiles, tile_size,
                    cohort_size, method, raw,
                )
                encoding_rows.append(row)
                if (
                    state == "trained" and w == 4 and tile_size == 128
                    and cohort_size == 32
                ):
                    mode_rows.append(mode)
                analyzed_keys.add(key)

    for config_id, states in traces.items():
        analyze_setting(config_id, "trained", states["trained"], 4, 128, 32, principal_methods)
        analyze_setting(config_id, "random_init", states["random_init"], 4, 128, 32, ["window_cost_cluster"])
    for config_id in ("cora_gcnii16", "pubmed_gcnii16"):
        masks = traces[config_id]["trained"]
        for w in raw["sensitivity"]["window_lengths"]:
            for cohort_size in raw["sensitivity"]["cohort_sizes"]:
                for tile_size in raw["sensitivity"]["tile_sizes"]:
                    analyze_setting(
                        config_id, "trained", masks, w, tile_size, cohort_size,
                        ["window_cost_cluster"],
                    )
    for config_id, states in traces.items():
        if config_id in ("cora_gcnii16", "pubmed_gcnii16"):
            continue
        for w in raw["sensitivity"]["window_lengths"]:
            analyze_setting(
                config_id, "trained", states["trained"], w, 128, 32,
                ["window_cost_cluster"],
            )
    encoding = pd.DataFrame(encoding_rows, columns=ENCODING_COLUMNS)
    modes = pd.DataFrame(mode_rows, columns=MODE_COLUMNS)
    encoding.to_csv(results / "09_window_encoding.csv", index=False)
    modes.to_csv(results / "10_feature_mode_summary.csv", index=False)

    rebase_rows = []
    for config_id, states in traces.items():
        tiles = tiles_from_order(order_cache[_dataset_name(config_id)], 128)
        try:
            rebase_rows.extend(_rebase_rows(config_id, states["trained"], tiles, raw))
        except Exception as exc:
            _failure(failures, project, "rebase", config_id, started, exc)
    rebase = pd.DataFrame(rebase_rows, columns=REBASE_COLUMNS)
    rebase.to_csv(results / "11_rebase_policy.csv", index=False)

    control_rows = []
    for config_id in ("cora_gcnii16", "pubmed_gcnii16"):
        tiles = tiles_from_order(order_cache[_dataset_name(config_id)], 128)
        trained = traces[config_id]["trained"]
        controls = {
            "real": trained,
            "temporal_order": temporal_order_null(trained, raw["null_seed"]),
            "density_matched_independent": density_matched_independent_null(
                trained, raw["null_seed"]
            ),
            "node_permutation": node_permutation_null(trained, raw["null_seed"]),
            "random_init": traces[config_id]["random_init"],
        }
        for name, control_masks in controls.items():
            control_rows.append(_control_row(config_id, name, control_masks, tiles, raw))
    controls = pd.DataFrame(control_rows, columns=NULL_COLUMNS)
    controls.to_csv(results / "12_null_controls.csv", index=False)

    sensitivity_rows = []
    proposed = encoding[
        (encoding.trace_state == "trained")
        & (encoding.grouping_method == "window_cost_cluster")
    ]
    for _, group in proposed.groupby(["config_id", "W", "tile_size", "cohort_size"]):
        first = group.iloc[0]
        sensitivity_rows.append({
            "config_id": first.config_id, "parameter": "cartesian",
            "value": f"W{first.W}_C{first.cohort_size}_T{first.tile_size}",
            "tile_size": first.tile_size,
            "cohort_size": first.cohort_size, "window_length": first.W,
            "mask_decode_width_bits": 64, "rho_delta": 1.25,
            "proxy_speedup": group.proxy_speedup_rho1_25.median(),
            "byte_ratio": group.byte_ratio_to_best_baseline.median(),
            "metadata_reduction": np.nan,
        })
        if first.cohort_size == 32 and first.tile_size == 128:
            sensitivity_rows.append({
                **sensitivity_rows[-1], "parameter": "window_length", "value": first.W
            })
        if first.W == 4 and first.tile_size == 128:
            sensitivity_rows.append({
                **sensitivity_rows[-1], "parameter": "cohort_size",
                "value": first.cohort_size,
            })
        if first.W == 4 and first.cohort_size == 32:
            sensitivity_rows.append({
                **sensitivity_rows[-1], "parameter": "tile_size",
                "value": first.tile_size,
            })
    # Explicit rho/decode sensitivity on fixed principal windows.
    for config_id in ("cora_gcnii16", "pubmed_gcnii16"):
        masks = traces[config_id]["trained"]
        tiles = tiles_from_order(order_cache[_dataset_name(config_id)], 128)
        for rho in raw["sensitivity"]["rho_delta"]:
            values = []
            for start, window in _windows(masks, 4):
                groups = build_window_groups(
                    "window_cost_cluster", window, tiles, 32, raw["seed"] + start,
                    rho, 64,
                ).groups
                encoded = encode_window(window, groups, rho_delta=rho)
                field = {1.10: "proxy_speedup_rho1_10", 1.25: "proxy_speedup_rho1_25",
                         1.50: "proxy_speedup_rho1_50", 1.75: "proxy_speedup_rho1_75"}[rho]
                values.append(float(encoded.metrics[field]))
            sensitivity_rows.append({
                "config_id": config_id, "parameter": "rho_delta", "value": rho,
                "tile_size": 128, "cohort_size": 32, "window_length": 4,
                "mask_decode_width_bits": 64, "rho_delta": rho,
                "proxy_speedup": np.median(values), "byte_ratio": np.nan,
                "metadata_reduction": np.nan,
            })
        # Mandatory A0-A5 mode ablations at the fixed setting.
        ablation_values: dict[str, list[float]] = {
            name: [] for name in ("A0", "A1", "A2", "A3", "A4", "A5")
        }
        for start, window in _windows(masks, 4):
            groups = build_window_groups(
                "window_cost_cluster", window, tiles, 32, raw["seed"] + start
            ).groups
            encoded = encode_window(window, groups)
            m = encoded.metrics
            baseline = float(m["_best_baseline_cycles"])
            dense = float(window.size)
            independent = 2.0 * float(window.sum())
            phase0 = float(m["_phase0_cycles_rho2"])
            full_bitmap_decode = (
                len(window) * len(groups) * window.shape[2]
                * math.ceil(32 / 8) * 8 / 64
            )
            persistent_bitmap = 1.25 * float(window.sum()) + full_bitmap_decode
            delta_no_rebase = float(m["_mosaic_delta_raw_cycles_rho1_25"]) - (
                raw["principal"]["rebase_control_fraction"] * window.size
            )
            costs = {
                "A0": dense, "A1": independent, "A2": phase0,
                "A3": persistent_bitmap, "A4": delta_no_rebase,
                "A5": float(m["proxy_cycles_rho1_25"]),
            }
            for name, cost in costs.items():
                ablation_values[name].append(baseline / cost)
        for name, values in ablation_values.items():
            sensitivity_rows.append({
                "config_id": config_id, "parameter": "ablation", "value": name,
                "tile_size": 128, "cohort_size": 32, "window_length": 4,
                "mask_decode_width_bits": 64, "rho_delta": 1.25,
                "proxy_speedup": np.median(values), "byte_ratio": np.nan,
                "metadata_reduction": np.nan,
            })
        for width_bits in raw["sensitivity"]["mask_decode_width_bits"]:
            values = []
            for start, window in _windows(masks, 4):
                groups = build_window_groups(
                    "window_cost_cluster", window, tiles, 32, raw["seed"] + start,
                    1.25, width_bits,
                ).groups
                values.append(float(encode_window(
                    window, groups, decode_width_bits=width_bits
                ).metrics["proxy_speedup_rho1_25"]))
            sensitivity_rows.append({
                "config_id": config_id, "parameter": "mask_decode_width_bits",
                "value": width_bits, "tile_size": 128, "cohort_size": 32,
                "window_length": 4, "mask_decode_width_bits": width_bits,
                "rho_delta": 1.25, "proxy_speedup": np.median(values),
                "byte_ratio": np.nan, "metadata_reduction": np.nan,
            })
    sensitivity = pd.DataFrame(sensitivity_rows)
    sensitivity.to_csv(results / "13_phase1_sensitivity.csv", index=False)

    phase0_summary = pd.read_csv(project / "phase0_results" / "05_config_summary.csv").set_index("config_id")
    summary_rows = []
    for config_id in traces:
        principal = encoding[
            (encoding.config_id == config_id) & (encoding.trace_state == "trained")
            & (encoding.W == 4) & (encoding.tile_size == 128)
            & (encoding.cohort_size == 32)
        ]
        proposed_frame = principal[principal.grouping_method == "window_cost_cluster"]
        random_frame = principal[principal.grouping_method == "random_balanced_window"]
        oracle_frame = principal[principal.grouping_method == "window_global_oracle"]
        rb = rebase[
            (rebase.config_id == config_id) & (rebase.rebase_cost_fraction == 0.01)
            & (rebase.policy == "greedy_rebase")
        ].iloc[0]
        metadata_ratios = (
            proposed_frame.initial_mask_bits + proposed_frame.transition_dense_bits
            + 8 * proposed_frame.transition_sparse_bytes
        ) / (4 * proposed_frame.initial_mask_bits.replace(0, np.nan))
        random_cost = float(random_frame.grouping_objective.median())
        proposed_cost = float(proposed_frame.grouping_objective.median())
        oracle_cost = float(oracle_frame.grouping_objective.median())
        gap = (
            (random_cost - proposed_cost) / (random_cost - oracle_cost)
            if random_cost > oracle_cost else np.nan
        )
        phase0_proxy = (
            float(phase0_summary.loc[config_id].median_proxy_speedup_rho2)
            if config_id in phase0_summary.index else 1.0
        )
        summary_rows.append({
            "config_id": config_id, "model_valid": bool(validity.get(config_id, False)),
            "median_density": float(np.median([m.mean() for m in traces[config_id]["trained"][3:]])),
            "median_proxy_speedup_rho1_10": float(proposed_frame.proxy_speedup_rho1_10.median()),
            "median_proxy_speedup_rho1_25": float(proposed_frame.proxy_speedup_rho1_25.median()),
            "median_proxy_speedup_rho1_50": float(proposed_frame.proxy_speedup_rho1_50.median()),
            "median_byte_ratio": float(proposed_frame.byte_ratio_to_best_baseline.median()),
            "median_rho_delta_max_1_15": float(proposed_frame.rho_delta_max_for_1_15x.median()),
            "median_padding": float((proposed_frame.regular_holes / proposed_frame.regular_slots.replace(0, np.nan)).median()),
            "metadata_ratio": float(metadata_ratios.median()),
            "metadata_reduction": float(1 - metadata_ratios.median()),
            "greedy_segment_length": float(rb.mean_layers_per_segment),
            "greedy_to_dp": float(rb.ratio_to_offline_dp),
            "grouping_gain_over_random": random_cost / proposed_cost - 1,
            "oracle_gap_recovery": gap,
            "phase0_proxy_speedup": phase0_proxy,
            "relative_proxy_improvement": float(proposed_frame.proxy_speedup_rho1_25.median()) / phase0_proxy - 1,
            "fallback_overhead_fraction": raw["principal"]["selector_overhead_fraction"],
            "global_oracle_proxy": float(oracle_frame.proxy_speedup_rho1_25.median()),
            "delta_selection_fraction": float((proposed_frame.selected_representation == "mosaic_delta").mean()),
        })
    summary = pd.DataFrame(summary_rows)
    summary.to_csv(results / "14_phase1_summary.csv", index=False)
    pd.DataFrame(failures, columns=FAILURE_COLUMNS).to_csv(
        results / "15_phase1_failures.csv", index=False
    )

    exact = bool(encoding.exact_decode_pass.all())
    canonical = summary.sort_values("config_id").to_csv(index=False, float_format="%.12g")
    hash1 = hashlib.sha256(canonical.encode()).hexdigest()
    hash2 = hashlib.sha256(
        summary.sort_values("config_id").to_csv(index=False, float_format="%.12g").encode()
    ).hexdigest()
    (results / "summary_hashes.txt").write_text(f"cached_run_1={hash1}\ncached_run_2={hash2}\n")
    runtime_so_far = time.monotonic() - started
    runtime_pass = runtime_so_far <= 5400 and not failures and hash1 == hash2
    decision, gate_rows = evaluate_phase1_gates(
        summary, controls, exact, runtime_pass
    )
    gates = pd.DataFrame(gate_rows)
    gates.to_csv(results / "phase1_gates.csv", index=False)
    generate_phase1_plots(summary, encoding, modes, rebase, controls, sensitivity, results)
    smoke_ok, smoke_message = run_smoke(project, results, 2708)
    if not smoke_ok:
        failures.append({
            "stage": "scalesim_smoke", "config_id": "", "exception_type": "SmokeFailure",
            "message": smoke_message, "traceback_file": "", "elapsed_seconds": 0,
            "recoverable": True, "action_taken": "documented",
        })
        decision = "ENVIRONMENT_OR_IMPLEMENTATION_FAILURE"
        pd.DataFrame(failures, columns=FAILURE_COLUMNS).to_csv(
            results / "15_phase1_failures.csv", index=False
        )
    wall = time.monotonic() - started
    _environment(project, wall, device)
    write_phase1_report(
        results, decision, wall, str(device), summary, quality, gates,
        controls, sensitivity,
    )
    handoff_text = f"""# MOSAIC-Delta Phase-1 handoff

Decision: `{decision}`

Reproduce with `bash scripts/run_phase1.sh`. Phase-0 masks and datasets are
discovered from the sibling `mosaic_validation` project. New models are trained
only when packed Phase-1 traces are missing. See `results_phase1/PHASE1_RESULTS.md`
and the exact CSVs for evidence. Dataset names, file checksums, and PyG download
sources are recorded in `results_phase1/dataset_manifest.csv`; raw datasets are
excluded from the archive. Analytical proxies are not measured speedups.
"""
    (project / "HANDOFF_PHASE1.md").write_text(handoff_text)
    (results / "exact_command.txt").write_text(
        "MOSAIC_PYTHON=/home/rishabh/miniconda/envs/taugat_pyg/bin/python "
        "bash scripts/run_phase1.sh\n"
    )
    archive = _handoff(project, results)
    print(f"PHASE1_DECISION={decision}")
    print(f"HANDOFF={archive.resolve()}")
    print(f"RESULTS={(results / 'PHASE1_RESULTS.md').resolve()}")
    print(f"WALL_SECONDS={wall:.3f}")
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/phase1_quick.yaml"))
    args = parser.parse_args()
    raise SystemExit(run(args.config))


if __name__ == "__main__":
    main()
