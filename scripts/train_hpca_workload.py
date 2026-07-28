#!/usr/bin/env python3
"""Train one reproducible HPCA XORFLOW workload; never tunes by sparsity."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from mosaic_validation.hpca_workloads import WorkloadConfig, train_and_trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--width", type=int, default=128)
    parser.add_argument("--layers", type=int, default=8)
    parser.add_argument("--max-epochs", type=int, default=160)
    parser.add_argument("--learning-rate", type=float, default=.005)
    parser.add_argument("--dropout", type=float, default=.20)
    parser.add_argument("--residual-scale", type=float, default=.20)
    parser.add_argument("--sampled-batches-per-epoch", type=int, default=24)
    parser.add_argument("--sampled-neighbors", type=int, default=2)
    parser.add_argument("--sampled-batch-size", type=int, default=128)
    parser.add_argument("--csr-checkpoint-training", action="store_true")
    parser.add_argument("--force-cpu", action="store_true")
    args = parser.parse_args()
    config = WorkloadConfig(dataset=args.dataset, config_id=args.config_id, seed=args.seed, width=args.width, layers=args.layers, max_epochs=args.max_epochs, learning_rate=args.learning_rate, dropout=args.dropout, residual_scale=args.residual_scale, sampled_batches_per_epoch=args.sampled_batches_per_epoch, sampled_neighbors=args.sampled_neighbors, sampled_batch_size=args.sampled_batch_size, csr_checkpoint_training=args.csr_checkpoint_training)
    print(json.dumps(train_and_trace(Path.cwd(), config, force_cpu=args.force_cpu), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
