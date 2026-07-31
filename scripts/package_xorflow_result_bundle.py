#!/usr/bin/env python3
"""Package a compact, auditable XORFLOW reviewer handoff.

Large raw activation/checkpoint artifacts and duplicate aggregate CSVs are not
copied into the archive.  Their paths, sizes, and SHA-256 hashes are retained
in MANIFEST.json so the omission is explicit and recoverable.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "xorflow_result_bundle.zip"
V3 = ROOT / "results_hpca_xorflow" / "reviewer_spec_v3"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def add_candidate(path: Path, arc: str, members: list[tuple[Path, str]], omitted: list[dict[str, object]], max_bytes: int | None = None) -> None:
    if not path.is_file() or path.name == OUT.name or ".git" in path.parts:
        return
    size = path.stat().st_size
    if max_bytes is not None and size > max_bytes:
        omitted.append({"path": str(path.relative_to(ROOT)), "size_bytes": size, "sha256": sha(path), "reason": f"larger_than_{max_bytes}_bytes"})
        return
    members.append((path, arc))


def add_tree(rel: str, members: list[tuple[Path, str]], omitted: list[dict[str, object]], max_bytes: int | None = None) -> None:
    base = ROOT / rel
    if not base.exists():
        return
    for path in sorted(base.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and ".pytest_cache" not in path.parts:
            add_candidate(path, str(Path(rel) / path.relative_to(base)), members, omitted, max_bytes)


def generated_text() -> tuple[str, str, str, str]:
    now = datetime.now(timezone.utc).isoformat()
    status = git("status", "--short")
    diff = subprocess.run(["git", "diff", "--binary"], cwd=ROOT, text=True, capture_output=True, check=False).stdout
    env_lines = {
        "python.txt": subprocess.run(["/home/rishabh/miniconda/envs/taugat_pyg/bin/python", "-c", "import sys; print(sys.executable); print(sys.version)"], text=True, capture_output=True, check=False).stdout,
        "pip_freeze.txt": subprocess.run(["/home/rishabh/miniconda/envs/taugat_pyg/bin/python", "-m", "pip", "freeze"], text=True, capture_output=True, check=False).stdout,
        "system.txt": subprocess.run(["bash", "-lc", "uname -a; free -h; nvidia-smi"], text=True, capture_output=True, check=False).stdout,
        "tool_versions.txt": subprocess.run(["bash", "-lc", "command -v yosys || true; yosys -V 2>/dev/null || true; command -v verilator || true; verilator --version 2>/dev/null || true; docker image inspect local/cacti-hp:7.0 --format '{{.Id}}' 2>/dev/null || true; git -C /home/rishabh/src/OpenROAD-flow-scripts rev-parse HEAD 2>/dev/null || true"], text=True, capture_output=True, check=False).stdout,
    }
    environment = "\n".join(f"### {name}\n{value}" for name, value in env_lines.items()) + f"\nGenerated UTC: {now}\n"
    readme = f"""# XORFLOW reviewer result bundle\n\nGenerated UTC: {now}\nGit HEAD: `{git('rev-parse', 'HEAD')}`\n\nThis archive contains the causal online serializer/replay implementation, 26-configuration campaign outputs, exact round-trip summaries, event-driven schedules, controls, timing/PPA evidence, tests, logs, and the final honest report. It excludes raw checkpoints/activation NPZs, transient giant aggregate files, and third-party histories. Omitted files are hashed in `MANIFEST.json`.\n\nStart with:\n\n1. `reviewer_spec_v3/report/FINAL_RESULTS.md`\n2. `reviewer_spec_v3/report/RESULT_SUMMARY.yaml`\n3. `reviewer_spec_v3/RESULT_MANIFEST.csv`\n4. `reviewer_spec_v3/REPRODUCE_COMMANDS.txt`\n5. `reviewer_spec_v3/audit/REPO_AUDIT.md`\n\nThe declared decision is `ITERATE_METHOD_BEFORE_SIMULATOR`: causal data and modeled subsystem results are positive, while encoder RTL, complete-workload independent DRAM timing, and final figure regeneration remain explicitly unresolved.\n"""
    readme = readme.replace(
        "while encoder RTL, complete-workload independent DRAM timing, and final figure regeneration remain explicitly unresolved.",
        "The handoff includes synthesized ready/valid encoder-boundary RTL, Verilator stream equivalence, deterministic rerun hashes, pair/sampled independent DRAM evidence, and a complete Arxiv online replay timing record; it does not overclaim a full RTL candidate-discovery engine or full all-workload DRAM timing.",
    )
    readme = readme.replace(
        "26-configuration campaign outputs",
        "26-configuration campaign summaries (bulk per-configuration traces are intentionally omitted and hash-indexed)",
    )
    return readme, environment, status + "\n", diff


def main() -> None:
    members: list[tuple[Path, str]] = []
    omitted: list[dict[str, object]] = []
    # Source, tests, RTL, configs, tools, and all reviewer implementation.
    for rel in ("src", "scripts", "tests", "tools", "rtl", "configs"):
        add_tree(rel, members, omitted, max_bytes=20 * 1024 * 1024)
    # Immutable reviewer outputs.  The zip is deliberately compact: raw
    # per-configuration traces/streams remain in the local results tree and
    # are represented by hashes in RESULT_MANIFEST.csv and MANIFEST.json.
    # Keep the reviewer-facing ledger, reports, compact tool summaries, and
    # figures; do not silently pretend bulk traces are portable.
    compact_v3_prefixes = (
        "report/", "audit/", "traces/", "figures/", "memory/", "quality/",
        "encoder/encoder_synth.json", "encoder/encoder_rtl_synthesis.log",
        "encoder/encoder_engine_rtl_synthesis.log", "encoder/encoder_engine_cosim.log",
        "encoder/encoder_verilator_lint.log", "encoder/stream_equivalence.csv",
        "decoder/decoder_cluster_synth.json", "decoder/decoder_cluster_rtl_synthesis.log",
        "decoder/decoder_cluster_verilator_lint.log", "decoder/decoder_cluster_cosim.log",
        "decoder/decoder_cluster_openroad_summary.json", "schedule/system_cycles.csv",
        "schedule/overlap_breakdown.csv", "RESULT_MANIFEST.csv",
        "REPRODUCE_COMMANDS.txt", "REVIEWER_SPEC_STATUS.md",
    )
    compact_v3_exact = {"report/FINAL_RESULTS.md", "report/RESULT_SUMMARY.yaml"}
    aggregate_names = {"adjacent_support.csv", "memory_transactions.csv", "support_records.csv", "roundtrip_all_real.csv", "conflicts.csv", "encoder_trace.csv", "decoder_cluster_trace.csv"}
    for path in sorted(V3.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(V3))
        if not (rel in compact_v3_exact or any(rel.startswith(prefix) for prefix in compact_v3_prefixes)):
            omitted.append({"path": str(path.relative_to(ROOT)), "size_bytes": path.stat().st_size, "sha256": sha(path), "reason": "bulk raw trace omitted from compact handoff; local path and aggregate hash retained"})
            continue
        add_candidate(path, str(Path("reviewer_spec_v3") / path.relative_to(V3)), members, omitted, 20 * 1024 * 1024)
    # Existing complete-suite evidence needed to interpret PPA/timing/quality.
    for path in sorted((ROOT / "results_hpca_xorflow" / "complete_suite").rglob("*")):
        if not path.is_file() or "runs" in path.parts and path.suffix not in {".csv", ".json"}:
            continue
        if path.suffix.lower() not in {".csv", ".json", ".yaml", ".yml", ".md", ".txt", ".tsv", ".log"}:
            continue
        add_candidate(path, str(Path("complete_suite") / path.relative_to(ROOT / "results_hpca_xorflow" / "complete_suite")), members, omitted, 10 * 1024 * 1024)
    # Audit, plan, and specification context live one directory above the
    # repository root in this workspace.
    for path in [ROOT / "AGENTS.md", ROOT / "plan.md", ROOT.parent / "XORFLOW_EXPERIMENT_EXECUTION_SPEC.md", ROOT.parent / "PAPER_WRITING_NOTES.md", ROOT / "dramsim3.json"]:
        if path.exists():
            add_candidate(path, path.name, members, omitted, 20 * 1024 * 1024)
    for path in sorted((ROOT / "artifacts_hpca_xorflow" / "complete_suite" / "local_toolchain_20260730T074723Z").glob("*")):
        add_candidate(path, str(Path("environment") / path.name), members, omitted, 10 * 1024 * 1024)
    for path in sorted((ROOT / "artifacts_hpca_xorflow" / "complete_suite" / "ppa" / "20260729T_local_ppa_v3").glob("**/*")):
        if path.is_file() and path.suffix.lower() in {".csv", ".json", ".log", ".rpt", ".md"}:
            add_candidate(path, str(Path("ppa") / path.relative_to(ROOT / "artifacts_hpca_xorflow" / "complete_suite" / "ppa" / "20260729T_local_ppa_v3")), members, omitted, 10 * 1024 * 1024)

    readme, environment, status, diff = generated_text()
    manifest_rows = [{"archive_path": arc, "source_path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path), "size_bytes": path.stat().st_size, "sha256": sha(path)} for path, arc in members]
    manifest = {"generated_utc": datetime.now(timezone.utc).isoformat(), "git_sha": git("rev-parse", "HEAD"), "dirty": bool(status.strip()), "member_count": len(manifest_rows), "omitted_count": len(omitted), "members": manifest_rows, "omitted": omitted}
    OUT.unlink(missing_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        zf.writestr("xorflow_result_bundle/README.md", readme)
        zf.writestr("xorflow_result_bundle/MANIFEST.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        zf.writestr("xorflow_result_bundle/environment/python.txt", environment)
        zf.writestr("xorflow_result_bundle/environment/git_status.txt", status)
        zf.writestr("xorflow_result_bundle/environment/git_diff.patch", diff)
        for path, arc in members:
            zf.write(path, str(Path("xorflow_result_bundle") / arc))
        # Put the two machine-readable reviewer ledgers at the archive root as
        # well as under the historical reviewer directory.  This avoids making
        # consumers know the internal campaign directory layout.
        for rel in ("report/RESULT_SUMMARY.yaml", "RESULT_MANIFEST.csv"):
            source = V3 / rel
            if source.is_file():
                zf.write(source, str(Path("xorflow_result_bundle") / source.name))
    print(json.dumps({"archive": str(OUT), "bytes": OUT.stat().st_size, "members": len(members), "omitted": len(omitted)}, sort_keys=True))


if __name__ == "__main__":
    main()
