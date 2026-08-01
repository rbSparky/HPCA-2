"""Predeclared per-configuration and project gates."""

import numpy as np
import pandas as pd


def _status(condition: bool, amber: bool) -> str:
    return "PASS" if condition else ("AMBER" if amber else "FAIL")


def summarize_config(config_id: str, valid: bool, signal: pd.DataFrame, cohort: pd.DataFrame, temporal: pd.DataFrame):
    trained = signal[
        (signal.config_id == config_id) & (signal.trace_state == "trained") & (signal.layer >= 4)
    ]
    methods = cohort[
        (cohort.config_id == config_id) & (cohort.trace_state == "trained") & (cohort.layer >= 4)
    ]
    rcm = methods[methods.grouping_method == "rcm_cost_cluster"]
    random = methods[methods.grouping_method == "random_balanced"]
    oracle = methods[methods.grouping_method == "global_lsh_oracle"]
    transitions = temporal[(temporal.config_id == config_id) & (temporal.to_layer >= 4)]
    med = lambda frame, col: float(frame[col].median()) if len(frame) else float("nan")
    edge = med(trained, "edge_to_random_ratio")
    local = med(trained, "local_to_random_ratio")
    layer_count = int((trained.local_to_random_ratio <= 0.95).sum())
    ci_effect = min(
        med(trained, "edge_ci_high") / max(med(trained, "random_ci_low"), 1e-12),
        med(trained, "local_ci_high") / max(med(trained, "random_ci_low"), 1e-12),
    )
    spatial_pass = edge <= 0.90 and local <= 0.90 and layer_count >= 8 and ci_effect < 0.98
    spatial_amber = edge <= 0.90 or local <= 0.90 or (edge <= 0.97 and local <= 0.97)
    spatial = _status(spatial_pass, spatial_amber)

    temp_flip = med(transitions, "activation_flip")
    temp_ratio = med(transitions, "activation_flip_ratio")
    stability = med(transitions, "assignment_stability")
    reuse = med(transitions, "reuse_penalty")
    temporal_pass = temp_flip <= 0.22 and temp_ratio <= 0.80 and stability >= 0.60 and reuse <= 0.10
    temporal_amber = temp_flip <= 0.30 and temp_ratio <= 0.90 and stability >= 0.45 and reuse <= 0.18
    temporal_gate = _status(temporal_pass, temporal_amber)

    capture = med(rcm, "regular_capture")
    padding = float(rcm.padding_fraction.quantile(0.75)) if len(rcm) else float("nan")
    residual = med(rcm, "residual_fraction")
    rho2 = med(rcm, "proxy_speedup_rho2")
    rho3 = med(rcm, "proxy_speedup_rho3")
    byte_ratio = med(rcm, "mosaic_to_best_byte_ratio")
    break_even = med(rcm, "break_even_rho")
    cohort_pass = (
        capture >= 0.70 and padding <= 0.30 and residual <= 0.30 and rho2 >= 1.15
        and rho3 >= 1.30 and byte_ratio <= 1.05 and break_even <= 2.25
    )
    byte_tradeoff = byte_ratio <= 1.15 and capture >= 0.80 and rho2 >= 1.30
    cohort_amber = capture >= 0.60 and rho2 >= 1.08 and byte_ratio <= 1.20
    cohort_gate = (
        "PASS" if cohort_pass else
        "PASS_WITH_BYTE_TRADEOFF" if byte_tradeoff else
        "AMBER" if cohort_amber else "FAIL"
    )

    random_rho2 = med(random, "proxy_speedup_rho2")
    oracle_rho2 = med(oracle, "proxy_speedup_rho2")
    gain = rho2 / random_rho2 - 1 if random_rho2 else float("nan")
    gap = (
        (rho2 - random_rho2) / (oracle_rho2 - random_rho2)
        if oracle_rho2 > random_rho2 else float("nan")
    )
    control_pass = gain >= 0.08 and gap >= 0.50 and oracle_rho2 >= 1.20
    control_amber = gain >= 0.03 and oracle_rho2 >= 1.10
    control = _status(control_pass, control_amber)
    passes = sum(value.startswith("PASS") for value in (spatial, temporal_gate, control))
    if not valid:
        decision = "INVALID_MODEL"
    elif cohort_gate.startswith("PASS") and passes >= 2:
        decision = "STRONG_PASS"
    elif (cohort_gate.startswith("PASS") or control == "PASS") and (
        spatial in ("PASS", "AMBER") or temporal_gate in ("PASS", "AMBER")
    ):
        decision = "PARTIAL_PASS"
    else:
        decision = "FAIL_SIGNAL"
    return {
        "config_id": config_id,
        "model_valid": bool(valid),
        "median_density": med(trained, "density"),
        "median_edge_to_random": edge,
        "median_local_to_random": local,
        "median_temporal_flip": temp_flip,
        "median_temporal_flip_ratio": temp_ratio,
        "median_assignment_stability": stability,
        "median_template_jaccard": med(transitions, "matched_template_jaccard"),
        "median_reuse_penalty": reuse,
        "median_regular_capture": capture,
        "p75_padding_fraction": padding,
        "median_residual_fraction": residual,
        "median_mosaic_to_best_byte_ratio": byte_ratio,
        "median_proxy_speedup_rho2": rho2,
        "median_proxy_speedup_rho3": rho3,
        "random_group_proxy_speedup_rho2": random_rho2,
        "global_lsh_proxy_speedup_rho2": oracle_rho2,
        "rcm_over_random_cost_gain": gain,
        "rcm_fraction_of_oracle_gap": gap,
        "spatial_gate": spatial,
        "temporal_gate": temporal_gate,
        "cohort_gate": cohort_gate,
        "control_gate": control,
        "config_decision": decision,
    }


def project_decision(summary: pd.DataFrame, cohort: pd.DataFrame | None = None) -> str:
    rows = summary.set_index("config_id")
    required = ["cora_gcnii16", "pubmed_gcnii16", "cora_resgcn16"]
    if not all(key in rows.index for key in required):
        return "ITERATE_METHOD_BEFORE_SIMULATOR"
    cora, pubmed, resgcn = (rows.loc[key] for key in required)
    main = [cora, pubmed]
    go = (
        bool(cora.model_valid) and bool(pubmed.model_valid)
        and sorted([cora.config_decision, pubmed.config_decision]).count("STRONG_PASS") >= 1
        and all(item.config_decision in ("STRONG_PASS", "PARTIAL_PASS") for item in main)
        and resgcn.config_decision in ("STRONG_PASS", "PARTIAL_PASS")
        and sum(item.cohort_gate.startswith("PASS") for item in (cora, pubmed, resgcn)) >= 2
        and np.median([item.median_proxy_speedup_rho2 for item in main]) >= 1.20
        and np.median([item.median_regular_capture for item in main]) >= 0.70
        and np.median([item.median_reuse_penalty for item in main]) <= 0.10
        and sum(item.rcm_over_random_cost_gain >= 0.08 for _, item in rows.iterrows() if item.model_valid) >= 2
    )
    if go:
        return "GO_TO_SCALESIM_METHOD_IMPLEMENTATION"
    iterate = any(
        item.cohort_gate.startswith("PASS") or item.control_gate == "PASS" for item in main
    ) and any(
        item.spatial_gate in ("PASS", "AMBER") or item.temporal_gate in ("PASS", "AMBER")
        for item in main
    )
    pivot = (
        all(item.global_lsh_proxy_speedup_rho2 < 1.10 for item in main)
        or (
            cohort is not None
            and all(
                cohort[
                    (cohort.config_id == config_id)
                    & (cohort.trace_state == "trained")
                    & (cohort.layer >= 4)
                    & (cohort.grouping_method == "global_lsh_oracle")
                ].regular_capture.median() < 0.55
                for config_id in ("cora_gcnii16", "pubmed_gcnii16")
            )
        )
        or all(
            item.spatial_gate == "FAIL" and item.temporal_gate == "FAIL"
            and item.median_reuse_penalty > 0.25
            for item in main if item.model_valid
        )
    )
    if pivot and not iterate:
        return "PIVOT_OR_KILL_TEMPLATE_DIRECTION"
    return "ITERATE_METHOD_BEFORE_SIMULATOR"
