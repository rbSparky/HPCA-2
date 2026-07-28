"""Reproducible training and exact inference tracing for HPCA workloads."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import time

import numpy as np
import torch

from .datasets import load_dataset
from .int8_validation import classification_accuracy, make_int8_model
from .models import build_deepres_v2
from .hpca_sparse import IncomingCsrSampler, deepres_csr_forward, normalized_csr_adjacency


@dataclass(frozen=True)
class WorkloadConfig:
    dataset: str
    config_id: str
    seed: int = 7
    width: int = 128
    layers: int = 8
    dropout: float = .20
    residual_scale: float = .20
    learning_rate: float = .005
    weight_decay: float = .0005
    max_epochs: int = 160
    min_epochs: int = 50
    patience: int = 25
    sampled_batches_per_epoch: int = 24
    sampled_neighbors: int = 2
    sampled_batch_size: int = 128
    csr_checkpoint_training: bool = False
    multi_label_pos_weight: bool = False


def _seed(value: int) -> None:
    torch.manual_seed(value)
    np.random.seed(value)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(value)


def _single_label_metrics(logits: torch.Tensor, data) -> dict[str, float]:
    result: dict[str, float] = {}
    for split in ("train", "val", "test"):
        mask = getattr(data, f"{split}_mask")
        result[f"{split}_loss"] = float(torch.nn.functional.cross_entropy(logits[mask], data.y[mask]))
        result[f"{split}_accuracy"] = float((logits[mask].argmax(1) == data.y[mask]).float().mean())
    return result


def _multi_label_metrics(logits: torch.Tensor, data) -> dict[str, float]:
    """Return BCE loss and global micro-F1 with the fixed zero-logit threshold.

    Yelp is multi-label.  A fixed threshold is part of the numerical contract;
    it is never selected from activation sparsity or a test split.
    """
    result: dict[str, float] = {}
    labels = data.y.to(dtype=logits.dtype)
    for split in ("train", "val", "test"):
        mask = getattr(data, f"{split}_mask")
        selected_logits = logits[mask]
        selected_labels = labels[mask]
        result[f"{split}_loss"] = float(torch.nn.functional.binary_cross_entropy_with_logits(selected_logits, selected_labels))
        predicted = selected_logits > 0
        truth = selected_labels > 0.5
        true_positive = int((predicted & truth).sum())
        false_positive = int((predicted & ~truth).sum())
        false_negative = int((~predicted & truth).sum())
        result[f"{split}_micro_f1"] = (2.0 * true_positive) / max(2 * true_positive + false_positive + false_negative, 1)
    return result


def train_and_trace(project: Path, config: WorkloadConfig, *, force_cpu: bool = False) -> dict:
    """Train DeepResV2 and store exact FP8 support traces for one workload.

    Single-label workloads use cross entropy/accuracy.  Multi-label Yelp uses
    BCE-with-logits/micro-F1 under the same causal training and tracing path.
    """
    _seed(config.seed)
    data, features, classes = load_dataset(config.dataset, project / "data")
    multi_label = data.y.ndim != 1
    device = torch.device("cpu" if force_cpu or not torch.cuda.is_available() else "cuda")
    model = build_deepres_v2(features, config.width, classes, config.layers, config.dropout, config.residual_scale).to(device)
    # Full edge-index message passing creates an edge-sized intermediate on
    # Reddit.  The CSR path is mathematically the same normalized all-neighbor
    # operator and remains exact at inference; it is selected by size only.
    use_csr = int(data.edge_index.shape[1]) > 10_000_000
    # The first route for large graphs is exact checkpointed CSR training.
    # Sampling remains a documented fallback for machines where that route
    # cannot fit, but never supplies the final support trace.
    sampled_training = use_csr and not config.csr_checkpoint_training
    # Keep the large graph itself on host during sampled training.  Full CSR is
    # created only for the final all-neighbour evaluation/support capture.
    adjacency = None if sampled_training else (normalized_csr_adjacency(data.edge_index, data.num_nodes, device) if use_csr else None)
    if not sampled_training:
        data = data.to(device)

    def forward(trace: bool = False, fp8: bool = False):
        if adjacency is not None:
            return deepres_csr_forward(model, data.x, adjacency, trace=trace, fp8=fp8, checkpoint_blocks=config.csr_checkpoint_training and model.training)
        return model(data.x, data.edge_index, trace=trace)

    metric_fn = _multi_label_metrics if multi_label else _single_label_metrics
    positive_weight = None
    if multi_label and config.multi_label_pos_weight:
        # The fallback uses only training labels, never support statistics or
        # validation/test labels.  Clipping prevents an extremely rare label
        # from dominating the shared representation.
        training_labels = data.y[data.train_mask].to(dtype=torch.float32)
        positives = training_labels.sum(dim=0)
        negatives = float(training_labels.shape[0]) - positives
        positive_weight = (negatives / positives.clamp_min(1.0)).clamp(max=20.0).to(device)

    def supervised_loss(logits: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        if multi_label:
            return torch.nn.functional.binary_cross_entropy_with_logits(
                logits[mask], data.y[mask].to(dtype=logits.dtype), pos_weight=positive_weight,
            )
        return torch.nn.functional.cross_entropy(logits[mask], data.y[mask])

    sampler = IncomingCsrSampler(data.edge_index, data.num_nodes) if sampled_training else None
    train_nodes = np.flatnonzero(data.train_mask.detach().cpu().numpy()) if sampled_training else None
    val_nodes = np.flatnonzero(data.val_mask.detach().cpu().numpy()) if sampled_training else None

    def sampled_metric() -> dict[str, float]:
        """Validation proxy used only to choose a training checkpoint.

        Large graphs are trained with causal neighbourhood sampling, then
        evaluated and traced with the exact all-neighbour CSR operator below.
        We intentionally never use support-density information here.
        """
        total_loss = total_correct = total = 0
        model.eval()
        validation_rng = np.random.default_rng(config.seed + 10_003)
        with torch.no_grad():
            for _ in range(max(4, config.sampled_batches_per_epoch // 3)):
                seeds = validation_rng.choice(val_nodes, size=min(config.sampled_batch_size, len(val_nodes)), replace=False)
                batch = sampler.sample(seeds, layers=config.layers, fanout=config.sampled_neighbors, rng=validation_rng)
                x = data.x[batch.nodes].to(device)
                logits = model(x, batch.edge_index.to(device))[batch.seed_local.to(device)]
                labels = data.y[torch.from_numpy(seeds)].to(device)
                if multi_label:
                    batch_loss = torch.nn.functional.binary_cross_entropy_with_logits(
                        logits, labels.to(dtype=logits.dtype), pos_weight=positive_weight, reduction="sum",
                    )
                    predicted = logits > 0
                    truth = labels > 0.5
                    total_correct += int((predicted & truth).sum()) * 2
                    total += int(2 * (predicted & truth).sum() + (predicted & ~truth).sum() + (~predicted & truth).sum())
                else:
                    batch_loss = torch.nn.functional.cross_entropy(logits, labels, reduction="sum")
                    total_correct += int((logits.argmax(1) == labels).sum())
                    total += int(labels.numel())
                total_loss += float(batch_loss)
        key = "val_micro_f1" if multi_label else "val_accuracy"
        return {"val_loss": total_loss / max(total, 1), key: total_correct / max(total, 1)}
    optimizer = torch.optim.Adam(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    best_state = None
    best_val = float("inf")
    checks = 0
    epoch2 = float("nan")
    started = time.monotonic()
    finite = True
    for epoch in range(1, config.max_epochs + 1):
        model.train()
        if sampled_training:
            # GCNConv's cache is invalid across sampled subgraphs.
            for conv in model.convs:
                conv.cached = False
                conv._cached_edge_index = None
            training_rng = np.random.default_rng(config.seed + epoch)
            for _ in range(config.sampled_batches_per_epoch):
                seeds = training_rng.choice(train_nodes, size=min(config.sampled_batch_size, len(train_nodes)), replace=False)
                batch = sampler.sample(seeds, layers=config.layers, fanout=config.sampled_neighbors, rng=training_rng)
                optimizer.zero_grad(set_to_none=True)
                logits = model(data.x[batch.nodes].to(device), batch.edge_index.to(device))[batch.seed_local.to(device)]
                labels = data.y[torch.from_numpy(seeds)].to(device)
                loss = torch.nn.functional.binary_cross_entropy_with_logits(logits, labels.to(dtype=logits.dtype), pos_weight=positive_weight) if multi_label else torch.nn.functional.cross_entropy(logits, labels)
                if not torch.isfinite(loss):
                    finite = False; break
                loss.backward(); optimizer.step()
            if not finite:
                break
        else:
            optimizer.zero_grad(set_to_none=True)
            logits = forward()
            loss = supervised_loss(logits, data.train_mask)
            if not torch.isfinite(loss):
                finite = False; break
            loss.backward(); optimizer.step()
        if epoch % 2 == 0:
            if sampled_training:
                metrics = sampled_metric()
            else:
                model.eval()
                with torch.no_grad():
                    metrics = metric_fn(forward(), data)
            if epoch == 2: epoch2 = metrics["val_loss"]
            if metrics["val_loss"] < best_val:
                best_val = metrics["val_loss"]
                best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
                best_epoch = epoch; checks = 0
            else:
                checks += 1
            if epoch >= config.min_epochs and checks >= config.patience:
                break
            print(json.dumps({"event": "validation", "epoch": epoch, "val_loss": metrics["val_loss"], "val_quality": metrics.get("val_micro_f1", metrics.get("val_accuracy")), "best_val_loss": best_val, "checks": checks}, sort_keys=True), flush=True)
    if best_state is None:
        raise RuntimeError("training produced no finite validation checkpoint")
    model.load_state_dict(best_state); model.to(device).eval()
    if sampled_training:
        adjacency = normalized_csr_adjacency(data.edge_index, data.num_nodes, device)
        # Do not call ``Data.to`` here: its 115M-edge index is not needed by
        # CSR inference and would consume another ~1.7 GiB of GPU memory.
        data.x = data.x.to(device)
        data.y = data.y.to(device)
        for split in ("train_mask", "val_mask", "test_mask"):
            setattr(data, split, getattr(data, split).to(device))
    with torch.no_grad():
        fp32 = metric_fn(forward(), data)
    fp8_model = make_int8_model(model.cpu(), value_format="fp8", weight_format="fp16").to(device).eval()
    with torch.no_grad():
        if adjacency is not None:
            fp8_logits, trace = deepres_csr_forward(fp8_model, data.x, adjacency, trace=True, fp8=True)
        else:
            fp8_logits, trace = fp8_model(data.x, data.edge_index, trace=True)
        fp8 = metric_fn(fp8_logits, data)
    supports = np.stack([(tensor > 0).detach().cpu().numpy() for tensor in trace])
    root = project / "artifacts_hpca_xorflow/workloads" / config.config_id
    root.mkdir(parents=True, exist_ok=True)
    checkpoint = root / "model.pt"
    torch.save({"model_state": best_state, "config": asdict(config), "best_epoch": best_epoch}, checkpoint)
    np.savez_compressed(root / "fp8_supports.npz", packed=np.packbits(supports, axis=2), shape=np.asarray(supports.shape, dtype=np.int64))
    record = {
        **asdict(config), "device": str(device), "training_backend": "sampled_neighbor" if sampled_training else "full_graph", "aggregation_backend": "normalized_csr" if use_csr else "pyg_edge_index", "epochs": epoch, "best_epoch": best_epoch,
        "finite_loss": finite, "epoch2_val_loss": epoch2, "best_val_loss": best_val,
        "train_seconds": time.monotonic() - started, **{f"fp32_{k}": v for k, v in fp32.items()},
        **{f"fp8_fp16_{k}": v for k, v in fp8.items()},
        "quality_metric": "micro_f1" if multi_label else "accuracy",
        "accuracy_drop": fp32.get("test_accuracy", fp32.get("test_micro_f1")) - fp8.get("test_accuracy", fp8.get("test_micro_f1")),
        "supports_path": str(root / "fp8_supports.npz"), "checkpoint": str(checkpoint),
    }
    (root / "record.json").write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return record
