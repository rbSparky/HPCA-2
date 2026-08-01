#!/usr/bin/env python3
"""Regenerate ablation cycles with the final causal finite-queue scheduler.

The historical ablation table intentionally kept only common-accounting bytes.
This driver converts the exact selected-record files emitted by
``xorflow.ablation`` into variant traffic/encoder inputs and runs the same
producer/consumer event schedule used by the headline result.  It is a
bounded, deterministic post-processing pass; no training or support capture is
performed here.
"""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

from xorflow.causal_schedule import simulate
from xorflow.online_replay import unpack_supports


def read(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def write(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"no rows for {path}")
    fields = list(rows[0])
    with path.open("w", newline="") as handle:
        out = csv.DictWriter(handle, fieldnames=fields)
        out.writeheader(); out.writerows(rows)


def prepare_variant(
    selected: Path, lifecycle: Path, traffic: Path, encoder: Path,
    work: Path, variant: str,
) -> tuple[Path, Path, Path]:
    rows = read(selected)
    # Recover the actual panel geometry from the cached support tensor.  This
    # also repairs old selected-record files generated before the loop-local
    # geometry fix; only descriptor fields are corrected, never the choice or
    # padded-byte accounting.
    trace = Path("artifacts_hpca_xorflow/workloads") / rows[0]["run_id"] / "fp8_supports.npz"
    if not trace.exists():
        trace = Path("artifacts_final8/masks") / f"{rows[0]['run_id']}_fp8_supports.npz"
    support_shape = unpack_supports(trace).shape
    n_rows, n_features = int(support_shape[1]), int(support_shape[2])
    n_slices = max(int(r["slice"]) for r in rows) + 1
    nominal_width = math.ceil(n_features / n_slices)
    life = {(int(r["layer"]), int(r["tile"]), int(r["slice"])): r for r in read(lifecycle)}
    by_layer: dict[int, list[dict[str, str]]] = {}
    for row in rows:
        key = (int(row["layer"]), int(row["tile"]), int(row["slice"]))
        rec = life.get(key)
        is_delta = row.get("chosen_format") == "DELTA" and row.get("role") == "target"
        row["anchor_read_bytes"] = rec.get("anchor_read_bytes", "0") if is_delta and rec else "0"
        row["consumer_anchor_read_bytes"] = rec.get("consumer_anchor_read_bytes", "0") if is_delta and rec else "0"
        row["consumer_anchor_decode_cycles"] = rec.get("consumer_anchor_decode_cycles", "0") if is_delta and rec else "0"
        # Older emitted files came from a loop whose final-slice variables
        # escaped the loop.  Repair dimensions from tile/slice and the source
        # traffic/record geometry before scheduling; this does not alter the
        # selected format or byte count.
        sid = int(row["slice"]); tile = int(row["tile"])
        row["features"] = str(min(nominal_width, n_features - sid * nominal_width))
        row["rows"] = str(min(128, n_rows - tile * 128))
        row["input_support_bits"] = str(int(row["features"]) * int(row["rows"]))
        by_layer.setdefault(int(row["layer"]), []).append(row)
    record_path = work / f"{variant}_records.csv"
    write(record_path, rows)

    traffic_rows = read(traffic)
    selected_meta = {layer: sum(int(r["padded_bytes"]) for r in rs) for layer, rs in by_layer.items()}
    selected_anchor = {layer: sum(int(r.get("anchor_read_bytes") or 0) for r in rs) for layer, rs in by_layer.items()}
    selected_consumer = {layer: sum(int(r.get("consumer_anchor_read_bytes") or 0) for r in rs) for layer, rs in by_layer.items()}
    if variant != "COMPLETE_XORFLOW":
        for tr in traffic_rows:
            layer = int(tr["layer"])
            old_meta = int(tr.get("xorflow_metadata_bytes", 0)); old_anchor = int(tr.get("xorflow_anchor_read_bytes", 0))
            meta = selected_meta.get(layer, old_meta); anchor = selected_anchor.get(layer, old_anchor)
            tr["xorflow_metadata_bytes"] = str(meta)
            tr["xorflow_anchor_read_bytes"] = str(anchor)
            # The event scheduler adds consumer rereads as a separate dependency;
            # keep total bytes explicit too so the variant traffic is auditable.
            old_total = int(tr.get("xorflow_total_bytes", 0))
            tr["xorflow_total_bytes"] = str(old_total - old_meta - old_anchor + meta + anchor + selected_consumer.get(layer, 0))
    traffic_path = work / f"{variant}_traffic.csv"; write(traffic_path, traffic_rows)

    enc_rows = read(encoder)
    original_enc_rows = [dict(r) for r in enc_rows]
    rate_by_layer = {int(r["layer"]): float(r.get("achieved_input_bits_per_cycle", 1.0)) for r in enc_rows}
    bits_by_layer = {layer: sum(int(r.get("payload_bits", 0)) + int(r.get("header_bits", 0)) for r in rs) for layer, rs in by_layer.items()}
    if variant != "COMPLETE_XORFLOW":
        for er in enc_rows:
            layer = int(er["layer"]); rate = max(rate_by_layer.get(layer, 1.0), 1e-9)
            er["total_cycles"] = str(max(1, math.ceil(bits_by_layer.get(layer, 0) / rate)))
            er["input_bits"] = str(bits_by_layer.get(layer, int(er.get("input_bits", 0))))
    else:
        enc_rows = original_enc_rows
    encoder_path = work / f"{variant}_encoder.csv"; write(encoder_path, enc_rows)
    return record_path, traffic_path, encoder_path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, default=Path.cwd())
    p.add_argument("--config-id", required=True)
    p.add_argument("--selected-dir", type=Path, required=True)
    p.add_argument("--lifecycle", type=Path, required=True)
    p.add_argument("--traffic", type=Path, required=True)
    p.add_argument("--encoder", type=Path, required=True)
    p.add_argument("--decoder", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--variants", nargs="+", default=["EVENT_ONLY", "A2_ONLY", "XOR_NO_A2", "GENERIC_XOR_RLE", "FULL_ONLINE_SERIAL", "FULL_ONLINE_EVENT", "FORCED_XORFLOW", "PAIR_ORACLE_UPPER_BOUND", "COMPLETE_XORFLOW"])
    args = p.parse_args()
    outputs: list[dict[str, object]] = []
    for variant in args.variants:
        selected = args.selected_dir / f"{args.config_id}_{variant}.csv"
        # COMPLETE_XORFLOW is the exact final-primary choice, not a second
        # optimizer.  Reuse its augmented committed records so the equality
        # check can compare integer bytes/cycles against the headline run.
        if variant == "COMPLETE_XORFLOW" and not selected.exists():
            selected = args.lifecycle
        if not selected.exists():
            continue
        work = args.output_dir / "prepared" / variant
        records, traffic, encoder = prepare_variant(selected, args.lifecycle, args.traffic, args.encoder, work, variant)
        out = args.output_dir / variant
        rows = simulate(project=args.project.resolve(), config_id=args.config_id,
                        records_path=records, traffic_path=traffic, encoder_path=encoder,
                        decoder_path=args.decoder, output_dir=out,
                        variants=("BEICSR_OPT", variant))
        outputs.extend(rows)
    write(args.output_dir / "final_ablation_cycles.csv", outputs)
    print(f"wrote {len(outputs)} final causal rows to {args.output_dir}")


if __name__ == "__main__":
    main()
