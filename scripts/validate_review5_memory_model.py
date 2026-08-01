#!/usr/bin/env python3
"""Cross-workload absolute validation of the final HBM timing scale."""
from __future__ import annotations

import csv, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R4 = ROOT / "results_hpca_xorflow/final_review4/full_network_external"
OUT = ROOT / "results_hpca_xorflow/final_review5_unified/memory_validation"


def internal(case: str) -> int:
    path = OUT / f"{case}_direct_internal.txt"
    return int(next(x.split(",")[1] for x in path.read_text().splitlines() if x.startswith("MAX,")))


def external(case: str) -> int:
    data = json.loads((R4 / case / "ramulator2.json").read_text())
    return max(int(x["cycles"]) for x in data["memory_system"]["controller"])


def main() -> None:
    train_i, train_e = internal("flickr_s7"), external("flickr_s7")
    scale = train_e / train_i
    rows = []
    for role, case in (("CALIBRATION", "flickr_s7"), ("HELD_OUT_VALIDATION", "flickr_s17")):
        i, e = internal(case), external(case)
        predicted = round(i * scale)
        rows.append({
            "case": case, "role": role, "raw_internal_cycles": i,
            "prediction_cycles": predicted, "ramulator2_cycles": e,
            "absolute_error_percent": 100 * abs(predicted - e) / e,
            "calibration_source": "flickr_s7_only",
            "same_case_external_used_for_prediction": role == "CALIBRATION",
        })
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "heldout_absolute_validation.csv").open("w", newline="") as h:
        w = csv.DictWriter(h, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    payload = {
        "version": "hbm2_flickr_s7_calibration_v1",
        "timing_scale": scale,
        "training_case": "flickr_s7_all_layers",
        "held_out_case": "flickr_s17_all_layers",
        "held_out_absolute_error_percent": rows[1]["absolute_error_percent"],
        "held_out_pass_le_5_percent": rows[1]["absolute_error_percent"] <= 5.0,
        "same_case_calibration_for_held_out_prediction": False,
    }
    (OUT / "memory_timing_model.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__": main()
