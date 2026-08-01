#!/usr/bin/env python3
"""Create a non-destructive, anonymous XORFLOW submission archive.

Only copied files are filtered or scrubbed.  The working tree, source results,
checkpoints, datasets, and generated handoffs are never modified.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "XORFLOW_ANONYMOUS_SUBMISSION.zip"

# Core implementation, validation, RTL, and reproducibility material.
SCRIPT_NAMES = {
    "audit_hpca_quality.py", "build_hpca_paper_evidence.py",
    "build_reviewer_ablation_decomposition.py", "build_reviewer_spec_audit.py",
    "check_reviewer_determinism.py", "consolidate_reviewer_spec.py",
    "finalize_reviewer_spec.py", "generate_reviewer_activity.py",
    "generate_reviewer_figures.py", "package_xorflow_result_bundle.py",
    "record_reviewer_rerun.py", "report_hpca_complete_suite.py",
    "run_corrected_schedule_lane.sh", "run_dramsim3_full_trace.py",
    "run_dramsim3_smoke.py", "run_dramsim3_trace_sample.py",
    "run_hpca_local_toolchain.sh", "run_hpca_ramulator.py",
    "run_hpca_xorflow_preflight.sh", "run_openroad_vcd_power.sh",
    "run_openroad_xorflow_cluster8.sh", "run_openroad_xorflow_lane.sh",
    "run_openroad_xorflow_pipelined.sh", "run_ramulator_hbm2.py",
    "run_xorflow_cuda_bench.py", "run_xorflow_decoder_cosim.sh",
    "scale_fullstream_activity.py", "summarize_online_ramulator.py",
    "synth_decoder.sh", "synth_pipelined_decoder.sh", "synth_xorflow_cluster.sh",
    "synth_xorflow_encoder.sh", "verify_encoder_engine_rtl.sh",
    "verify_encoder_rtl_stream.py", "verify_zip.py",
}

TEXT_SUFFIXES = {
    ".py", ".sh", ".sv", ".v", ".vh", ".cpp", ".h", ".mk", ".sdc",
    ".yaml", ".yml", ".json", ".csv", ".txt", ".toml", ".patch", ".md",
}


def scrub(text: str) -> str:
    """Remove local identities and machine-specific paths from copied text."""
    text = re.sub(r"/home/[^/\s:'\"]+", "<PROJECT_ROOT>", text)
    text = re.sub(r"/mnt/[^\s:'\"]+", "<EXTERNAL_DATA>", text)
    text = re.sub(r"/workspace/[^\s:'\"]+", "<PROJECT_ROOT>", text)
    text = re.sub(r"/tmp/[A-Za-z0-9_.+@/-]+", "<TEMP_PATH>", text)
    text = text.replace("rbSparky", "anonymous")
    text = text.replace("mll5090", "compute-host")
    text = text.replace("rishabh", "anonymous")
    text = re.sub(r"<PROJECT_ROOT>(?:/HPCA2)?(?:/mosaic_delta_phase1)?", "<PROJECT_ROOT>", text)
    text = text.replace("/HPCA2", "")
    # Do not expose environment layout even through the placeholder prefix.
    text = re.sub(r"<PROJECT_ROOT>/[^\s:'\"]+", "<PROJECT_ROOT>", text)
    text = re.sub(r"https://github\.com/[^\s/]+/[^\s/]+", "https://example.invalid/anonymous/xorflow", text)
    return text


def copy_text(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    raw = src.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        dst.write_bytes(raw)
        return
    dst.write_text(scrub(text))


def copy_tree_files(
    src_root: Path,
    dst_root: Path,
    suffixes: set[str] | None = None,
    excluded_names: set[str] | None = None,
) -> None:
    for src in sorted(src_root.rglob("*")):
        if not src.is_file() or any(part in {"__pycache__", ".git", ".pytest_cache"} for part in src.parts):
            continue
        if src.suffix in {".pyc", ".pyo", ".nbi", ".nbc"}:
            continue
        if src.name in {"hpca_paper_queue.py", "phase1_cli.py"} or (excluded_names and src.name in excluded_names):
            continue
        if suffixes is not None and src.suffix not in suffixes:
            continue
        copy_text(src, dst_root / src.relative_to(src_root))


def copy_named(src: Path, dst: Path) -> None:
    if src.exists() and src.is_file():
        copy_text(src, dst)


def write_submission_readme(dst: Path) -> None:
    dst.write_text(
        """# XORFLOW: anonymous supplementary artifact

This archive contains the core exact support-streaming implementation, RTL and
software validation harnesses, and a compact subset of audited XORFLOW results.
It is prepared for anonymous review and contains no raw datasets, checkpoints,
third-party histories, queue logs, agent instructions, or machine-local paths.

## Contribution

XORFLOW stores an exact topology-local support anchor, independently decodable
XOR exception streams, packed activation values, and a tile-local reconstructed
support cache. The causal schedule uses finite queues, explicit producer,
memory, decoder, aggregation, combination, and writeback dependencies, memory
completion, layer barriers, fill/drain, and anchor recovery accounting.

## Included material

- `src/xorflow/`: causal serializer, online replay, encoder/decoder and traffic models.
- `src/mosaic_validation/`: supporting exact codecs, null controls, host and tool bridges.
- `rtl/`: encoder/decoder RTL and software/RTL testbenches.
- `tests/`: correctness and schedule/resource tests.
- `configs/`: reproducible experiment configurations.
- `results/`: the corrected reviewer tables and selected RTL/toolchain evidence.

## Results scope

The results are exact serialized bytes and modeled aggregation+combination
subsystem cycles. They are not measured end-to-end GNN accelerator speedups.
Negative and near-parity workloads are retained. The reviewer-results document
records the remaining limitation that the wide full-workload producer packer
was elaborated but not fully mapped through ABC; tile-scale producer and routed
decoder-cluster evidence are reported separately.

## Reproduction

Install the dependencies from `pyproject.toml`, set `PYTHONPATH=src`, then run
the focused tests with `pytest -q tests/test_xorflow_core.py tests/test_causal_schedule.py
tests/test_xorflow_serializer.py tests/test_reviewer_rtl_integration.py`.
The selected CSV/JSON artifacts under `results/` are the source for the tables.
"""
    )


def git_revision() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unavailable"


def main() -> None:
    stage = Path(tempfile.mkdtemp(prefix="xorflow_anon_"))
    try:
        # Core Python implementation and tests; omit bytecode and cache state.
        copy_tree_files(ROOT / "src", stage / "src", TEXT_SUFFIXES)
        copy_tree_files(ROOT / "tests", stage / "tests", {".py"})
        copy_tree_files(ROOT / "rtl", stage / "rtl", TEXT_SUFFIXES)
        copy_tree_files(
            ROOT / "configs",
            stage / "configs",
            TEXT_SUFFIXES,
            {"hpca_paper_queue.yaml", "hpca_paper_ready_tracking.yaml", "hpca_overnight.yaml"},
        )
        (stage / "scripts").mkdir(parents=True, exist_ok=True)
        for name in sorted(SCRIPT_NAMES):
            copy_named(ROOT / "scripts" / name, stage / "scripts" / name)
        for name in ("pyproject.toml", "scalesim_numpy2.patch"):
            copy_named(ROOT / name, stage / name)

        # Curated best results only; no raw traces, activations, checkpoints,
        # queue/monitor logs, or personal handoffs are copied.
        result_files = {
            "results_hpca_xorflow/reviewer_spec_v3/schedule/system_cycles.csv": "results/causal_schedule.csv",
            "results_hpca_xorflow/reviewer_spec_v3/ablation/ablation_decomposition.csv": "results/ablation_decomposition.csv",
            "results_hpca_xorflow/reviewer_spec_v3/report/paper_summary.csv": "results/paper_summary.csv",
            "results_hpca_xorflow/complete_suite/HPCA_PAPER_EVIDENCE.csv": "results/hpca_paper_evidence.csv",
            "results_hpca_xorflow/complete_suite/HPCA_PAPER_GATES.csv": "results/hpca_paper_gates.csv",
            "results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_synth.json": "results/encoder_synth.json",
            "results_hpca_xorflow/reviewer_spec_v3/encoder/encoder_stream_cosim.log": "results/encoder_stream_cosim.log",
            "results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_synth.json": "results/decoder_cluster_synth.json",
            "results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_cosim.log": "results/decoder_cluster_cosim.log",
            "results_hpca_xorflow/reviewer_spec_v3/decoder/decoder_cluster_openroad_summary.json": "results/decoder_cluster_openroad_summary.json",
            "results_hpca_xorflow/reviewer_spec_v3/encoder/stream_equivalence.csv": "results/encoder_stream_equivalence.csv",
        }
        for src_rel, dst_rel in result_files.items():
            copy_named(ROOT / src_rel, stage / dst_rel)
        write_submission_readme(stage / "README.md")
        (stage / "results" / "PROVENANCE.txt").write_text(
            "Anonymous XORFLOW artifact\n"
            f"Source revision: {git_revision()}\n"
            "Only curated tables and selected implementation evidence are included.\n"
            "Raw datasets, checkpoints, transient traces, queue logs, agent files, and local paths are excluded.\n"
        )

        if ARCHIVE.exists():
            ARCHIVE.unlink()
        with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(stage).as_posix())
        size = ARCHIVE.stat().st_size
        if size >= 20 * 1024 * 1024:
            raise SystemExit(f"archive exceeds 20 MiB: {size}")
        print(f"archive={ARCHIVE}")
        print(f"bytes={size}")
        print(f"files={sum(1 for p in stage.rglob('*') if p.is_file())}")
        print(f"staging={stage}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__":
    main()
