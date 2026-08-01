#!/usr/bin/env python3
"""Build a compact, reviewer-5 correction archive from audited final artifacts."""
from __future__ import annotations

import csv, hashlib, json, math, shutil, subprocess, tempfile, zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NEW = ROOT / "results_hpca_xorflow/final_review5_calibrated"
VALIDATION = ROOT / "results_hpca_xorflow/final_review5_unified/memory_validation"
OLD = ROOT / "results_hpca_xorflow/review5_acceptance"
R4 = ROOT / "results_hpca_xorflow/final_review4"
ZIP = ROOT / "xorflow_review5_acceptance_bundle.zip"


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as h: return list(csv.DictReader(h))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def cp(src: Path, dst: Path, stage: Path) -> None:
    if not src.is_file(): return
    target = stage / dst; target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, target)


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows: raise RuntimeError(f"no rows for {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def main() -> None:
    stage = Path(tempfile.mkdtemp(prefix="xorflow_review5_"))
    try:
        schedules = sorted((NEW / "primary").glob("*/causal_event_schedule.csv"))
        if len(schedules) != 12: raise RuntimeError(f"expected 12 final schedules, found {len(schedules)}")
        cycle_rows = [r for p in schedules for r in read(p)]
        if len(cycle_rows) != 24: raise RuntimeError("every checkpoint needs BEICSR and XORFLOW rows")
        if any(r["schedule_model"] != "CAUSAL_UNIFIED_8CH_RW_SCALESIM_LAYER_BARRIER" for r in cycle_rows):
            raise RuntimeError("legacy schedule mixed into final results")
        write_csv(stage / "results/final_unified_primary_cycles.csv", cycle_rows)

        xr = [r for r in cycle_rows if r["variant"] == "XORFLOW_ONLINE"]
        speed = [float(r["speedup_vs_selected_baseline"]) for r in xr]
        trace_geo = math.exp(sum(map(math.log, speed)) / len(speed))
        grouped: dict[str, list[float]] = defaultdict(list)
        for r, s in zip(xr, speed):
            name = r["run_id"]; ds = "arxiv" if name.startswith("ogbn_arxiv") else name.split("_", 1)[0]
            grouped[ds].append(s)
        ds_values = [math.exp(sum(map(math.log, v)) / len(v)) for v in grouped.values()]
        balanced = math.exp(sum(map(math.log, ds_values)) / len(ds_values))

        # The timing scale is fitted once on Flickr-s7 and then frozen. Flickr-s17
        # is a held-out absolute completion-time validation; its external result
        # is never used to fit the prediction.
        mem_rows = read(VALIDATION / "heldout_absolute_validation.csv")
        write_csv(stage / "results/heldout_absolute_memory_validation.csv", mem_rows)

        byte_ablation = []
        for r in read(OLD / "results/unified_ablation.csv"):
            byte_ablation.append({k: r[k] for k in (
                "run_id", "variant", "baseline_support_bytes", "variant_support_bytes",
                "baseline_total_bytes", "variant_total_bytes", "producer_anchor_bytes",
                "consumer_anchor_bytes",
            )})
        write_csv(stage / "results/ablation_bytes_only.csv", byte_ablation)

        report = ["# XORFLOW reviewer-5 correction results", "",
                  "All numbers below are modeled aggregation+combination-subsystem results, not end-to-end GNN speedups.", "",
                  "## Final common scheduler", "",
                  "Every producer-anchor read, target/consumer read, and output writeback contends in one persistent eight-channel resource. The model separates a 32-entry request queue from eight timing-active channel slots, uses deterministic physical-address striping, charges read/write turnaround, resumes dependents only on completion, and retains layer barriers. Combination service comes from the versioned 32x32 weight-stationary SCALE-Sim shape cache and is consumed once per executed record.", "",
                  f"Coverage: **{len(xr)} checkpoints**, including Flickr seeds 7, 17, and 27. Trace geomean: **{trace_geo:.3f}x**; dataset-balanced geomean: **{balanced:.3f}x**; range **{min(speed):.3f}x–{max(speed):.3f}x**; regressions: **{sum(x < 1 for x in speed)}**.", "",
                  "| Checkpoint | BEICSR cycles | XORFLOW cycles | Speedup |", "|---|---:|---:|---:|"]
        for r in sorted(xr, key=lambda x: x["run_id"]):
            b = next(x for x in cycle_rows if x["run_id"] == r["run_id"] and x["variant"] == "BEICSR_OPT")
            report.append(f"| {r['run_id']} | {int(b['total_cycles']):,} | {int(r['total_cycles']):,} | {float(r['speedup_vs_selected_baseline']):.3f}x |")
        report += ["", "## Held-out absolute external-memory validation", "",
                   "The HBM timing scale is fitted only on Flickr seed 7 and then frozen. Flickr seed 17 is a held-out absolute Ramulator2 completion-time comparison; its external completion is not used during calibration.", "",
                   "| Case | Internal cycles | Ramulator2 cycles | Error | Requests |", "|---|---:|---:|---:|---:|"]
        for r in mem_rows:
            manifest = json.loads((R4 / "full_network_external" / r["case"] / "manifest.json").read_text())
            report.append(f"| {r['case']} | {int(float(r['prediction_cycles'])):,} | {int(float(r['ramulator2_cycles'])):,} | {float(r['absolute_error_percent']):.2f}% | {int(manifest['combined_requests']):,} |")
        report += ["", "## Hardware and ablation scope", "",
                   "The complete variable-length RTL source and the unbounded Yosys log are included. Tile-scale event discovery/packing and routed consumer evidence remain valid. The archive does not invent full-packer PPA if global elaboration has not completed.",
                   "Non-complete variants are restricted to exact common-accounting byte attribution in `results/ablation_bytes_only.csv`. No legacy cycle estimate is used for performance attribution; complete XORFLOW alone is replayed through the corrected final scheduler."]
        (stage / "REVIEW5_FINAL_REPORT.md").write_text("\n".join(report) + "\n")

        # Compact evidence only; raw traces are represented by hashes/manifests.
        for p in schedules:
            cfg = p.parent.name
            for name in ("causal_event_schedule.csv", "causal_resource_audit.csv", "causal_recurrence_check.csv"):
                cp(p.parent / name, Path("results/schedule_detail") / cfg / name, stage)
        for src, dst in [
            (OLD / "results/anchor_lifecycle_summary.csv", Path("results/anchor_lifecycle_summary.csv")),
            (OLD / "results/producer_dependency_audit.csv", Path("results/producer_dependency_audit.csv")),
            (R4 / "flickr_extra/results/anchor_lifecycle_summary.csv", Path("results/flickr_extra_anchor_lifecycle.csv")),
            (ROOT / "artifacts_hpca_xorflow/scalesim_final_schedule/shape_cache.json", Path("results/scalesim_shape_cache.json")),
            (R4 / "packer_synthesis/yosys_full_wide_unbounded.log", Path("hardware/yosys_full_wide_unbounded.log")),
            (OLD / "results/hardware/encoder_synth.json", Path("hardware/encoder_tile_synthesis.json")),
            (OLD / "results/hardware/decoder_cluster_openroad_summary.json", Path("hardware/decoder_cluster_openroad_summary.json")),
            (OLD / "results/hardware/stream_equivalence.csv", Path("hardware/stream_equivalence.csv")),
            (VALIDATION / "heldout_absolute_validation.csv", Path("memory/heldout_absolute_validation.csv")),
            (VALIDATION / "memory_timing_model.json", Path("memory/memory_timing_model.json")),
            (NEW / "logs/pytest_causal.log", Path("logs/pytest_causal.log")),
            (NEW / "logs/pytest_causal.exit", Path("logs/pytest_causal.exit")),
        ]: cp(src, dst, stage)
        for case in ("flickr_s7", "flickr_s17"):
            cp(R4 / "full_network_external" / case / "manifest.json", Path("memory") / case / "manifest.json", stage)
            cp(R4 / "full_network_external" / case / "ramulator2.json", Path("memory") / case / "ramulator2.json", stage)
            cp(VALIDATION / f"{case}_direct_internal.txt", Path("memory") / f"{case}_direct_internal.txt", stage)
        for rel in ("src/xorflow/causal_schedule.py", "tests/test_causal_schedule.py", "scripts/run_review5_unified_primary.sh", "scripts/build_review5_correction_bundle.py", "rtl/xorflow_encoder_pipelined.sv"):
            cp(ROOT / rel, Path("source") / rel, stage)
        provenance = {"git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "files": {}}
        for p in sorted(stage.rglob("*")):
            if p.is_file(): provenance["files"][str(p.relative_to(stage))] = {"bytes": p.stat().st_size, "sha256": digest(p)}
        for case in ("flickr_s7", "flickr_s17"):
            p = R4 / "full_network_external" / case / f"{case}_full.trace"
            provenance.setdefault("external_large_traces", []).append({"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": digest(p)})
        (stage / "MANIFEST.json").write_text(json.dumps(provenance, indent=2, sort_keys=True) + "\n")
        if ZIP.exists(): ZIP.unlink()
        with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p in sorted(stage.rglob("*")):
                if p.is_file(): z.write(p, p.relative_to(stage).as_posix())
        if ZIP.stat().st_size >= 100_000_000: raise RuntimeError("archive exceeds 100 MB")
        print(f"archive={ZIP}\nbytes={ZIP.stat().st_size}\nsha256={digest(ZIP)}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)


if __name__ == "__main__": main()
