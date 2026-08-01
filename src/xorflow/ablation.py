"""Same-host baseline selection and component ablations for online XORFLOW."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from dataclasses import dataclass
from typing import Any

import numpy as np

from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.hpca_xorflow_cli import _case, _output_writeback_traffic, _sources
from mosaic_validation.memory_subsystem import build_mixed_sliced_layout, simulate_layout_source_lru, validate_nonoverlap
from .online_replay import unpack_supports
from .serializer import Codec, SerializedRecord, serialize_record


VARIANTS = (
    "BEICSR_OPT", "EVENT_ONLY", "A2_ONLY", "XOR_NO_A2", "GENERIC_XOR_RLE",
    "FULL_ONLINE_SERIAL", "FULL_ONLINE_EVENT", "FORCED_XORFLOW", "PAIR_ORACLE_UPPER_BOUND",
)

BASELINE_COLUMNS = [
    "run_id", "dataset", "model", "seed", "variant", "slice_width", "anchor_policy",
    "support_bytes", "value_bytes", "topology_bytes", "descriptor_bytes", "padding_bytes",
    "total_physical_bytes", "cycles", "energy_nj", "selected_for_headline", "deployable",
]

FORMAT_COLUMNS = ["run_id", "variant", "slice_width", "format", "count", "fraction", "bytes"]


@dataclass(frozen=True)
class Choice:
    name: str
    padded_bytes: int
    unpadded_bytes: int
    payload_bits: int


def _choice(record: SerializedRecord) -> Choice:
    return Choice(record.codec.name, record.padded_bytes, record.unpadded_bytes, record.payload_bits)


def _rle_choice(delta: np.ndarray) -> Choice:
    bits = np.asarray(delta, dtype=bool).reshape(-1)
    if bits.size == 0:
        return Choice("GENERIC_RLE", 64, 4, 16)
    changes = np.flatnonzero(bits[1:] != bits[:-1]) + 1
    runs = np.diff(np.concatenate(([0], changes, [len(bits)])))
    payload = 1 + 2  # initial bit, 16-bit run count
    for length in runs:
        value = int(length)
        payload += 8
        while value >= 128:
            payload += 8; value >>= 7
    unpadded = 2 + math.ceil(payload / 8)
    return Choice("GENERIC_RLE", math.ceil(unpadded / 64) * 64, unpadded, payload)


def choose_record(
    *, variant: str, layer: int, current: np.ndarray, previous: np.ndarray | None,
    future: np.ndarray | None = None,
) -> Choice:
    beic = _choice(serialize_record(current, Codec.BEICSR))
    a0 = _choice(serialize_record(current, Codec.A0))
    a2 = _choice(serialize_record(current, Codec.A2))
    is_anchor = layer % 2 == 0
    if variant == "BEICSR_OPT":
        return beic
    if variant == "EVENT_ONLY":
        return min((beic, a0), key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1))
    if variant == "A2_ONLY":
        return min((beic, a0, a2), key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1, item.name))
    if variant in {"XOR_NO_A2", "GENERIC_XOR_RLE", "FULL_ONLINE_SERIAL", "FULL_ONLINE_EVENT", "FORCED_XORFLOW"}:
        if is_anchor or previous is None:
            candidates = (a0,) if variant == "XOR_NO_A2" else (a0, a2)
            if variant != "FORCED_XORFLOW":
                candidates = (beic, *candidates)
            return min(candidates, key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1, item.name))
        delta_mask = np.logical_xor(previous, current)
        delta = _rle_choice(delta_mask) if variant == "GENERIC_XOR_RLE" else _choice(serialize_record(delta_mask, Codec.DELTA))
        if variant == "FORCED_XORFLOW":
            return delta
        return min((beic, delta), key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1))
    if variant == "PAIR_ORACLE_UPPER_BOUND":
        # Explicitly illegal: the anchor branch may inspect ``future``.  It is
        # isolated here so deployable variants cannot receive the argument.
        pair_anchor = current if is_anchor else previous
        pair_target = future if is_anchor else current
        if pair_anchor is None or pair_target is None:
            return beic
        anchor = min((_choice(serialize_record(pair_anchor, Codec.A0)), _choice(serialize_record(pair_anchor, Codec.A2))), key=lambda item: (item.unpadded_bytes, item.name))
        delta = _choice(serialize_record(np.logical_xor(pair_anchor, pair_target), Codec.DELTA))
        pair_beic = serialize_record(pair_anchor, Codec.BEICSR).unpadded_bytes + serialize_record(pair_target, Codec.BEICSR).unpadded_bytes
        if anchor.unpadded_bytes + delta.unpadded_bytes < pair_beic:
            return anchor if is_anchor else delta
        return beic
    raise ValueError(variant)


def _choose_precomputed(variant: str, layer: int, records: dict[str, Choice]) -> Choice:
    beic, a0, a2 = records["BEICSR"], records["A0"], records["A2"]
    anchor = layer % 2 == 0
    if variant == "BEICSR_OPT": return beic
    if variant == "EVENT_ONLY": return min((beic, a0), key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1))
    if variant == "A2_ONLY": return min((beic, a0, a2), key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1, item.name))
    if variant in {"XOR_NO_A2", "GENERIC_XOR_RLE", "FULL_ONLINE_SERIAL", "FULL_ONLINE_EVENT", "FORCED_XORFLOW"}:
        if anchor or "DELTA" not in records:
            candidates = (a0,) if variant == "XOR_NO_A2" else (a0, a2)
            if variant != "FORCED_XORFLOW": candidates = (beic, *candidates)
            return min(candidates, key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1, item.name))
        delta = records["RLE"] if variant == "GENERIC_XOR_RLE" else records["DELTA"]
        return delta if variant == "FORCED_XORFLOW" else min((beic, delta), key=lambda item: (item.unpadded_bytes, 0 if item.name == "BEICSR" else 1))
    if variant == "PAIR_ORACLE_UPPER_BOUND":
        if "DELTA" not in records: return beic
        anchor_code = min((records.get("PAIR_A0", a0), records.get("PAIR_A2", a2)), key=lambda item: (item.unpadded_bytes, item.name))
        if anchor_code.unpadded_bytes + records["DELTA"].unpadded_bytes < beic.unpadded_bytes + records["PAIR_BEICSR"].unpadded_bytes:
            return anchor_code if anchor else records["DELTA"]
        return beic
    raise ValueError(variant)


def run(
    *, project: Path, config_id: str, output_dir: Path, widths: tuple[int, ...] = (64, 96, 128, 256),
    tile_rows: int = 128, cache_bytes: int = 512 * 1024, edge_order: str = "O0",
    emit_selected_records: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    trace = project / "artifacts_hpca_xorflow" / "workloads" / config_id / "fp8_supports.npz"
    if not trace.exists(): trace = project / "artifacts_final8" / "masks" / f"{config_id}_fp8_supports.npz"
    supports = unpack_supports(trace)
    _, data, dataset = _case(project, config_id)
    if dataset == "Data": dataset = config_id.split("_", 1)[0].title()
    record_path = project / "artifacts_hpca_xorflow" / "workloads" / config_id / "record.json"
    record = json.loads(record_path.read_text()) if record_path.exists() else {"seed": 7, "model_kind": config_id}
    seed = int(record.get("seed", 7)); model = str(record.get("model_kind", "deepres_v2"))
    edge_index = data.edge_index.cpu().numpy(); _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    sources = _sources(edge_index, edge_order); topology_layer = int(edge_index.shape[1] * 4 + (data.num_nodes + 1) * 4)
    results: list[dict[str, Any]] = []; selections: list[dict[str, Any]] = []
    selected_records: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for width in widths:
        slices = math.ceil(supports.shape[2] / width)
        candidate_cache: dict[tuple[int, int, int], dict[str, Choice]] = {}
        for layer, mask in enumerate(supports):
            for tile, start in enumerate(range(0, len(order), tile_rows)):
                nodes = order[start:min(len(order), start + tile_rows)]
                for sid, col in enumerate(range(0, mask.shape[1], width)):
                    stop = min(mask.shape[1], col + width); local = mask[nodes, col:stop]
                    item = {
                        "BEICSR": _choice(serialize_record(local, Codec.BEICSR)),
                        "A0": _choice(serialize_record(local, Codec.A0)),
                        "A2": _choice(serialize_record(local, Codec.A2)),
                    }
                    other = None
                    if layer % 2 == 1:
                        other = supports[layer - 1, nodes, col:stop]
                    elif layer + 1 < len(supports):
                        other = supports[layer + 1, nodes, col:stop]
                    if other is not None:
                        item["DELTA"] = _choice(serialize_record(np.logical_xor(local, other), Codec.DELTA))
                        item["RLE"] = _rle_choice(np.logical_xor(local, other))
                        item["PAIR_BEICSR"] = _choice(serialize_record(other, Codec.BEICSR))
                        if layer % 2 == 1:
                            item["PAIR_A0"] = _choice(serialize_record(other, Codec.A0))
                            item["PAIR_A2"] = _choice(serialize_record(other, Codec.A2))
                    candidate_cache[(layer, tile, sid)] = item
        traffic_cache: dict[tuple[int, bytes], tuple[Any, Any, int]] = {}
        for variant in VARIANTS:
            support_bytes = padding = value_bytes = descriptor = total = decode_bits = 0
            format_counts: dict[str, int] = {}; format_bytes: dict[str, int] = {}
            layouts = []
            record_rows: list[dict[str, Any]] = []
            for layer, mask in enumerate(supports):
                metadata_layer = 0
                formats = np.full((mask.shape[0], slices), "BEICSR", dtype=object)
                for tile, start in enumerate(range(0, len(order), tile_rows)):
                    nodes = order[start:min(len(order), start + tile_rows)]
                    for sid, col in enumerate(range(0, mask.shape[1], width)):
                        stop = min(mask.shape[1], col + width)
                        local = mask[nodes, col:stop]
                        choice = _choose_precomputed(variant, layer, candidate_cache[(layer, tile, sid)])
                        # Preserve the exact per-tile choice that generated the
                        # aggregate byte row.  Final-review event scheduling
                        # consumes this file; it never reconstructs variant
                        # cycles from the historical aggregate cycle column.
                        record_rows.append({
                            "run_id": config_id, "dataset": dataset, "model": model,
                            "seed": seed, "layer": layer, "tile": tile, "slice": sid,
                            "pair_id": layer // 2, "role": "anchor" if layer % 2 == 0 else "target",
                            "chosen_format": "DELTA" if choice.name in {"DELTA", "GENERIC_RLE"} else choice.name,
                            "payload_bits": choice.payload_bits, "header_bits": 16,
                            "unpadded_bytes": choice.unpadded_bytes, "padded_bytes": choice.padded_bytes,
                            "input_support_bits": int(local.size), "rows": int(len(nodes)),
                            "features": int(stop - col), "anchor_read_bytes": 0,
                            "consumer_anchor_read_bytes": 0, "consumer_anchor_decode_cycles": 0,
                        })
                        if choice.name != "BEICSR":
                            formats[nodes, sid] = "XORFLOW"
                            support_bytes += choice.padded_bytes; metadata_layer += choice.padded_bytes
                            padding += choice.padded_bytes - choice.unpadded_bytes
                            decode_bits += choice.padded_bytes * 8
                        format_counts[choice.name] = format_counts.get(choice.name, 0) + 1
                        format_bytes[choice.name] = format_bytes.get(choice.name, 0) + choice.padded_bytes
                signature = np.packbits(formats == "XORFLOW").tobytes()
                cache_key = (layer, signature)
                if cache_key not in traffic_cache:
                    layout = build_mixed_sliced_layout(mask, slice_width=width, formats=formats, node_order=order)
                    if not validate_nonoverlap(layout): raise AssertionError("ablation layout overlap")
                    traffic = simulate_layout_source_lru(layout, sources, capacity_bytes=cache_bytes)
                    base_output = _output_writeback_traffic([layout])
                    traffic_cache[cache_key] = (layout, traffic, base_output)
                layout, traffic, base_output = traffic_cache[cache_key]
                layouts.append(layout)
                output = base_output + 2 * metadata_layer
                total += traffic.read_bytes + traffic.writeback_bytes + topology_layer + output
                value_bytes += int(mask.sum())
                descriptor += int(layout.starts.size * layout.descriptor_bytes)
            total += support_bytes
            cycles = math.ceil(total / 256) + math.ceil(decode_bits / 2048)
            deployable = variant != "PAIR_ORACLE_UPPER_BOUND"
            results.append({
                "run_id": config_id, "dataset": dataset, "model": model, "seed": seed,
                "variant": variant, "slice_width": width, "anchor_policy": "FINITE_RETENTION",
                "support_bytes": support_bytes, "value_bytes": value_bytes,
                "topology_bytes": topology_layer * len(supports), "descriptor_bytes": descriptor,
                "padding_bytes": padding, "total_physical_bytes": total, "cycles": cycles,
                "energy_nj": "", "selected_for_headline": False, "deployable": deployable,
            })
            count = max(sum(format_counts.values()), 1)
            selections.extend({
                "run_id": config_id, "variant": variant, "slice_width": width, "format": name,
                "count": number, "fraction": number / count, "bytes": format_bytes[name],
            } for name, number in sorted(format_counts.items()))
            selected_records[(variant, width)] = record_rows
    # Select each variant's best independently; only deployable BEICSR_OPT and
    # FULL_ONLINE_EVENT rows are eligible for the paper headline.
    for variant in VARIANTS:
        candidates = [row for row in results if row["variant"] == variant]
        selected = min(candidates, key=lambda row: (row["cycles"], row["slice_width"]))
        if emit_selected_records is not None:
            emit_selected_records.mkdir(parents=True, exist_ok=True)
            chosen = selected_records[(variant, int(selected["slice_width"]))]
            path = emit_selected_records / f"{config_id}_{variant}.csv"
            with path.open("w", newline="") as handle:
                fields = list(chosen[0]) if chosen else ["run_id"]
                writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(chosen)
        if variant in {"BEICSR_OPT", "FULL_ONLINE_EVENT"}:
            selected["selected_for_headline"] = True
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / f"baseline_selection_{config_id}.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BASELINE_COLUMNS); writer.writeheader(); writer.writerows(results)
    with (output_dir / f"component_ablation_{config_id}.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BASELINE_COLUMNS); writer.writeheader(); writer.writerows(results)
    with (output_dir / f"format_selection_{config_id}.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FORMAT_COLUMNS); writer.writeheader(); writer.writerows(selections)
    return results, selections


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--config-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--widths", type=int, nargs="+", default=(64, 96, 128, 256))
    parser.add_argument("--edge-order", choices=("O0", "O1"), default="O0")
    parser.add_argument("--emit-selected-records", type=Path)
    args = parser.parse_args()
    results, _ = run(project=args.project.resolve(), config_id=args.config_id, output_dir=args.output_dir, widths=tuple(args.widths), edge_order=args.edge_order, emit_selected_records=args.emit_selected_records)
    print(json.dumps({"rows": len(results), "output": str(args.output_dir)}, sort_keys=True))


if __name__ == "__main__":
    main()
