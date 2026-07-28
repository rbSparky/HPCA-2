"""Event-level host timing model for the causal XORFLOW memory subsystem.

The host is deliberately conventional: eight aggregation engines and eight
32×32 WS combination engines.  XORFLOW changes only support/value movement,
not the arithmetic result or the systolic combination mapping.  This module
combines exact cache-line traffic from the preflight with calibrated SCALE-Sim
combination cycles and explicit encoder/decoder/output pipeline stages.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
import argparse
from pathlib import Path

import pandas as pd

from .hpca_scalesim import calibrate_gemm


@dataclass(frozen=True)
class HostConfig:
    aggregation_engines: int = 8
    # 8 × 32 FP8 lanes can consume the 256 B/cycle principal HBM interface;
    # 16 lanes is retained as an explicit sensitivity, not the headline host.
    aggregation_simd: int = 32
    combination_engines: int = 8
    frequency_ghz: float = 1.0
    dram_bytes_per_cycle: int = 256
    encode_bits_per_cycle: int = 2048
    decode_bits_per_cycle: int = 2048
    support_cache_bytes: int = 16 * 1024
    double_buffered: bool = True


def _support_cache_fit(tile_rows: int, slice_width: int, budget: int) -> bool:
    # Reconstructed support plus 32-bit row prefixes and one compact descriptor
    # per row.  Anchor stream is separately buffered in metadata SRAM.
    return tile_rows * math.ceil(slice_width / 8) + tile_rows * 5 <= budget


def model_host(project: Path, preflight: pd.DataFrame, *, artifact_dir: Path, config: HostConfig = HostConfig()) -> pd.DataFrame:
    """Model all preflight pairs under one normalized host configuration."""
    rows: list[dict] = []
    for item in preflight.to_dict("records"):
        nodes = int(item["nodes"])
        width = int(item["slice_width"])
        # Equal contiguous row partitions across the unchanged eight engines.
        gemm = calibrate_gemm(
            project, artifact_dir / "scalesim", m=math.ceil(nodes / config.combination_engines), n=width, k=width
        )
        combination_cycles = gemm.cycles if gemm.success else 0
        aggregation_cycles = math.ceil(
            (float(item["aggregation_active_values"]) / config.aggregation_engines)
            * float(item["aggregation_load_imbalance"])
            / config.aggregation_simd
        )
        descriptor_cycles = int(item["descriptor_cycles"])
        beic_memory = math.ceil(int(item["beicsr_total_bytes"]) / config.dram_bytes_per_cycle)
        xor_memory = math.ceil(int(item["xorflow_total_bytes"]) / config.dram_bytes_per_cycle)
        decode_cycles = math.ceil(int(item["xorflow_support_bits"]) / config.decode_bits_per_cycle)
        # One full tile-slice passes the encoder/compactor in 32×64-bit lanes.
        encode_cycles = math.ceil(int(item["pair_active_values"]) / max(config.encode_bits_per_cycle // 8, 1))
        support_cache_ok = _support_cache_fit(int(item["tile_rows"]), width, config.support_cache_bytes)
        # First output has no predecessor overlap.  Thereafter two tile buffers
        # permit memory/decode/aggregation to overlap with unchanged combination.
        beic_memory_stage = beic_memory + descriptor_cycles
        xor_memory_stage = xor_memory + descriptor_cycles + decode_cycles + encode_cycles
        if config.double_buffered:
            xor_stream_stage = max(xor_memory + decode_cycles, aggregation_cycles, encode_cycles) + descriptor_cycles
            beic_stream_stage = max(beic_memory, aggregation_cycles) + descriptor_cycles
        else:
            xor_stream_stage = xor_memory_stage + aggregation_cycles
            beic_stream_stage = beic_memory_stage + aggregation_cycles
        beic_total = beic_stream_stage + combination_cycles
        xor_total = xor_stream_stage + combination_cycles
        rows.append({
            "config_id": item["config_id"],
            "pair_start_layer": item["pair_start_layer"],
            "pair_end_layer": item["pair_end_layer"],
            "slice_width": width,
            "tile_rows": item["tile_rows"],
            "feature_cache_bytes": item["feature_cache_bytes"],
            "beicsr_memory_cycles": beic_memory,
            "xorflow_memory_cycles": xor_memory,
            "aggregation_cycles": aggregation_cycles,
            "descriptor_cycles": descriptor_cycles,
            "support_decode_cycles": decode_cycles,
            "support_encode_cycles": encode_cycles,
            "combination_scalesim_cycles_per_engine": combination_cycles,
            "combination_scalesim_utilization": gemm.utilization,
            "combination_scalesim_success": gemm.success,
            "support_cache_fits": support_cache_ok,
            "beicsr_host_cycles": beic_total,
            "xorflow_host_cycles": xor_total,
            "host_speedup": beic_total / max(xor_total, 1),
            "beicsr_stream_cycles": beic_stream_stage,
            "xorflow_stream_cycles": xor_stream_stage,
            "double_buffered": config.double_buffered,
            "model_scope": "aggregation+combination+support_io; energy_pending",
        })
    return pd.DataFrame(rows)


def write_host_results(project: Path, preflight_path: Path, *, output: Path, artifact_dir: Path, config: HostConfig = HostConfig()) -> pd.DataFrame:
    frame = pd.read_csv(preflight_path)
    required = {"aggregation_simd_cycles_8x16", "pair_active_values", "beicsr_output_write_bytes", "xorflow_output_write_bytes"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"stale preflight schema; rerun causal preflight before host modeling: {missing}")
    result = model_host(project, frame, artifact_dir=artifact_dir, config=config)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Model the common XORFLOW host from causal preflight data.")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--input", type=Path, help="configuration-specific causal-preflight CSV")
    parser.add_argument("--output", type=Path, help="configuration-specific host-model CSV")
    args = parser.parse_args()
    project = args.project.resolve()
    input_path = args.input or (project / "results_hpca_xorflow/01_causal_pair_preflight.csv")
    output_path = args.output or (project / "results_hpca_xorflow/02_host_model.csv")
    if not input_path.is_absolute():
        input_path = project / input_path
    if not output_path.is_absolute():
        output_path = project / output_path
    result = write_host_results(project, input_path, output=output_path, artifact_dir=project / "artifacts_hpca_xorflow")
    print(result.to_string(index=False))


if __name__ == "__main__":
    main()
