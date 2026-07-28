"""Cached SCALE-Sim calibration for unchanged GNN combination GEMMs."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from .scalesim_bridge import Workload, write_topology


@dataclass(frozen=True)
class ScaleSimResult:
    m: int
    n: int
    k: int
    cycles: int
    cycles_with_prefetch: int
    utilization: float
    success: bool
    error: str = ""


def _key(m: int, n: int, k: int) -> str:
    return hashlib.sha256(f"ws32x32|256|256|256|{m}|{n}|{k}".encode()).hexdigest()


def _config(path: Path, run_name: str) -> None:
    path.write_text(f"""[general]
run_name = {run_name}

[architecture_presets]
ArrayHeight: 32
ArrayWidth: 32
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
""")


def calibrate_gemm(project: Path, artifact_dir: Path, *, m: int, n: int, k: int) -> ScaleSimResult:
    """Run or reuse one 32×32 WS GEMM calibration without reducing execution count.

    Caching only avoids duplicate simulator invocations.  Callers must multiply
    the returned cycle count by actual layer execution count themselves.
    """
    if min(m, n, k) <= 0:
        raise ValueError("GEMM dimensions must be positive")
    artifact_dir.mkdir(parents=True, exist_ok=True)
    cache_path = artifact_dir / "shape_cache.json"
    cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
    key = _key(m, n, k)
    if key in cache and cache[key].get("success", False):
        return ScaleSimResult(**cache[key])
    run_dir = artifact_dir / key[:16]
    run_dir.mkdir(exist_ok=True)
    topology = run_dir / "topology.csv"
    config = run_dir / "scale.cfg"
    output = run_dir / "reports"
    write_topology([Workload("combination", m, n, k)], topology)
    _config(config, f"xorflow_{key[:12]}")
    command = [
        # The historical launcher can be a non-executable symlink when the
        # repository is mounted from WSL.  The active interpreter is the
        # reproducible environment selected by the calling stage.
        sys.executable, "-m", "mosaic_validation.scalesim_smoke_runner",
        "-c", str(config), "-t", str(topology),
        "-l", str(project / "third_party/SCALE-Sim/layouts/conv_nets/test.csv"),
        "-p", str(output),
    ]
    try:
        completed = subprocess.run(command, text=True, capture_output=True, timeout=1800)
        (run_dir / "command.log").write_text(
            " ".join(command) + "\n\nSTDOUT\n" + completed.stdout + "\nSTDERR\n" + completed.stderr
        )
        report = next(output.glob("*/COMPUTE_REPORT.csv"))
        with report.open(newline="") as handle:
            row = next(csv.DictReader(handle))
        result = ScaleSimResult(
            m=m, n=n, k=k,
            cycles=int(float(row[" Total Cycles"])),
            cycles_with_prefetch=int(float(row[" Total Cycles (incl. prefetch)"])),
            utilization=float(row[" Overall Util %"]),
            success=completed.returncode == 0,
            error="" if completed.returncode == 0 else completed.stderr[-1000:],
        )
    except Exception as error:  # Failure remains a recorded tool fact.
        result = ScaleSimResult(m=m, n=n, k=k, cycles=0, cycles_with_prefetch=0, utilization=0.0, success=False, error=repr(error))
    cache[key] = asdict(result)
    cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True) + "\n")
    return result
