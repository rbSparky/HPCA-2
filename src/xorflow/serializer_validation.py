"""Generate serializer round-trip evidence and human-inspectable golden vectors."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import random

import numpy as np

from .online_replay import unpack_supports
from .serializer import Codec, FormatError, decode_record, serialize_record


COLUMNS = [
    "case_id", "source", "codec", "R", "C", "event_count", "encoded_bits",
    "unpadded_bytes", "padded_bytes", "analytic_bits_match", "roundtrip_match",
    "malformed_detected", "input_sha256", "stream_sha256",
]


def _hash_support(value: np.ndarray) -> str:
    return hashlib.sha256(np.packbits(np.asarray(value, dtype=bool).reshape(-1)).tobytes()).hexdigest()


def validate_case(case_id: str, source: str, support: np.ndarray, codec: Codec) -> dict[str, object]:
    record = serialize_record(support, codec)
    decoded = decode_record(record.data, rows=support.shape[0], features=support.shape[1])
    malformed = bytearray(record.data)
    malformed[-1] = 1
    detected = False
    try:
        decode_record(bytes(malformed), rows=support.shape[0], features=support.shape[1])
    except FormatError:
        detected = True
    return {
        "case_id": case_id, "source": source, "codec": codec.name, "R": support.shape[0],
        "C": support.shape[1], "event_count": record.event_count,
        "encoded_bits": record.payload_bits, "unpadded_bytes": record.unpadded_bytes,
        "padded_bytes": record.padded_bytes,
        "analytic_bits_match": record.payload_bits == decoded.payload_bits_consumed,
        "roundtrip_match": bool(np.array_equal(decoded.support, support)),
        "malformed_detected": detected, "input_sha256": _hash_support(support),
        "stream_sha256": record.sha256,
    }


def validate_trace(
    trace: Path, output: Path, *, source_name: str, tile_rows: int = 128,
    slice_width: int = 128, max_records: int | None = None,
) -> Path:
    supports = unpack_supports(trace)
    rows: list[dict[str, object]] = []
    visited = 0
    for layer, mask in enumerate(supports):
        for tile, row_start in enumerate(range(0, mask.shape[0], tile_rows)):
            for feature_slice, col_start in enumerate(range(0, mask.shape[1], slice_width)):
                local = mask[row_start:min(mask.shape[0], row_start + tile_rows), col_start:min(mask.shape[1], col_start + slice_width)]
                for codec in Codec:
                    rows.append(validate_case(f"{source_name}:l{layer}:t{tile}:s{feature_slice}:{codec.name}", source_name, local, codec))
                visited += 1
                if max_records is not None and visited >= max_records:
                    break
            if max_records is not None and visited >= max_records:
                break
        if max_records is not None and visited >= max_records:
            break
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return output


def generate_golden(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7007)
    cases: list[tuple[str, np.ndarray]] = [
        ("all_zero", np.zeros((8, 32), dtype=bool)),
        ("all_one", np.ones((8, 32), dtype=bool)),
        ("diagonal", np.eye(8, 32, dtype=bool)),
        ("cohort_tie", np.vstack([np.ones((4, 32), dtype=bool), np.zeros((4, 32), dtype=bool)])),
        ("gap255_256", np.isin(np.arange(256), [0, 255]).reshape(8, 32)),
    ]
    for density in (0.01, 0.05, 0.10, 0.25, 0.5):
        cases.append((f"random_d{int(density*100):02d}", rng.random((8, 32)) < density))
    emitted = 0
    for name, support in cases:
        for codec in Codec:
            if emitted >= 24:
                return
            record = serialize_record(support, codec)
            stem = output / f"{emitted:02d}_{name}_{codec.name.lower()}"
            stem.with_suffix(".bin").write_bytes(record.data)
            decoded = decode_record(record.data, rows=support.shape[0], features=support.shape[1])
            metadata = {
                "case_name": name, "codec": codec.name, "rows": support.shape[0],
                "features": support.shape[1], "input_bits_row_major": "".join("1" if bit else "0" for bit in support.reshape(-1)),
                "selected_modes": list(record.selected_modes), "event_count": record.event_count,
                "payload_bits": record.payload_bits, "payload_bytes": record.payload_bytes,
                "unpadded_bytes": record.unpadded_bytes, "padded_bytes": record.padded_bytes,
                "padding_bytes": record.padded_bytes - record.unpadded_bytes,
                "stream_sha256": record.sha256, "decoded_output_sha256": _hash_support(decoded.support),
            }
            stem.with_suffix(".json").write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n")
            emitted += 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trace", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-name", default="synthetic")
    parser.add_argument("--tile-rows", type=int, default=128)
    parser.add_argument("--slice-width", type=int, default=128)
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--golden", action="store_true")
    args = parser.parse_args()
    if args.golden:
        generate_golden(args.output)
    elif args.trace is not None:
        validate_trace(args.trace, args.output, source_name=args.source_name, tile_rows=args.tile_rows, slice_width=args.slice_width, max_records=args.max_records)
    else:
        parser.error("--trace or --golden is required")


if __name__ == "__main__":
    main()
