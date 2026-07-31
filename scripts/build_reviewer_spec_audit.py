#!/usr/bin/env python3
"""Build the repository audit and immutable trace manifest for reviewer replay."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import subprocess
from datetime import datetime, timezone

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results_hpca_xorflow" / "reviewer_spec_v2"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def inventory() -> None:
    rows = []
    patterns = {
        "source": ("src/**/*.py", "tests/**/*.py", "scripts/**/*.py"),
        "rtl": ("rtl/**/*",), "config": ("configs/**/*",),
        "trace": ("artifacts_hpca_xorflow/workloads/*/fp8_supports.npz",),
        "checkpoint": ("artifacts_hpca_xorflow/workloads/*/model.pt",),
        "result": ("results_hpca_xorflow/complete_suite/**/*",),
    }
    for kind, globs in patterns.items():
        for pattern in globs:
            for path in ROOT.glob(pattern):
                if not path.is_file():
                    continue
                rows.append({
                    "artifact_type": kind, "path": str(path.relative_to(ROOT)), "status": "present",
                    "version_or_commit": git("rev-parse", "HEAD") if kind in {"source", "rtl", "config"} else "",
                    "sha256": sha(path), "used_by": "reviewer_spec_v2",
                    "notes": "immutable pre-existing evidence" if kind in {"trace", "checkpoint", "result"} else "audited implementation input",
                })
    target = OUT / "audit" / "repo_inventory.csv"; target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=("artifact_type", "path", "status", "version_or_commit", "sha256", "used_by", "notes"))
        writer.writeheader(); writer.writerows(sorted(rows, key=lambda row: (row["artifact_type"], row["path"])))


def trace_manifest() -> None:
    columns = "run_id dataset model seed checkpoint_sha256 config_sha256 git_sha layer_count hidden_width precision node_order rcm_enabled tile_rows default_slice_width support_path value_path shape_json command start_utc end_utc".split()
    rows = []
    for record_path in sorted((ROOT / "artifacts_hpca_xorflow" / "workloads").glob("*/record.json")):
        support = record_path.with_name("fp8_supports.npz")
        checkpoint = record_path.with_name("model.pt")
        if not support.exists():
            continue
        record = json.loads(record_path.read_text())
        payload = np.load(support)
        shape = [int(value) for value in payload["shape"]]
        timestamp = datetime.fromtimestamp(support.stat().st_mtime, timezone.utc).isoformat()
        rows.append({
            "run_id": record.get("config_id", record_path.parent.name), "dataset": record.get("dataset", "unknown"),
            "model": record.get("model_kind", "deepres_v2"), "seed": record.get("seed", ""),
            "checkpoint_sha256": sha(checkpoint) if checkpoint.exists() else "UNAVAILABLE",
            "config_sha256": sha(record_path), "git_sha": git("rev-parse", "HEAD"),
            "layer_count": shape[0], "hidden_width": shape[2], "precision": "FP8_E4M3_support",
            "node_order": "original_trace_rows; RCM permutation applied at replay",
            "rcm_enabled": True, "tile_rows": 128, "default_slice_width": 128,
            "support_path": str(support.relative_to(ROOT)), "value_path": "NOT_RETAINED; exact packed byte count derived from support nnz",
            "shape_json": json.dumps(shape),
            "command": f"python -m mosaic_validation.hpca_workloads --config-id {record.get('config_id', record_path.parent.name)}",
            "start_utc": "UNAVAILABLE", "end_utc": timestamp,
        })
    target = OUT / "traces" / "trace_manifest.csv"; target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader(); writer.writerows(rows)


def report() -> None:
    text = f"""# XORFLOW Repository and Input Audit

Git revision: `{git('rev-parse', 'HEAD')}` (`gem`). This audit preserves all historical phase results and uses cached traces/checkpoints without retraining.

## Resolved implementation contracts

- **Residual ordering:** `DeepResV2` applies `LayerNorm(h) -> ReLU -> trace/quantize -> dropout -> GCNConv -> h + residual_scale*z`. The recorded tensor is the quantized post-ReLU tensor consumed by the convolution.
- **Projection:** the input feature dimension is projected once by `Linear(num_features,width)`; residual blocks are fixed width, so no hidden per-block projection occurs.
- **Graph semantics:** model execution uses the dataset edge stream and `GCNConv(cached=True, add_self_loops=True, normalize=True)`. Analysis symmetrizes edges only for Reverse Cuthill--McKee ordering. Replay preserves original node IDs and edge arithmetic while using 128-row RCM topology tiles.
- **Trace contract:** packed NPZ traces contain exact nonzero support of FP8 E4M3 post-ReLU activations in layer-production order. Checkpoint, config, trace, and source hashes are inventoried.
- **BEICSR:** historical physical layout is implemented in `mosaic_validation.memory_subsystem`; reviewer replay uses the frozen byte-producing BEICSR bitmap record in `xorflow.serializer`, with identical FP8 values and 64-byte alignment across compared formats.
- **Producer contract:** the finite-queue model uses the existing 32x64-bit (2,048-bit/cycle) producer sensitivity point and reports achieved rates under ready/valid backpressure rather than assuming peak throughput.
- **Memory:** common host uses 64-byte cache lines, 512 KiB 16-way LRU feature cache, eight-channel HBM2, two 32-byte transactions per line, 256 GB/s at 1 GHz. Full config/version evidence is retained under the prior timing campaign and copied into the final bundle.
- **Decoder provenance:** `rtl/xorflow_decoder_pipelined.sv` is the routed one-lane source. It is evidence for the lane only; the new integrated cluster is separately modeled/synthesized and is not inferred by multiplying lane PPA.

## Reconstructed or newly frozen

- The prior analytical event accounting did not define a parseable byte stream. `xorflow.serializer` now freezes bit order, headers, field widths, tie rules, zero padding, malformed behavior, and the 16-byte offset table.
- The prior pair-complete selector was future dependent. `xorflow.online_replay` now commits every anchor before reading its target and emits decision events plus a future-mutation causality test.

## Unavailable inputs

- Historical full-precision activation tensors and packed value contents were intentionally not retained. Exact value byte counts and addresses are reproducible from support NNZ, but value-bit payload hashes cannot be reconstructed.
- Original trace-capture start timestamps are absent; file completion times are recorded.
- A full common-host floorplan is unavailable, so host-relative area/power percentages must remain unclaimed unless the new integrated flow establishes them.
"""
    target = OUT / "audit" / "REPO_AUDIT.md"; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(text)


def main() -> None:
    inventory(); trace_manifest(); report()
    print(OUT)


if __name__ == "__main__":
    main()
