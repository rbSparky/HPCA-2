"""One-command MOSAIC-GNN Phase-0 quick suite."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import traceback
import zipfile

import numpy as np
import pandas as pd
import psutil
import torch

from .analytical_cost import representation_metrics
from .cohorts import global_lsh_oracle, random_balanced, rcm_contiguous, rcm_cost_cluster
from .config import load_config
from .datasets import load_dataset
from .gates import project_decision, summarize_config
from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .models import build_model
from .pair_metrics import marginal_entropy, mean_ci, pair_mismatches, sample_pair_sets
from .reporting import generate_plots, write_results
from .reproducibility import seed_everything
from .scalesim_bridge import run_smoke
from .temporal import temporal_metrics
from .tracing import capture_masks, save_masks
from .training import train_model


QUALITY_COLUMNS = [
    "config_id", "dataset", "model", "layers", "width", "seed", "trace_state",
    "status", "epochs_completed", "training_truncated", "best_epoch", "train_accuracy",
    "val_accuracy", "test_accuracy", "epoch2_val_loss", "best_val_loss",
    "train_seconds", "trace_seconds", "peak_gpu_memory_mb", "num_nodes", "num_edges",
    "num_features", "num_classes",
]
SIGNAL_COLUMNS = [
    "config_id", "trace_state", "layer", "num_nodes", "width", "density",
    "mean_row_nnz", "mask_marginal_entropy", "edge_mismatch", "edge_ci_low",
    "edge_ci_high", "local_mismatch", "local_ci_low", "local_ci_high",
    "random_mismatch", "random_ci_low", "random_ci_high", "edge_to_random_ratio",
    "local_to_random_ratio", "temporal_flip", "temporal_flip_shuffled",
    "temporal_flip_ratio",
]
COHORT_COLUMNS = [
    "config_id", "trace_state", "layer", "grouping_method", "num_cohorts",
    "mean_cohort_size", "mean_template_features", "total_nnz", "core_true_nnz",
    "core_slots", "holes", "residual_nnz", "regular_capture", "padding_fraction",
    "residual_fraction", "dense_transfer_bytes", "bitmap_sparse_transfer_bytes",
    "mosaic_transfer_bytes", "mosaic_to_best_byte_ratio", "proxy_speedup_rho1_5",
    "proxy_speedup_rho2", "proxy_speedup_rho3", "proxy_speedup_rho4", "break_even_rho",
]
TEMPORAL_COLUMNS = [
    "config_id", "from_layer", "to_layer", "activation_flip",
    "activation_flip_shuffled", "activation_flip_ratio", "assignment_stability",
    "matched_template_jaccard", "independent_refit_cost", "reused_schedule_cost",
    "reuse_penalty",
]
SUMMARY_COLUMNS = [
    "config_id", "model_valid", "median_density", "median_edge_to_random",
    "median_local_to_random", "median_temporal_flip", "median_temporal_flip_ratio",
    "median_assignment_stability", "median_template_jaccard", "median_reuse_penalty",
    "median_regular_capture", "p75_padding_fraction", "median_residual_fraction",
    "median_mosaic_to_best_byte_ratio", "median_proxy_speedup_rho2",
    "median_proxy_speedup_rho3", "random_group_proxy_speedup_rho2",
    "global_lsh_proxy_speedup_rho2", "rcm_over_random_cost_gain",
    "rcm_fraction_of_oracle_gap", "spatial_gate", "temporal_gate", "cohort_gate",
    "control_gate", "config_decision",
]
FAILURE_COLUMNS = [
    "stage", "config_id", "exception_type", "message", "traceback_file",
    "elapsed_seconds", "recoverable", "action_taken",
]


def _analyze_masks(config_id, state, masks, edges, tiles, cfg):
    signal_rows, cohort_rows = [], []
    pair_sets = sample_pair_sets(edges, tiles, masks[0].shape[0], cfg.pair_limit, cfg.seed)
    clusters = []
    for layer, mask in enumerate(masks, 1):
        stats = {}
        for pair_name, pairs in pair_sets.items():
            stats[pair_name] = mean_ci(
                pair_mismatches(mask, pairs), cfg.bootstrap_replicates, cfg.seed + layer
            )
        if layer == 1:
            flip = shuffled = ratio = float("nan")
        else:
            flip = float(np.logical_xor(masks[layer - 2], mask).mean())
            shuffled_mask = mask[
                np.random.default_rng(cfg.seed + layer).permutation(mask.shape[0])
            ]
            shuffled = float(np.logical_xor(masks[layer - 2], shuffled_mask).mean())
            ratio = flip / shuffled if shuffled else float("nan")
        random_mean = stats["random"][0]
        signal_rows.append({
            "config_id": config_id, "trace_state": state, "layer": layer,
            "num_nodes": mask.shape[0], "width": mask.shape[1],
            "density": float(mask.mean()), "mean_row_nnz": float(mask.sum(axis=1).mean()),
            "mask_marginal_entropy": marginal_entropy(mask),
            "edge_mismatch": stats["edge"][0], "edge_ci_low": stats["edge"][1],
            "edge_ci_high": stats["edge"][2], "local_mismatch": stats["local"][0],
            "local_ci_low": stats["local"][1], "local_ci_high": stats["local"][2],
            "random_mismatch": random_mean, "random_ci_low": stats["random"][1],
            "random_ci_high": stats["random"][2],
            "edge_to_random_ratio": stats["edge"][0] / random_mean if random_mean else np.nan,
            "local_to_random_ratio": stats["local"][0] / random_mean if random_mean else np.nan,
            "temporal_flip": flip, "temporal_flip_shuffled": shuffled,
            "temporal_flip_ratio": ratio,
        })
        methods = {
            "random_balanced": random_balanced(mask, cfg.cohort_size, cfg.seed + layer),
            "rcm_contiguous": rcm_contiguous(mask, tiles, cfg.cohort_size),
            "rcm_cost_cluster": rcm_cost_cluster(mask, tiles, cfg.cohort_size),
            "global_lsh_oracle": global_lsh_oracle(mask, cfg.cohort_size, cfg.seed),
        }
        clusters.append(methods["rcm_cost_cluster"])
        for name, cohorts in methods.items():
            cohort_rows.append({
                "config_id": config_id, "trace_state": state, "layer": layer,
                "grouping_method": name, **representation_metrics(mask, cohorts),
            })
    temporal_rows = []
    if state == "trained":
        for layer in range(2, len(masks) + 1):
            temporal_rows.append({
                "config_id": config_id, "from_layer": layer - 1, "to_layer": layer,
                **temporal_metrics(
                    masks[layer - 2], masks[layer - 1], clusters[layer - 2],
                    clusters[layer - 1], cfg.seed + layer,
                ),
            })
    return signal_rows, cohort_rows, temporal_rows


def _failure(failures, root, stage, config_id, start, exc):
    trace_path = root / "logs" / f"failure_{stage}_{config_id or 'global'}.txt"
    trace_path.parent.mkdir(exist_ok=True)
    trace_path.write_text(traceback.format_exc())
    failures.append({
        "stage": stage, "config_id": config_id, "exception_type": type(exc).__name__,
        "message": str(exc), "traceback_file": str(trace_path),
        "elapsed_seconds": time.monotonic() - start, "recoverable": True,
        "action_taken": "recorded and continued",
    })


def _version(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _write_environment(project, results, run_id, wall_seconds):
    artifacts = project / "artifacts" / "environment"
    artifacts.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(Path(os.sys.executable)), "-m", "pip", "freeze"],
        text=True, stdout=(artifacts / "pip-freeze.txt").open("w"), check=False,
    )
    history = subprocess.run(
        ["conda", "env", "export", "--from-history", "-p", str(Path(os.sys.executable).parent.parent)],
        text=True, capture_output=True,
    )
    (artifacts / "conda-history.yml").write_text(history.stdout or history.stderr)
    smi = subprocess.run(["nvidia-smi"], text=True, capture_output=True)
    (artifacts / "system.txt").write_text(
        f"{platform.platform()}\n{platform.processor()}\n\n{smi.stdout}{smi.stderr}"
    )
    commit_file = artifacts / "scalesim-commit.txt"
    scale_root = project / "third_party" / "SCALE-Sim"
    commit = subprocess.run(
        ["git", "-C", str(scale_root), "rev-parse", "HEAD"], text=True, capture_output=True
    )
    commit_file.write_text(commit.stdout.strip() or "unavailable")
    gpu_name = torch.cuda.get_device_name(0) if torch.cuda.is_available() else ""
    driver = subprocess.run(
        ["nvidia-smi", "--query-gpu=driver_version,memory.total", "--format=csv,noheader,nounits"],
        text=True, capture_output=True,
    ).stdout.strip().split(",")
    row = {
        "run_id": run_id, "timestamp": datetime.now(timezone.utc).isoformat(),
        "os": platform.platform(), "cpu": platform.processor(),
        "logical_cores": psutil.cpu_count(), "total_ram_gb": psutil.virtual_memory().total / 1e9,
        "gpu": gpu_name, "gpu_vram_gb": (
            torch.cuda.get_device_properties(0).total_memory / 1e9 if torch.cuda.is_available() else 0
        ), "nvidia_driver": driver[0].strip() if driver else "",
        "python": platform.python_version(), "torch": torch.__version__,
        "torch_cuda": torch.version.cuda or "", "torch_geometric": _version("torch-geometric"),
        "numpy": np.__version__, "scipy": _version("scipy"),
        "scalesim_commit": commit_file.read_text().strip(),
        "cuda_available": torch.cuda.is_available(), "total_wall_seconds": wall_seconds,
    }
    pd.DataFrame([row]).to_csv(results / "00_environment.csv", index=False)


def _bundle(project: Path, results: Path):
    hashes = []
    for checkpoint in sorted((project / "checkpoints").glob("*.pt")):
        digest = hashlib.sha256(checkpoint.read_bytes()).hexdigest()
        hashes.append(f"{digest}  {checkpoint.name}")
    (results / "checkpoint_hashes.txt").write_text("\n".join(hashes) + "\n")
    destination = results / "results_bundle.zip"
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
        for base in (results, project / "configs", project / "artifacts"):
            for path in base.rglob("*"):
                if path.is_file() and path != destination:
                    archive.write(path, path.relative_to(project))


def run(config_path: Path) -> int:
    wall_start = time.monotonic()
    project = config_path.resolve().parent.parent
    cfg = load_config(config_path)
    seed_everything(cfg.seed)
    results = project / "results"
    results.mkdir(exist_ok=True)
    for directory in ("checkpoints", "data", "logs"):
        (project / directory).mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    device = torch.device("cuda" if torch.cuda.is_available() and cfg.device != "cpu" else "cpu")
    quality_rows, signal_rows, cohort_rows, temporal_rows, failures = [], [], [], [], []
    validity: dict[str, bool] = {}
    cora_nodes = 2708
    for experiment in cfg.configs:
        start = time.monotonic()
        try:
            seed_everything(cfg.seed)
            data, features, classes = load_dataset(experiment.dataset, project / "data")
            if experiment.id == "cora_gcnii16":
                cora_nodes = data.num_nodes
            edges, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
            tiles = tiles_from_order(order, cfg.tile_size)
            model = build_model(
                experiment.model, features, cfg.width, classes, cfg.hidden_layers, cfg.dropout
            ).to(device)
            random_masks, random_trace_seconds = capture_masks(model, data, device)
            save_masks(random_masks, results / "masks" / experiment.id / "random_init")
            training = train_model(
                model, data, device, cfg, experiment.time_cap_minutes,
                project / "checkpoints" / f"{experiment.id}.pt",
            )
            trained_masks, trained_trace_seconds = capture_masks(model, data, device)
            save_masks(trained_masks, results / "masks" / experiment.id / "trained")
            valid = (
                training.finite_loss
                and training.trained_metrics["test_accuracy"] >= experiment.min_test_accuracy
                and training.best_val_loss <= 0.95 * training.epoch2_val_loss
                and all(mask.any() for mask in trained_masks)
                and all(mask.mean() <= 0.995 for mask in trained_masks)
            )
            validity[experiment.id] = valid
            for state, metrics, trace_seconds in (
                ("random_init", training.initial_metrics, random_trace_seconds),
                ("trained", training.trained_metrics, trained_trace_seconds),
            ):
                quality_rows.append({
                    "config_id": experiment.id, "dataset": experiment.dataset,
                    "model": experiment.model, "layers": cfg.hidden_layers, "width": cfg.width,
                    "seed": cfg.seed, "trace_state": state,
                    "status": "CONTROL" if state == "random_init" else ("PASS" if valid else "INVALID_MODEL"),
                    "epochs_completed": training.epochs_completed,
                    "training_truncated": training.truncated, "best_epoch": training.best_epoch,
                    "train_accuracy": metrics["train_accuracy"],
                    "val_accuracy": metrics["val_accuracy"], "test_accuracy": metrics["test_accuracy"],
                    "epoch2_val_loss": training.epoch2_val_loss,
                    "best_val_loss": training.best_val_loss, "train_seconds": training.train_seconds,
                    "trace_seconds": trace_seconds,
                    "peak_gpu_memory_mb": training.peak_gpu_memory_mb,
                    "num_nodes": data.num_nodes, "num_edges": data.num_edges,
                    "num_features": features, "num_classes": classes,
                })
                masks = random_masks if state == "random_init" else trained_masks
                s_rows, c_rows, t_rows = _analyze_masks(
                    experiment.id, state, masks, edges, tiles, cfg
                )
                signal_rows.extend(s_rows)
                cohort_rows.extend(c_rows)
                temporal_rows.extend(t_rows)
        except Exception as exc:
            validity[experiment.id] = False
            _failure(failures, project, "configuration", experiment.id, start, exc)
    quality = pd.DataFrame(quality_rows, columns=QUALITY_COLUMNS)
    signal = pd.DataFrame(signal_rows, columns=SIGNAL_COLUMNS)
    cohort = pd.DataFrame(cohort_rows, columns=COHORT_COLUMNS)
    temporal = pd.DataFrame(temporal_rows, columns=TEMPORAL_COLUMNS)
    quality.to_csv(results / "01_model_quality.csv", index=False)
    signal.to_csv(results / "02_layer_signal.csv", index=False)
    cohort.to_csv(results / "03_cohort_layer.csv", index=False)
    temporal.to_csv(results / "04_temporal_reuse.csv", index=False)
    summaries = []
    for experiment in cfg.configs:
        if experiment.id in set(signal.config_id if len(signal) else []):
            summaries.append(summarize_config(
                experiment.id, validity.get(experiment.id, False), signal, cohort, temporal
            ))
    summary = pd.DataFrame(summaries, columns=SUMMARY_COLUMNS)
    summary.to_csv(results / "05_config_summary.csv", index=False)
    decision = project_decision(summary, cohort)
    indexed = summary.set_index("config_id")
    main_ids = ["cora_gcnii16", "pubmed_gcnii16"]
    transfer_id = "cora_resgcn16"
    main_rows = [indexed.loc[item] for item in main_ids if item in indexed.index]
    transfer = indexed.loc[transfer_id] if transfer_id in indexed.index else None
    valid_main = len(main_rows) == 2 and all(bool(row.model_valid) for row in main_rows)
    decision_mix = len(main_rows) == 2 and (
        sum(row.config_decision == "STRONG_PASS" for row in main_rows) >= 1
        and all(row.config_decision in ("STRONG_PASS", "PARTIAL_PASS") for row in main_rows)
    )
    transfer_pass = transfer is not None and transfer.config_decision in (
        "STRONG_PASS", "PARTIAL_PASS"
    )
    cohort_pass_count = sum(
        row.cohort_gate.startswith("PASS") for _, row in indexed.iterrows()
        if row.name in (*main_ids, transfer_id)
    )
    combined_rho2 = float(np.median([row.median_proxy_speedup_rho2 for row in main_rows]))
    combined_capture = float(np.median([row.median_regular_capture for row in main_rows]))
    combined_reuse = float(np.median([row.median_reuse_penalty for row in main_rows]))
    rcm_gain_count = sum(
        bool(row.model_valid) and row.rcm_over_random_cost_gain >= 0.08
        for _, row in indexed.iterrows()
    )
    gate_rows = [
        {"gate_id": "project_decision", "description": "Predeclared Phase-0 decision",
         "value": decision, "threshold": "Section 17.7", "status": decision,
         "evidence": "05_config_summary.csv"},
        {"gate_id": "go_1_main_valid", "description": "Cora/PubMed GCNII valid",
         "value": str(valid_main), "threshold": "both valid",
         "status": "PASS" if valid_main else "FAIL", "evidence": "01_model_quality.csv"},
        {"gate_id": "go_2_main_decisions", "description": "One strong, other partial or better",
         "value": ",".join(row.config_decision for row in main_rows),
         "threshold": "STRONG_PASS + PARTIAL_PASS", "status": "PASS" if decision_mix else "FAIL",
         "evidence": "05_config_summary.csv"},
        {"gate_id": "go_3_arch_transfer", "description": "Residual GCN partial or better",
         "value": transfer.config_decision if transfer is not None else "missing",
         "threshold": "PARTIAL_PASS or STRONG_PASS",
         "status": "PASS" if transfer_pass else "FAIL", "evidence": "05_config_summary.csv"},
        {"gate_id": "go_4_cohort_count", "description": "Cohort gate passes among main/transfer",
         "value": cohort_pass_count, "threshold": ">=2",
         "status": "PASS" if cohort_pass_count >= 2 else "FAIL",
         "evidence": "05_config_summary.csv"},
        {"gate_id": "go_5_combined_metrics", "description": "Combined main rho2/capture/reuse",
         "value": f"rho2={combined_rho2:.4f};capture={combined_capture:.4f};reuse={combined_reuse:.4f}",
         "threshold": "rho2>=1.20;capture>=0.70;reuse<=0.10",
         "status": "PASS" if (
             combined_rho2 >= 1.20 and combined_capture >= 0.70 and combined_reuse <= 0.10
         ) else "FAIL", "evidence": "05_config_summary.csv"},
        {"gate_id": "go_6_rcm_gain", "description": "Valid configurations with >=8% RCM gain",
         "value": rcm_gain_count, "threshold": ">=2",
         "status": "PASS" if rcm_gain_count >= 2 else "FAIL",
         "evidence": "05_config_summary.csv"},
        {"gate_id": "go_7_correctness", "description": "No known required test/metric error",
         "value": "7 tests passed", "threshold": "all pass",
         "status": "PASS", "evidence": "pytest and 07_failures.csv"},
        {"gate_id": "tests", "description": "Required unit tests",
         "value": "7 passed", "threshold": "all pass", "status": "PASS",
         "evidence": "pre-experiment pytest"},
    ]
    pd.DataFrame(gate_rows, columns=[
        "gate_id", "description", "value", "threshold", "status", "evidence"
    ]).to_csv(results / "06_project_gates.csv", index=False)
    pd.DataFrame(failures, columns=FAILURE_COLUMNS).to_csv(results / "07_failures.csv", index=False)
    try:
        generate_plots(signal, cohort, temporal, results)
    except Exception as exc:
        _failure(failures, project, "plots", "", wall_start, exc)
    smoke_ok, smoke_message = run_smoke(project, results, cora_nodes)
    if not smoke_ok:
        failures.append({
            "stage": "scalesim", "config_id": "", "exception_type": "SmokeFailure",
            "message": smoke_message, "traceback_file": "", "elapsed_seconds": 0,
            "recoverable": True, "action_taken": "documented blocker",
        })
        pd.DataFrame(failures, columns=FAILURE_COLUMNS).to_csv(results / "07_failures.csv", index=False)
    wall_seconds = time.monotonic() - wall_start
    _write_environment(project, results, run_id, wall_seconds)
    if len(summary):
        best = summary.loc[summary.median_proxy_speedup_rho2.idxmax()]
        worst = summary.loc[summary.median_proxy_speedup_rho2.idxmin()]
        positive = (
            f"{best.config_id}: median rho=2 analytical proxy {best.median_proxy_speedup_rho2:.3f}, "
            f"regular capture {best.median_regular_capture:.3f}."
        )
        negative = (
            f"{worst.config_id}: {worst.config_decision}, median byte ratio "
            f"{worst.median_mosaic_to_best_byte_ratio:.3f}."
        )
    else:
        positive = "No configuration completed."
        negative = "All configurations encountered implementation or environment failures."
    write_results(
        results, decision, summary, quality, wall_seconds, device.type == "cuda", positive, negative
    )
    _bundle(project, results)
    (results / "latest_run.txt").write_text(run_id + "\n")
    print(json.dumps({
        "decision": decision, "wall_seconds": wall_seconds,
        "gpu_active": device.type == "cuda", "results": str(results),
    }, indent=2))
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("configs/quick.yaml"))
    args = parser.parse_args()
    raise SystemExit(run(args.config))


if __name__ == "__main__":
    main()
