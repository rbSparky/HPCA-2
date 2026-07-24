"""Predeclared Phase-2 gate evaluation."""

import numpy as np
import pandas as pd


def gm(values):
    values = np.asarray(list(values), float)
    return float(np.exp(np.log(values).mean()))


def evaluate(summary, nulls, calibration, exact, runtime_ok):
    idx = summary.set_index("config_id")
    principal = [idx.loc["cora_gcnii16"], idx.loc["pubmed_gcnii16"]]
    g1 = exact
    reductions = [r.chain_gap_relative_metadata_reduction for r in principal]
    g2_pass = min(reductions) >= .25 and gm(reductions) >= .30 and all(
        r.entropy_overhead_median <= 1.75 and r.entropy_overhead_p90 <= 2.5 for r in principal)
    g2_amber = min(reductions) >= .15 and gm(reductions) >= .20
    g2 = "PASS" if g2_pass else "AMBER" if g2_amber else "FAIL"
    g3 = all(r.chain_replay_amplification <= 1.25 or r.chain_state_bytes <= 2**20 for r in principal)
    # Extrapolated 250k x 256 state is 8 MiB and therefore makes this false.
    g3 = g3 and (250_000 * 256 / 8 <= 2**20)
    speeds = [r.anchor_proxy_speedup_rho1_25 for r in principal]
    speed50 = [r.anchor_proxy_speedup_rho1_50 for r in principal]
    bytes_ = [r.anchor_byte_ratio for r in principal]
    improvements = [max(r.anchor_proxy_speedup_rho1_25 / r.phase0_proxy - 1,
                        1 - r.anchor_byte_ratio_to_phase0) for r in principal]
    g4_pass = min(speeds) >= 1.15 and gm(speeds) >= 1.25 and min(speed50) >= 1.12 and gm(bytes_) <= .94 and min(improvements) >= .03
    g4_amber = min(speeds) >= 1.10 and gm(speeds) >= 1.18 and gm(bytes_) <= .98 and min(improvements) >= -.02
    g4 = "PASS" if g4_pass else "AMBER" if g4_amber else "FAIL"
    deep = idx.loc["cora_deepres28_w128"]
    g5 = (.25 <= deep.median_density <= .65 and deep.anchor_proxy_speedup_rho1_25 >= 1.45
          and deep.anchor_proxy_speedup_rho1_50 >= 1.30 and deep.anchor_byte_ratio <= .94
          and bool(deep.anchor_independent_decode))
    valid = summary[summary.model_valid]
    counts = [
        int((valid.anchor_capture >= .60).sum()),
        int((valid.anchor_padding <= .12).sum()),
        int((valid.anchor_segment_length >= 3).sum()),
    ]
    g6_pass = min(counts) >= 3 and valid.anchor_greedy_to_dp.median() <= 1.08 and int((valid.oracle_gap_recovery >= .5).sum()) >= 2
    g6_amber = min(counts) >= 2 and valid.anchor_greedy_to_dp.median() <= 1.15
    g6 = "PASS" if g6_pass else "AMBER" if g6_amber else "FAIL"
    g7_checks = []
    for cid in ("cora_gcnii16", "pubmed_gcnii16"):
        f = nulls[nulls.config_id == cid].set_index("control_type")
        real, ind, node, temp, rnd = (f.loc[x] for x in ("real","density_matched_independent","node_permutation","temporal_order","random_init"))
        checks = [
            (1-real.metadata_ratio) >= 1.5*(1-ind.metadata_ratio),
            real.analytical_proxy_speedup_rho1_25 >= 1.08*ind.analytical_proxy_speedup_rho1_25,
            real.anchor_nnz_capture-real.padding_fraction >= 1.2*(node.anchor_nnz_capture-node.padding_fraction),
            temp.metadata_ratio >= 1.15*real.metadata_ratio,
            real.analytical_proxy_speedup_rho1_25/real.density >= 1.1*rnd.analytical_proxy_speedup_rho1_25/rnd.density,
        ]
        g7_checks.append(sum(checks) >= 2 and any(checks[:2]))
    g7 = all(g7_checks)
    cal = summary.set_index("config_id")
    hybrid_principal = [cal.loc[x].anchor_hybrid_combination_speedup for x in ("cora_gcnii16","pubmed_gcnii16")]
    call_ok = bool(calibration.scalesim_run_success.all()) and len(calibration) > 0
    g8_pass = call_ok and gm(hybrid_principal) >= 1.15 and deep.anchor_hybrid_combination_speedup >= 1.25
    g8_amber = call_ok and 1.05 <= gm(hybrid_principal) < 1.15
    g8 = "PASS" if g8_pass else "AMBER" if g8_amber else "FAIL"
    g9 = runtime_ok and min(r.anchor_proxy_speedup_rho1_75 for r in principal) >= 1.08
    rows = [("G1", "PASS" if g1 else "FAIL"),("G2",g2),("G3","PASS" if g3 else "FAIL"),
            ("G4",g4),("G5","PASS" if g5 else "FAIL"),("G6",g6),
            ("G7","PASS" if g7 else "FAIL"),("G8",g8),("G9","PASS" if g9 else "FAIL")]
    status = dict(rows)
    if status["G1"]!="PASS" or status["G9"]!="PASS":
        decision="ENVIRONMENT_OR_IMPLEMENTATION_FAILURE"
    elif status["G4"]=="PASS" and status["G5"]=="PASS" and status["G6"] in ("PASS","AMBER") and status["G7"]=="PASS" and status["G8"] in ("PASS","AMBER"):
        decision="GO_TO_PHASE3_ANCHOR_ACCELERATOR"
    elif status["G4"]=="AMBER" and deep.anchor_proxy_speedup_rho1_25 >= 1.30 and status["G7"]=="PASS":
        decision="ITERATE_ANCHOR_ENCODING"
    elif status["G3"]=="FAIL" and all(
        max(
            r.anchor_proxy_speedup_rho1_25 / r.phase0_proxy - 1,
            1 - r.anchor_byte_ratio_to_phase0,
        ) < .03
        for r in principal
    ):
        decision="PIVOT_TO_SPATIAL_ONLY_MOSAIC"
    else:
        decision="ITERATE_ANCHOR_ENCODING"
    out=[{"gate_id":g,"status":s} for g,s in rows]
    out.append({"gate_id":"PHASE2_DECISION","status":decision})
    return decision,out
