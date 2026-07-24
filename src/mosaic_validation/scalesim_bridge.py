"""Dense SCALE-Sim smoke integration and future regular/residual interface."""

from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class Workload:
    name: str
    m: int
    n: int
    k: int


def write_topology(workloads: list[Workload], path: Path) -> None:
    lines = ["Layer,M,N,K,"]
    for item in workloads:
        lines.append(f"{item.name},{item.m},{item.n},{item.k},")
    path.write_text("\n".join(lines) + "\n")


def emit_regular_and_residual_workloads(
    regular: list[Workload], residual: list[Workload], directory: Path
) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    regular_path, residual_path = directory / "regular.csv", directory / "residual.csv"
    write_topology(regular, regular_path)
    write_topology(residual, residual_path)
    return regular_path, residual_path


def run_smoke(project_root: Path, results_root: Path, num_nodes: int) -> tuple[bool, str]:
    topology = results_root / "scalesim_cora_hidden.csv"
    write_topology([Workload("cora_hidden_01", num_nodes, 64, 64)], topology)
    scalesim_root = project_root / "third_party" / "SCALE-Sim"
    if not (scalesim_root / "configs" / "scale.cfg").exists():
        message = "SCALE-Sim configuration not found; clone/install blocker."
        (results_root / "SCALESIM_SMOKE.md").write_text(f"# SCALE-Sim smoke\n\n{message}\n")
        return False, message
    config = results_root / "scalesim_32x32_ws.cfg"
    config.write_text("""[general]
run_name = mosaic_dense_smoke

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
    output = results_root / "scalesim_reports"
    output.mkdir(exist_ok=True)
    command = [
        str(project_root / ".scalesim-python"),
        "-m", "mosaic_validation.scalesim_smoke_runner",
        "-c", str(config), "-t", str(topology),
        "-l", str(scalesim_root / "layouts" / "conv_nets" / "test.csv"),
        "-p", str(output),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=300)
    markdown = (
        "# SCALE-Sim dense GEMM smoke test\n\n"
        "This callability smoke test does not evaluate MOSAIC.\n\n"
        f"Command: `{' '.join(command)}`\n\n"
        f"Exit code: `{completed.returncode}`\n\n"
        f"```text\n{completed.stdout[-4000:]}\n{completed.stderr[-4000:]}\n```\n"
    )
    (results_root / "SCALESIM_SMOKE.md").write_text(markdown)
    return completed.returncode == 0, completed.stderr[-1000:]
