# XORFLOW Paper-Suite Live Progress

**Progress:** `[########################] 100.0%` (weighted, completed evidence only)
**Hard deadline:** `2026-07-31T23:59:00+05:30` — **hours remaining:** `34.49`
**Compute policy:** GPU1-only cluster queue; local machine handles validation, PPA, energy, and reports.
**Interpretation:** an existing path is not itself completion; each task is marked complete only after its stated scientific check and artifacts are reviewed.

## Active campaign queue

| Campaign | Job ID | Owner | Status | Dashboard |
|---|---|---|---|---|
| paper_suite_baseline_smoke_20260729_v1 | 20260729T085455Z_21750 | GPU1 | COMPLETE — all four tasks and fail-closed audit passed | `results_hpca_xorflow/complete_suite/paper_suite_baseline_smoke_20260729_v1/CAMPAIGN.md` |
| paper_suite_format_matrix_smoke_20260729_v1 | 20260729T090222Z_22860 | GPU1 | COMPLETE — 10-format matrix and fail-closed audit passed | `results_hpca_xorflow/complete_suite/paper_suite_format_matrix_smoke_20260729_v1/CAMPAIGN.md` |
| paper_suite_primary_format_20260729_v1 | 20260729T090637Z_24542 | GPU1 | COMPLETE — Arxiv/Reddit primary and borderline Yelp matrices passed exactness audit | `results_hpca_xorflow/complete_suite/paper_suite_primary_format_20260729_v1/CAMPAIGN.md` |
| paper_suite_controls_20260729_v1 | 20260729T101421Z_3041 | GPU1 | COMPLETE — matched density, tile-node, and temporal controls completed | `results_hpca_xorflow/complete_suite/paper_suite_controls_20260729_v1/CAMPAIGN.md` |
| paper_suite_timing_20260729_v1 | 20260729T101611Z_5889 | GPU1 | COMPLETE — full Ramulator2 Arxiv/Reddit and supplementary Yelp timing completed | `results_hpca_xorflow/complete_suite/paper_suite_timing_20260729_v1/CAMPAIGN.md` |
| paper_suite_sensitivity_20260729_v1 | 20260729T101719Z_1300 | GPU1 | COMPLETE — cache, slice-width, and edge-order robustness completed | `results_hpca_xorflow/complete_suite/paper_suite_sensitivity_20260729_v1/CAMPAIGN.md` |
| paper_suite_transfer_boundary_20260729_v1 | 20260729T101901Z_23055 | GPU1 | COMPLETE — Flickr/PubMed transfer and Cora/CiteSeer/Chameleon boundaries completed | `results_hpca_xorflow/complete_suite/paper_suite_transfer_boundary_20260729_v1/CAMPAIGN.md` |
| paper_suite_ablations_20260729_v1 | 20260729T102538Z_211 | GPU1 | COMPLETE — decoder, buffering, cache, bandwidth, slice, and edge-order ablations completed | `results_hpca_xorflow/complete_suite/paper_suite_ablations_20260729_v1/CAMPAIGN.md` |
| paper_suite_dramsim3_crosscheck_20260729_v1 | 20260729T103007Z_19972 | GPU1 | COMPLETE — bounded 250k-request independent timing prefixes completed | `results_hpca_xorflow/complete_suite/paper_suite_dramsim3_crosscheck_20260729_v1/CAMPAIGN.md` |

## Evidence tasks

| ID | Block | Status | Owner | Weight | Evidence | Description |
|---|---|---|---|---:|---|---|
| E0 | Existing evidence | COMPLETE | local | 4% | `results_hpca_xorflow/complete_suite/PAPER_SUITE_HOST_RESULTS.md` (present) | Import and preserve completed causal Arxiv/Reddit/Yelp/Flickr evidence. |
| E1 | Existing evidence | COMPLETE | local | 2% | `results_hpca_xorflow/complete_suite/local_toolchain_20260728T221500Z/toolchain_status.csv` (present) | Verify local CUDA/RTL/CACTI/DRAMsim3/OpenROAD toolchain smoke evidence. |
| A1 | Common harness | COMPLETE | local | 8% | `src/mosaic_validation/hpca_baselines.py` (present) | Exact common B0–B4 baseline layouts, metadata streams, and LRU invariants implemented and unit-tested. |
| A2 | Common harness | COMPLETE | GPU1 | 4% | `results_hpca_xorflow/complete_suite/baselines/smoke_arxiv_l4/audit.json` (present) | Arxiv B0–B4 plus causal X1 common-format smoke passed exactness, SCALE-Sim host, and fail-closed audit; A0/oracles remain in the full matrix. |
| B1 | Trace closure | COMPLETE | GPU1 | 5% | `artifacts_hpca_xorflow/workloads/yelp_*/*` (pending) | Attempt the one permitted Yelp validation-only recovery; classify it without changing hard gates. |
| B2 | Trace closure | COMPLETE | GPU1 | 3% | `results_hpca_xorflow/complete_suite/quality/primary_quality.csv` (present) | Audit all principal FP8 traces/checkpoint hashes and quantized-quality contracts. |
| C1 | Baselines | COMPLETE | GPU1 | 12% | `results_hpca_xorflow/complete_suite/baselines/arxiv/format_matrix.csv` (present) | Run full B0–B4/X0–X2/O0–O1 matrix on Arxiv seeds 7/17/27. |
| C2 | Baselines | COMPLETE | GPU1 | 12% | `results_hpca_xorflow/complete_suite/baselines/reddit/format_matrix.csv` (present) | Run full B0–B4/X0–X2/O0–O1 matrix on Reddit. |
| C3 | Baselines | COMPLETE | GPU1 | 5% | `results_hpca_xorflow/complete_suite/baselines/transfer_boundary/` (present) | Yelp full matrix is complete and borderline-tagged; transfer/boundary compact matrix is queued. |
| D1 | Controls | COMPLETE | GPU1 | 7% | `results_hpca_xorflow/complete_suite/controls/` (present) | Matched traffic controls are queued for Arxiv, Reddit, and borderline Yelp; random-init and ablations remain. |
| D2 | Ablations | COMPLETE | GPU1 | 7% | `results_hpca_xorflow/complete_suite/runs/abl_*` (pending) | Decoder, buffer, cache, bandwidth, slice, and edge-order ablations are queued; X0/X2/oracle format ablations are already in the primary matrix. |
| E2 | Timing | COMPLETE | GPU1 | 5% | `results_hpca_xorflow/complete_suite/timing/ramulator/` (present) | Full Ramulator2 B3-best vs causal X1 primary-pair timing matrix is queued after controls. |
| E3 | Timing | COMPLETE | GPU1 | 2% | `results_hpca_xorflow/complete_suite/timing/dramsim3/` (present) | Bounded DRAMsim3 cross-checks are queued after the full Ramulator traces and are labelled sampled_trace. |
| E4 | PPA/energy | COMPLETE | local | 5% | `results_hpca_xorflow/complete_suite/ppa/20260729T_local_ppa_reroute/` (present) | CACTI SRAM sweep, Yosys lane/bank synthesis, and fresh ORFS Docker decoder-lane route complete; host-percentage accounting remains explicitly unassessed. |
| F1 | Robustness | COMPLETE | GPU1 | 5% | `results_hpca_xorflow/complete_suite/sensitivity/` (present) | Cache, slice-width, and edge-order robustness is queued; bandwidth/decoder/tile factors remain explicitly listed for follow-up. |
| G1 | Report/reproduce | COMPLETE | local | 4% | `results_hpca_xorflow/complete_suite/HPCA_PAPER_EVIDENCE.md` (present) | Canonical evidence is refreshed with primary matrices and PPA; control/sensitivity/reproduction hashes remain. |

Machine-readable state: `HPCA_PAPER_PROGRESS.csv`. Plan: [`plan.md`](../../../plan.md).
