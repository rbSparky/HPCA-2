"""Predeclared MOSAIC-Delta Phase-1 gates and project decision."""

import math

import numpy as np
import pandas as pd


def _geomean(values) -> float:
    values = np.asarray(list(values), dtype=float)
    return float(np.exp(np.log(values).mean()))


def evaluate_phase1_gates(
    summary: pd.DataFrame,
    controls: pd.DataFrame,
    exactness_pass: bool,
    runtime_pass: bool,
) -> tuple[str, list[dict[str, object]]]:
    indexed = summary.set_index("config_id")
    principals = [indexed.loc[key] for key in ("cora_gcnii16", "pubmed_gcnii16")]
    temporal_pass_each = [
        row.metadata_ratio <= 0.45
        and row.greedy_segment_length >= 3
        and row.greedy_to_dp <= 1.08
        for row in principals
    ]
    temporal_amber_each = [
        row.metadata_ratio <= 0.60
        and row.greedy_segment_length >= 2
        and row.greedy_to_dp <= 1.15
        for row in principals
    ]
    temporal_status = (
        "PASS" if all(temporal_pass_each) else
        "AMBER" if all(temporal_amber_each) else "FAIL"
    )
    speedups = [row.median_proxy_speedup_rho1_25 for row in principals]
    relative = [row.relative_proxy_improvement for row in principals]
    byte_gm = _geomean(row.median_byte_ratio for row in principals)
    economic_pass = (
        min(speedups) >= 1.18 and _geomean(speedups) >= 1.27
        and min(relative) >= 0.05 and byte_gm <= 0.95
        and min(row.median_rho_delta_max_1_15 for row in principals) >= 1.50
    )
    economic_amber = (
        min(speedups) >= 1.12 and _geomean(speedups) >= 1.20
        and min(relative) >= 0.02 and byte_gm <= 1.00
        and min(row.median_rho_delta_max_1_15 for row in principals) >= 1.25
    )
    economic_status = "PASS" if economic_pass else "AMBER" if economic_amber else "FAIL"

    deep = summary[
        summary.config_id.isin(("cora_deepres28_w128", "pubmed_deepres28_w128"))
        & summary.model_valid
    ]
    sparse_pass = any(
        0.25 <= row.median_density <= 0.65
        and row.median_proxy_speedup_rho1_25 >= 1.45
        and row.median_proxy_speedup_rho1_50 >= 1.30
        and row.median_byte_ratio <= 0.92
        and row.greedy_to_dp <= 1.12
        for _, row in deep.iterrows()
    )
    valid = summary[summary.model_valid]
    locality_pass = (
        int((valid.grouping_gain_over_random >= 0.08).sum()) >= 3
        and int((valid.oracle_gap_recovery >= 0.60).sum()) >= 3
        and float(valid.median_padding.median()) <= 0.12
    )
    locality_amber = (
        int((valid.grouping_gain_over_random >= 0.05).sum()) >= 2
        and int((valid.oracle_gap_recovery >= 0.40).sum()) >= 2
        and float(valid.median_padding.median()) <= 0.18
    )
    locality_status = "PASS" if locality_pass else "AMBER" if locality_amber else "FAIL"

    null_primary = []
    additional = []
    for config_id in ("cora_gcnii16", "pubmed_gcnii16"):
        frame = controls[controls.config_id == config_id].set_index("control_type")
        real = frame.loc["real"]
        independent = frame.loc["density_matched_independent"]
        structural = (
            real.metadata_reduction >= 1.5 * independent.metadata_reduction
            or real.proxy_speedup_rho1_25 >= 1.10 * independent.proxy_speedup_rho1_25
        )
        null_primary.append(structural)
        temporal = frame.loc["temporal_order"]
        node = frame.loc["node_permutation"]
        random_init = frame.loc["random_init"]
        additional.extend([
            real.metadata_reduction - temporal.metadata_reduction
            >= 0.25 * max(real.metadata_reduction, 1e-12),
            real.window_cluster_gain_over_random - node.window_cluster_gain_over_random
            >= 0.25 * max(real.window_cluster_gain_over_random, 1e-12),
            real.proxy_speedup_rho1_25 / max(real.density, 1e-12)
            > random_init.proxy_speedup_rho1_25 / max(random_init.density, 1e-12),
        ])
    null_pass = all(null_primary) and sum(additional) >= 2

    robustness_pass = (
        _geomean(row.median_proxy_speedup_rho1_50 for row in principals) >= 1.18
        and all(row.fallback_overhead_fraction <= 0.05 for row in principals)
    )
    rows = [
        ("exactness", exactness_pass, "all real/synthetic masks exact"),
        ("temporal_compression", temporal_status, "principal metadata/segments/DP"),
        ("economic", economic_status, "fixed principal setting"),
        ("sparse_target_architecture", sparse_pass, "valid deepres_v2 target"),
        ("cohort_locality", locality_status, "random gain/oracle recovery/padding"),
        ("null_controls", null_pass, "density and temporal/node nulls"),
        ("robustness", robustness_pass, "rho=1.50 and fallback overhead"),
        ("runtime_reproducibility", runtime_pass, "<=90m, tests, hashes, GPU record"),
    ]
    gate_rows = [
        {
            "gate_id": gate,
            "status": (
                value if isinstance(value, str) else ("PASS" if value else "FAIL")
            ),
            "evidence": evidence,
        }
        for gate, value, evidence in rows
    ]
    statuses = {row["gate_id"]: row["status"] for row in gate_rows}
    if statuses["exactness"] != "PASS" or statuses["runtime_reproducibility"] != "PASS":
        decision = "ENVIRONMENT_OR_IMPLEMENTATION_FAILURE"
    elif (
        statuses["temporal_compression"] == "PASS"
        and statuses["economic"] == "PASS"
        and statuses["sparse_target_architecture"] == "PASS"
        and statuses["cohort_locality"] in ("PASS", "AMBER")
        and statuses["null_controls"] == "PASS"
        and statuses["robustness"] == "PASS"
    ):
        decision = "GO_TO_SCALESIM_DELTA_IMPLEMENTATION"
    else:
        some_margin = any(
            row.median_rho_delta_max_1_15 >= 1.25 for _, row in valid.iterrows()
        )
        structural = any(null_primary)
        if (
            statuses["temporal_compression"] in ("PASS", "AMBER")
            and statuses["economic"] in ("PASS", "AMBER")
            and some_margin
            and structural
        ):
            decision = "ITERATE_DELTA_ENCODING"
        elif (
            statuses["temporal_compression"] == "PASS"
            and statuses["cohort_locality"] == "FAIL"
            and max(row.median_rho_delta_max_1_15 for _, row in valid.iterrows()) >= 1.25
        ):
            decision = "PIVOT_TO_TEMPORAL_ONLY"
        else:
            weak = (
                all(
                    controls[
                        (controls.config_id == config_id)
                        & (controls.control_type == "real")
                    ].metadata_reduction.iloc[0] < 0.10
                    for config_id in ("cora_gcnii16", "pubmed_gcnii16")
                )
                and all(row.median_proxy_speedup_rho1_10 < 1.15 for row in principals)
                and all(row.global_oracle_proxy < 1.15 for row in principals)
                and all(row.delta_selection_fraction < 0.5 for _, row in valid.iterrows())
            )
            decision = "STOP_MOSAIC_DIRECTION" if weak else "ITERATE_DELTA_ENCODING"
    gate_rows.append(
        {"gate_id": "phase1_decision", "status": decision, "evidence": "predeclared logic"}
    )
    return decision, gate_rows

