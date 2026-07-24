"""Full-batch training with best-validation checkpoints and time caps."""

from dataclasses import dataclass
import time

import torch


@dataclass
class TrainingResult:
    initial_metrics: dict[str, float]
    trained_metrics: dict[str, float]
    epochs_completed: int
    best_epoch: int
    epoch2_val_loss: float
    best_val_loss: float
    train_seconds: float
    truncated: bool
    finite_loss: bool
    peak_gpu_memory_mb: float


@torch.no_grad()
def evaluate(model, data, device: torch.device) -> dict[str, float]:
    model.eval()
    logits = model(data.x.to(device), data.edge_index.to(device))
    result: dict[str, float] = {}
    for split in ("train", "val", "test"):
        mask = getattr(data, f"{split}_mask").to(device)
        loss = torch.nn.functional.cross_entropy(logits[mask], data.y.to(device)[mask])
        accuracy = (logits[mask].argmax(dim=1) == data.y.to(device)[mask]).float().mean()
        result[f"{split}_loss"] = float(loss)
        result[f"{split}_accuracy"] = float(accuracy)
    return result


def train_model(model, data, device, config, time_cap_minutes: float, checkpoint_path):
    model.to(device)
    data = data.to(device)
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)
    initial = evaluate(model, data, device)
    optimizer = torch.optim.Adam(
        model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay
    )
    start = time.monotonic()
    best_loss = float("inf")
    best_epoch = 0
    best_state = None
    epoch2_loss = float("nan")
    checks_without_improvement = 0
    finite = True
    truncated = False
    epoch = 0
    for epoch in range(1, config.max_epochs + 1):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        logits = model(data.x, data.edge_index)
        loss = torch.nn.functional.cross_entropy(logits[data.train_mask], data.y[data.train_mask])
        if not torch.isfinite(loss):
            finite = False
            break
        loss.backward()
        optimizer.step()
        if epoch % config.validation_interval == 0:
            metrics = evaluate(model, data, device)
            val_loss = metrics["val_loss"]
            if epoch == 2:
                epoch2_loss = val_loss
            if val_loss < best_loss:
                best_loss = val_loss
                best_epoch = epoch
                best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
                checks_without_improvement = 0
            else:
                checks_without_improvement += 1
            if epoch >= config.min_epochs and checks_without_improvement >= config.patience_checks:
                break
        if time.monotonic() - start >= time_cap_minutes * 60:
            truncated = True
            break
    train_seconds = time.monotonic() - start
    if best_state is None:
        best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        best_loss = evaluate(model, data, device)["val_loss"]
        best_epoch = epoch
    model.load_state_dict(best_state)
    torch.save(
        {"model_state": best_state, "best_epoch": best_epoch, "best_val_loss": best_loss},
        checkpoint_path,
    )
    trained = evaluate(model, data, device)
    peak = (
        torch.cuda.max_memory_allocated(device) / (1024**2) if device.type == "cuda" else 0.0
    )
    return TrainingResult(
        initial, trained, epoch, best_epoch, epoch2_loss, best_loss, train_seconds,
        truncated, finite, peak,
    )

