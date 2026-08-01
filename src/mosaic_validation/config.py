"""Typed configuration loading."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class Experiment:
    id: str
    dataset: str
    model: str
    min_test_accuracy: float
    time_cap_minutes: float


@dataclass(frozen=True)
class QuickConfig:
    seed: int
    hidden_layers: int
    width: int
    dropout: float
    learning_rate: float
    weight_decay: float
    max_epochs: int
    min_epochs: int
    patience_checks: int
    validation_interval: int
    bootstrap_replicates: int
    pair_limit: int
    tile_size: int
    cohort_size: int
    principal_layer_start: int
    device: str
    configs: tuple[Experiment, ...]


def load_config(path: Path) -> QuickConfig:
    raw = yaml.safe_load(path.read_text())
    experiments = tuple(Experiment(**item) for item in raw.pop("configs"))
    return QuickConfig(configs=experiments, **raw)

