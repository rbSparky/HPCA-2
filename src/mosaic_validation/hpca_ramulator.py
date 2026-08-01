"""Bounded real HBM2 timing for exact causal XORFLOW pair traces.

The Ramulator frontend accepts text LD/ST transactions.  To avoid retaining
large traces, this module emits one temporary trace, hashes it, runs the pinned
HBM2 model, verifies served request counts, retains JSON/statistics, then
removes only that self-created temporary file unless explicitly requested.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import sys
import os

import numpy as np
import pandas as pd

from .graph_order import symmetrized_edges_and_rcm, tiles_from_order
from .hpca_xorflow_cli import _case, _sources, build_pair_format_plan
from .memory_subsystem import (
    build_mixed_sliced_layout, build_sliced_layout, materialize_cache_miss_lines,
)


def _write_read_line(handle, address: int) -> int:
    handle.write(f"LD 0x{address:x}\nLD 0x{address + 32:x}\n")
    return 2


def _write_output_line(handle, address: int) -> int:
    # Write-allocate: one 64-B read-for-ownership followed by a dirty 64-B
    # writeback.  The temporary trace models both transactions explicitly.
    handle.write(f"LD 0x{address:x}\nLD 0x{address + 32:x}\nST 0x{address:x}\nST 0x{address + 32:x}\n")
    return 4


def _output_lines(layout) -> np.ndarray:
    values: list[np.ndarray] = []
    for start, useful in zip(layout.starts, layout.useful_bytes, strict=True):
        values.append(np.arange(start // 64, (start + int(useful) - 1) // 64 + 1, dtype=np.int64))
    return np.concatenate(values) if values else np.empty(0, dtype=np.int64)


def _emit_trace(project: Path, config_id: str, start: int, fmt: str, trace: Path, *, cache_bytes: int = 512 * 1024, slice_width: int = 128, tile_rows: int = 128) -> dict:
    masks, data, _ = _case(project, config_id)
    edge_index = data.edge_index.cpu().numpy()
    _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    tiles = tiles_from_order(order, tile_rows)
    pair = masks[start:start + 2]
    plan = build_pair_format_plan(pair, tiles, slice_width)
    if fmt == "xorflow":
        layouts = [build_mixed_sliced_layout(layer, slice_width=slice_width, formats=plan["formats"], node_order=order) for layer in pair]
        metadata_bytes = int(plan["xor_metadata"])
    elif fmt == "beicsr":
        layouts = [build_sliced_layout(layer, slice_width=slice_width, format_name="BEICSR", node_order=order) for layer in pair]
        metadata_bytes = 0
    else:
        raise ValueError(fmt)
    sources = _sources(edge_index, "O0")
    requests = 0
    with trace.open("w") as handle:
        for layer_index, layout in enumerate(layouts):
            misses = materialize_cache_miss_lines(layout, sources, capacity_bytes=cache_bytes)
            input_base = 0x1000000000 + layer_index * 0x100000000
            for line in misses:
                requests += _write_read_line(handle, input_base + int(line) * 64)
            topology_base = 0x4000000000 + layer_index * 0x100000000
            topology_bytes = edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4
            for offset in range(0, topology_bytes, 64):
                requests += _write_read_line(handle, topology_base + offset)
            output_base = 0x8000000000 + layer_index * 0x100000000
            for line in _output_lines(layout):
                requests += _write_output_line(handle, output_base + int(line) * 64)
        if metadata_bytes:
            metadata_base = 0xC000000000
            for offset in range(0, metadata_bytes, 64):
                requests += _write_read_line(handle, metadata_base + offset)
                requests += _write_output_line(handle, metadata_base + 0x10000000 + offset)
    return {"requests": requests, "metadata_bytes": metadata_bytes, "nodes": int(data.num_nodes), "edges": int(edge_index.shape[1])}


def _parse_stats(path: Path, expected_requests: int) -> dict:
    stats = json.loads(path.read_text())
    controllers = stats["memory_system"]["controller"]
    served = sum(int(c["num_read_reqs_served"]) + int(c["num_write_reqs_served"]) for c in controllers)
    # HBM controller statistics count migrated read requests as forwarded at
    # the source controller. They are still accounted requests, not drops.
    forwarded = sum(int(c.get("num_read_reqs_forwarded", 0)) for c in controllers)
    # A known fixed 4096-cycle frontend drain applies equally to both formats.
    cycles = max(int(c["cycles"]) for c in controllers) - 4096
    return {"dram_cycles": cycles, "served_requests": served, "forwarded_requests": forwarded,
            "accounted_requests": served + forwarded,
            "all_requests_drained": served + forwarded == expected_requests}


def run_pair(project: Path, *, config_id: str, pair_start_layer: int, artifact_dir: Path, keep_trace: bool = False) -> pd.DataFrame:
    """Time BEICSR and causal XORFLOW for one exact pair through Ramulator2."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    with tempfile.TemporaryDirectory(prefix="xorflow_hbm_", dir=artifact_dir) as temporary:
        work = Path(temporary)
        for fmt in ("beicsr", "xorflow"):
            trace = work / f"{fmt}.trace"
            emitted = _emit_trace(project, config_id, pair_start_layer - 1, fmt, trace)
            digest = hashlib.sha256(trace.read_bytes()).hexdigest()
            output = artifact_dir / f"{config_id}_l{pair_start_layer}_{fmt}_ramulator.json"
            ramulator_root = project / "third_party/ramulator2"
            # The pinned nanobind module was built for the system Python 3.12;
            # the ML environment is Python 3.11.  Keep timing isolated in its
            # compatible interpreter rather than rebuilding or downgrading the
            # training environment mid-study.
            interpreter = os.environ.get("MOSAIC_RAMULATOR_PY", "python3")
            command = [interpreter, str(project / "scripts/run_ramulator_hbm2.py"), str(trace), str(output)]
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(ramulator_root / "python") + os.pathsep + environment.get("PYTHONPATH", "")
            environment["LD_LIBRARY_PATH"] = str(ramulator_root) + os.pathsep + environment.get("LD_LIBRARY_PATH", "")
            completed = subprocess.run(command, text=True, capture_output=True, timeout=3600, env=environment)
            (artifact_dir / f"{config_id}_l{pair_start_layer}_{fmt}_ramulator.log").write_text(
                " ".join(command) + "\n\nSTDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr
            )
            parsed = _parse_stats(output, emitted["requests"]) if completed.returncode == 0 and output.exists() else {"dram_cycles": 0, "served_requests": 0, "all_requests_drained": False}
            rows.append({"config_id": config_id, "pair_start_layer": pair_start_layer, "format": fmt, "trace_sha256": digest, **emitted, **parsed, "tool_success": completed.returncode == 0, "error": completed.stderr[-1000:]})
            if keep_trace:
                target = artifact_dir / f"{config_id}_l{pair_start_layer}_{fmt}.trace"
                trace.replace(target)
        frame = pd.DataFrame(rows)
    beic = frame.loc[frame.format == "beicsr", "dram_cycles"].iloc[0]
    frame["speedup_vs_beicsr"] = beic / frame["dram_cycles"].clip(lower=1)
    return frame
