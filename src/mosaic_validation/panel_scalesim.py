"""Cached real SCALE-Sim calibration for row-panel GEMM shapes."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pandas as pd

from .scalesim_bridge import Workload, write_topology


def _config_text(array: int) -> str:
    return f"""[general]
run_name = mosaic_panel_{array}

[architecture_presets]
ArrayHeight: {array}
ArrayWidth: {array}
IfmapSramSzkB: 256
FilterSramSzkB: 256
OfmapSramSzkB: 256
IfmapOffset: 0
FilterOffset: 10000000
OfmapOffset: 20000000
Bandwidth: 10
Dataflow: ws
MemoryBanks: 1
ReadRequestBuffer: 32
WriteRequestBuffer: 32

[layout]
IfmapCustomLayout: False
IfmapSRAMBankBandwidth: 10
IfmapSRAMBankNum: 10
IfmapSRAMBankPort: 2
FilterCustomLayout: False
FilterSRAMBankBandwidth: 10
FilterSRAMBankNum: 10
FilterSRAMBankPort: 2

[sparsity]
SparsitySupport: false
SparseRep: ellpack_block
OptimizedMapping: false
BlockSize: 8
RandomNumberGeneratorSeed: 7

[run_presets]
InterfaceBandwidth: CALC
UseRamulatorTrace: False
"""


def calibrate_shapes(
    project: Path,
    shapes: set[tuple[int, int, int]],
    array: int = 32,
) -> dict[tuple[int, int, int], tuple[float, float]]:
    """Run each unique shape once and reuse its real reported cycles."""
    root = project / "artifacts_phase3a" / "scalesim" / f"array_{array}"
    root.mkdir(parents=True, exist_ok=True)
    cache_path = root / "shape_cache.json"
    cached: dict[str, list[float]] = {}
    if cache_path.exists():
        cached = json.loads(cache_path.read_text())
    missing = sorted(shape for shape in shapes if "_".join(map(str, shape)) not in cached)
    if missing:
        topology = root / "topology.csv"
        write_topology(
            [Workload(f"panel_{i}", m, n, k) for i, (m, k, n) in enumerate(missing)],
            topology,
        )
        layout = root / "layout.csv"
        template = (
            project / "third_party/SCALE-Sim/layouts/conv_nets/test.csv"
        ).read_text().splitlines()
        layout.write_text(
            template[0]
            + "\n"
            + "\n".join(
                template[1].replace("Inc5b_3x3", f"panel_{i}")
                for i in range(len(missing))
            )
            + "\n"
        )
        config = root / "scale.cfg"
        config.write_text(_config_text(array))
        reports = root / "reports"
        reports.mkdir(exist_ok=True)
        command = [
            str(project / ".scalesim-python"),
            "-m",
            "mosaic_validation.scalesim_smoke_runner",
            "-c",
            str(config),
            "-t",
            str(topology),
            "-l",
            str(layout),
            "-p",
            str(reports),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, timeout=1200)
        (root / "command.log").write_text(
            " ".join(command) + "\n" + completed.stdout + completed.stderr
        )
        report_paths = sorted(reports.glob("*/COMPUTE_REPORT.csv"))
        if completed.returncode or not report_paths:
            raise RuntimeError(
                f"SCALE-Sim array {array} failed ({completed.returncode}): "
                f"{completed.stderr[-1000:]}"
            )
        frame = pd.read_csv(report_paths[-1])
        if len(frame) != len(missing):
            raise RuntimeError("SCALE-Sim report row count does not match emitted shapes")
        for index, shape in enumerate(missing):
            cached["_".join(map(str, shape))] = [
                float(frame.iloc[index, 1]),
                float(frame.iloc[index, 4]),
            ]
        cache_path.write_text(json.dumps(cached, indent=2, sort_keys=True))
    return {
        shape: tuple(cached["_".join(map(str, shape))])  # type: ignore[arg-type]
        for shape in shapes
    }
