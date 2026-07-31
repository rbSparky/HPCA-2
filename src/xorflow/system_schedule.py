"""Finite-resource event-driven XORFLOW/BEICSR host schedule.

The simulator consumes the exact online record table and exact per-layer cache
traffic.  It never replaces byte traffic with logical nonzero counts.  Tile
traffic is apportioned by each tile's exact source-degree-weighted active-value
work; the apportioned integers are corrected so that they sum to the measured
layer byte total.  Eight memory channels, aggregation engines, and combination
engines are explicit finite servers, as are decoder clusters and encoder
working buffers.  Layer barriers include output writeback completion.
"""
from __future__ import annotations

import argparse, csv, json, math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from mosaic_validation.graph_order import symmetrized_edges_and_rcm
from mosaic_validation.hpca_scalesim import calibrate_gemm
from mosaic_validation.hpca_xorflow_cli import _case
from .online_replay import unpack_supports


SYSTEM_COLUMNS = [
    "run_id", "dataset", "model", "seed", "variant", "slice_width", "anchor_policy",
    "queue_config", "total_cycles", "memory_cycles", "decode_cycles", "aggregation_cycles",
    "combination_cycles", "encode_cycles", "writeback_cycles", "fill_cycles", "drain_cycles",
    "barrier_cycles", "producer_stall_cycles", "decoder_stall_cycles", "memory_stall_cycles",
    "speedup_vs_selected_baseline",
]


@dataclass
class Pool:
    count: int
    queue_depth: int
    free: list[int] | None = None
    busy_cycles: int = 0
    stall_cycles: int = 0

    def __post_init__(self) -> None:
        self.free = [0] * self.count

    def issue(self, ready: int, service: int, affinity: int | None = None) -> tuple[int, int]:
        assert self.free is not None
        if affinity is None:
            lane = min(range(self.count), key=lambda i: (self.free[i], i))
        else:
            lane = affinity % self.count
        start = max(ready, self.free[lane])
        self.stall_cycles += max(0, start - ready)
        done = start + max(service, 0)
        self.free[lane] = done
        self.busy_cycles += max(service, 0)
        return start, done


def _partition(total: int, weights: np.ndarray) -> np.ndarray:
    """Largest-remainder integer partition with an exact sum."""
    if total <= 0:
        return np.zeros(len(weights), dtype=np.int64)
    values = np.asarray(weights, dtype=np.float64)
    if values.sum() <= 0:
        values = np.ones(len(values), dtype=np.float64)
    raw = values / values.sum() * total
    base = np.floor(raw).astype(np.int64)
    remaining = total - int(base.sum())
    if remaining:
        order = np.argsort(-(raw - base), kind="stable")
        base[order[:remaining]] += 1
    assert int(base.sum()) == total
    return base


def _read(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open()))


def _write(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns); writer.writeheader(); writer.writerows(rows)


def simulate(
    *, project: Path, config_id: str, records_path: Path, traffic_path: Path,
    encoder_path: Path, decoder_path: Path, output_dir: Path,
    queue_config: str = "iq4_work2_of8_parallel", decoder_banks: int = 16,
) -> list[dict[str, Any]]:
    records = _read(records_path); traffic = {int(r["layer"]): r for r in _read(traffic_path)}
    enc = [r for r in _read(encoder_path) if r["queue_config"] == queue_config]
    if not enc: raise ValueError(f"missing encoder configuration {queue_config}")
    enc_layer = {int(r["layer"]): r for r in enc}
    decoder = next(r for r in _read(decoder_path) if int(r["banks"]) == decoder_banks)
    decode_rate = float(decoder["achieved_encoded_bits_per_cycle"])
    if decode_rate <= 0: raise ValueError("nonpositive measured decoder rate")
    _, data, dataset = _case(project, config_id)
    if dataset == "Data": dataset = config_id.split("_", 1)[0].title()
    trace = project / "artifacts_hpca_xorflow/workloads" / config_id / "fp8_supports.npz"
    if not trace.exists(): trace = project / "artifacts_final8/masks" / f"{config_id}_fp8_supports.npz"
    supports = unpack_supports(trace)
    _, order = symmetrized_edges_and_rcm(data.edge_index, data.num_nodes)
    src_degree = np.bincount(data.edge_index[0].cpu().numpy(), minlength=data.num_nodes)
    record_path = project / "artifacts_hpca_xorflow/workloads" / config_id / "record.json"
    record_meta = json.loads(record_path.read_text()) if record_path.exists() else {"seed": 7, "model_kind": config_id}
    seed = int(record_meta.get("seed", 7)); model = str(record_meta.get("model_kind", "deepres_v2"))
    width = int(records[0]["features"]); tile_rows = 128
    gemm_cache: dict[int, int] = {}
    by_layer: dict[int, list[dict[str, str]]] = {}
    for row in records: by_layer.setdefault(int(row["layer"]), []).append(row)

    outputs: list[dict[str, Any]] = []; event_rows: list[dict[str, Any]] = []
    for variant in ("BEICSR_OPT", "XORFLOW_ONLINE"):
        memory = Pool(8, 32); decoder_pool = Pool(4, 16); aggregation = Pool(8, 8)
        combination = Pool(8, 8); encoder = Pool(2, 8)
        barrier = 0; first_start = None; final_done = 0
        decode_sum = agg_sum = comb_sum = encode_sum = write_sum = barrier_sum = 0
        for layer in sorted(by_layer):
            local_rows = sorted(by_layer[layer], key=lambda r: (int(r["tile"]), int(r["slice"])))
            layer_start = barrier
            weighted = []
            for row in local_rows:
                tile = int(row["tile"]); sid = int(row["slice"])
                nodes = order[tile * tile_rows:min(len(order), (tile + 1) * tile_rows)]
                col = sid * width; stop = min(supports.shape[2], col + int(row["features"]))
                weighted.append(int((supports[layer, nodes, col:stop].sum(axis=1) * src_degree[nodes]).sum()))
            tr = traffic[layer]
            if variant == "BEICSR_OPT":
                input_total = int(tr["baseline_feature_read_bytes"]) + int(tr["baseline_topology_bytes"])
                output_total = int(tr["baseline_output_bytes"]) + int(tr["baseline_writeback_bytes"])
            else:
                input_total = (int(tr["xorflow_feature_read_bytes"]) + int(tr["xorflow_metadata_bytes"])
                               + int(tr["xorflow_anchor_read_bytes"]) + int(tr["xorflow_topology_bytes"]))
                output_total = int(tr["xorflow_output_bytes"]) + int(tr["xorflow_writeback_bytes"])
            input_parts = _partition(input_total, np.asarray(weighted)); output_parts = _partition(output_total, np.asarray(weighted))
            layer_done = layer_start
            pending_writebacks: list[tuple[int, int, int, dict[str, Any]]] = []
            for ordinal, (row, active, in_bytes, out_bytes) in enumerate(zip(local_rows, weighted, input_parts, output_parts)):
                tile = int(row["tile"]); descriptor_ready = layer_start + ordinal
                mem_service = math.ceil(int(in_bytes) / 32) + (50 if in_bytes else 0)
                _, mem_done = memory.issue(descriptor_ready, mem_service, affinity=tile)
                bits = (int(row["padded_bytes"]) if variant == "XORFLOW_ONLINE" else math.ceil(int(row["input_support_bits"]) / 8 / 64) * 64) * 8
                dec_service = math.ceil(bits / decode_rate)
                _, dec_done = decoder_pool.issue(descriptor_ready, dec_service)
                agg_service = math.ceil(active / 32)
                _, agg_done = aggregation.issue(max(mem_done, dec_done), agg_service)
                rows_n = int(row["rows"])
                if rows_n not in gemm_cache:
                    gemm_cache[rows_n] = calibrate_gemm(project, output_dir / "scalesim", m=rows_n, k=supports.shape[2], n=supports.shape[2]).cycles
                _, comb_done = combination.issue(agg_done, gemm_cache[rows_n])
                if variant == "XORFLOW_ONLINE":
                    layer_cycles = int(float(enc_layer[layer]["total_cycles"]))
                    enc_service = max(1, math.ceil(layer_cycles / len(local_rows)))
                    _, enc_done = encoder.issue(comb_done, enc_service)
                else:
                    enc_service = 0; enc_done = comb_done
                first_start = descriptor_ready if first_start is None else min(first_start, descriptor_ready)
                decode_sum += dec_service; agg_sum += agg_service; comb_sum += gemm_cache[rows_n]
                encode_sum += enc_service
                event = {"run_id": config_id, "variant": variant, "layer": layer, "tile": tile,
                    "slice": int(row["slice"]), "descriptor_ready": descriptor_ready, "memory_done": mem_done,
                    "decode_done": dec_done, "aggregation_done": agg_done, "combination_done": comb_done,
                    "encode_done": enc_done, "writeback_done": -1, "input_bytes": int(in_bytes),
                    "output_bytes": int(out_bytes), "aggregation_active_values": active}
                event_rows.append(event)
                pending_writebacks.append((enc_done, tile, int(out_bytes), event))
            # Input requests have priority within a layer.  Scheduling their
            # known arrivals before future-ready writebacks avoids the causal
            # time-inversion produced by inserting a late writeback into a
            # FIFO and then discovering an earlier input request.
            for enc_done, tile, out_bytes, event in sorted(pending_writebacks):
                wb_service = math.ceil(out_bytes / 32) + (50 if out_bytes else 0)
                _, done = memory.issue(enc_done, wb_service, affinity=tile)
                event["writeback_done"] = done
                write_sum += wb_service
                layer_done = max(layer_done, done); final_done = max(final_done, done)
            barrier_sum += max(0, layer_done - layer_start)
            barrier = layer_done
        outputs.append({"run_id": config_id, "dataset": dataset, "model": model, "seed": seed,
            "variant": variant, "slice_width": width, "anchor_policy": "FINITE_RETENTION",
            "queue_config": queue_config, "total_cycles": final_done, "memory_cycles": memory.busy_cycles,
            "decode_cycles": decode_sum, "aggregation_cycles": agg_sum, "combination_cycles": comb_sum,
            "encode_cycles": encode_sum, "writeback_cycles": write_sum,
            "fill_cycles": 0 if first_start is None else first_start, "drain_cycles": 0,
            "barrier_cycles": barrier_sum, "producer_stall_cycles": encoder.stall_cycles,
            "decoder_stall_cycles": decoder_pool.stall_cycles, "memory_stall_cycles": memory.stall_cycles,
            "speedup_vs_selected_baseline": 1.0})
    base = next(r for r in outputs if r["variant"] == "BEICSR_OPT")["total_cycles"]
    for row in outputs: row["speedup_vs_selected_baseline"] = base / max(row["total_cycles"], 1)
    _write(output_dir / "system_cycles.csv", SYSTEM_COLUMNS, outputs)
    _write(output_dir / "tile_event_trace.csv", list(event_rows[0]), event_rows)
    analytical = [{"run_id": r["run_id"], "variant": r["variant"],
        "analytical_cycles": max(r["memory_cycles"] // 8, r["aggregation_cycles"] // 8, r["combination_cycles"] // 8) + r["encode_cycles"],
        "event_cycles": r["total_cycles"], "relative_error": abs((max(r["memory_cycles"] // 8, r["aggregation_cycles"] // 8, r["combination_cycles"] // 8) + r["encode_cycles"]) - r["total_cycles"]) / max(r["total_cycles"], 1),
        "critical_path_component": max(("memory", r["memory_cycles"]), ("aggregation", r["aggregation_cycles"]), ("combination", r["combination_cycles"]), key=lambda x:x[1])[0]} for r in outputs]
    _write(output_dir / "analytical_vs_event.csv", list(analytical[0]), analytical)
    return outputs


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument("--project",type=Path,default=Path.cwd()); p.add_argument("--config-id",required=True)
    p.add_argument("--records",type=Path,required=True); p.add_argument("--traffic",type=Path,required=True)
    p.add_argument("--encoder",type=Path,required=True); p.add_argument("--decoder",type=Path,required=True); p.add_argument("--output-dir",type=Path,required=True)
    a=p.parse_args(); rows=simulate(project=a.project.resolve(),config_id=a.config_id,records_path=a.records,traffic_path=a.traffic,encoder_path=a.encoder,decoder_path=a.decoder,output_dir=a.output_dir)
    print(json.dumps(rows,sort_keys=True))

if __name__ == "__main__": main()
