# HPCA XORFLOW Evidence Index

**Suite progress:** `[################----] 84%` (fixed manifest weights)
**Hard deadline:** `2026-07-31T23:59:00Z` — **hours remaining:** `75.83`
**Policy:** `BORDERLINE` results are supplementary only; they never satisfy hard gates.
**Reviewer-facing completed-results report:** [HPCA_PAPER_READY_RESULTS.md](HPCA_PAPER_READY_RESULTS.md)

| Stage | Status | Weight |
|---|---:|---:|
| smoke | COMPLETE | 8% |
| quality | COMPLETE | 8% |
| primary | COMPLETE | 18% |
| controls | COMPLETE | 10% |
| tools | COMPLETE | 8% |
| temporal | COMPLETE | 14% |
| sensitivity | COMPLETE | 16% |
| memory_timing | PENDING | 6% |
| cuda | PENDING | 4% |
| rtl | PENDING | 4% |
| expanded_models | PENDING | 2% |
| reproduce | COMPLETE | 2% |
| report | COMPLETE | 0% |

## Indexed artifacts

| Stage | Item | Status | Validity | Metric | Artifact | Log | Reason |
|---|---|---|---|---|---|---|---|
| quality | ogbn_arxiv_deepres8_w128_s17 | SUCCEEDED | HARD_VALID | accuracy 0.682777 | `artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres8_w128_s17/record.json` | `` | meets predeclared floor |
| quality | ogbn_arxiv_deepres8_w128_s27 | SUCCEEDED | HARD_VALID | accuracy 0.686583 | `artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres8_w128_s27/record.json` | `` | meets predeclared floor |
| quality | reddit_deepres8_w128_s7_native | SUCCEEDED | HARD_VALID | accuracy 0.953360 | `artifacts_hpca_xorflow/workloads/reddit_deepres8_w128_s7_native/record.json` | `` | meets predeclared floor |
| quality | yelp_deepres8_w128_s7_balanced_fallback | SUCCEEDED | BORDERLINE | micro_f1 0.433952 | `artifacts_hpca_xorflow/workloads/yelp_deepres8_w128_s7_balanced_fallback/record.json` | `` | within 0.020 of floor; report-only |
| quality | flickr_deepres8_w128_s7 | SUCCEEDED | HARD_VALID | accuracy 0.472281 | `artifacts_hpca_xorflow/workloads/flickr_deepres8_w128_s7/record.json` | `` | meets predeclared floor |
| smoke | environment_and_regression | SUCCEEDED | N/A |   | `artifacts_hpca_xorflow/overnight_smoke.json` | `artifacts_hpca_xorflow/logs/overnight_pytest.log` | all admission checks passed |
| quality | ogbn_arxiv_deepres8_w128_s17 | SUCCEEDED | HARD_VALID | accuracy 0.682777 | `artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres8_w128_s17/record.json` | `` | meets predeclared floor |
| quality | ogbn_arxiv_deepres8_w128_s27 | SUCCEEDED | HARD_VALID | accuracy 0.686583 | `artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres8_w128_s27/record.json` | `` | meets predeclared floor |
| quality | reddit_deepres8_w128_s7_native | SUCCEEDED | HARD_VALID | accuracy 0.953360 | `artifacts_hpca_xorflow/workloads/reddit_deepres8_w128_s7_native/record.json` | `` | meets predeclared floor |
| quality | yelp_deepres8_w128_s7_balanced_fallback | SUCCEEDED | BORDERLINE | micro_f1 0.433952 | `artifacts_hpca_xorflow/workloads/yelp_deepres8_w128_s7_balanced_fallback/record.json` | `` | within 0.020 of floor; report-only |
| quality | flickr_deepres8_w128_s7 | SUCCEEDED | HARD_VALID | accuracy 0.472281 | `artifacts_hpca_xorflow/workloads/flickr_deepres8_w128_s7/record.json` | `` | meets predeclared floor |
| smoke | environment_and_regression | SUCCEEDED | N/A |   | `artifacts_hpca_xorflow/overnight_smoke.json` | `artifacts_hpca_xorflow/logs/overnight_pytest.log` | all admission checks passed |
| primary | ogbn_arxiv_deepres8_w128_s17 | SUCCEEDED | HARD_VALID | accuracy 0.682777 | `results_hpca_xorflow/runs/ogbn_arxiv_deepres8_w128_s17/host_model_overnight.csv` | `artifacts_hpca_xorflow/logs/overnight_ogbn_arxiv_deepres8_w128_s17.log` |  |
| primary | ogbn_arxiv_deepres8_w128_s27 | SUCCEEDED | HARD_VALID | accuracy 0.686583 | `results_hpca_xorflow/runs/ogbn_arxiv_deepres8_w128_s27/host_model_overnight.csv` | `artifacts_hpca_xorflow/logs/overnight_ogbn_arxiv_deepres8_w128_s27.log` |  |
| primary | reddit_deepres8_w128_s7_native | SUCCEEDED | HARD_VALID | accuracy 0.953360 | `results_hpca_xorflow/runs/reddit_deepres8_w128_s7_native/host_model_overnight.csv` | `artifacts_hpca_xorflow/logs/overnight_reddit_deepres8_w128_s7_native.log` |  |
| primary | yelp_deepres8_w128_s7_balanced_fallback | SUCCEEDED | BORDERLINE | micro_f1 0.433952 | `results_hpca_xorflow/runs/yelp_deepres8_w128_s7_balanced_fallback/host_model_overnight.csv` | `artifacts_hpca_xorflow/logs/overnight_yelp_deepres8_w128_s7_balanced_fallback.log` |  |
| primary | flickr_deepres8_w128_s7 | SUCCEEDED | HARD_VALID | accuracy 0.472281 | `results_hpca_xorflow/runs/flickr_deepres8_w128_s7/host_model_overnight.csv` | `artifacts_hpca_xorflow/logs/overnight_flickr_deepres8_w128_s7.log` |  |
| controls | causal_support_nulls | SUCCEEDED | HARD_VALID_ONLY |   | `results_hpca_xorflow/overnight_null_controls.csv` | `` | density, node, and temporal controls use seed 7007 |
| tools | scalesim_and_ramulator_smoke | SUPERSEDED | N/A |   | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | exit 1; corrected rerun passed |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| tools | scalesim_and_ramulator_smoke | SUPERSEDED | N/A |   | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | exit 1; corrected rerun passed |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| tools | scalesim_and_ramulator_smoke | SUPERSEDED | N/A |   | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | exit 1; corrected rerun passed |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| tools | scalesim_and_ramulator_smoke | SUCCEEDED | N/A |   | `artifacts_hpca_xorflow/ramulator/overnight_tiny.json` | `artifacts_hpca_xorflow/logs/overnight_ramulator_smoke.log` | PPA tools unavailable are recorded in smoke manifest |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| report | overnight_summary | SUCCEEDED | N/A |   | `results_hpca_xorflow/overnight_summary.csv` | `` | indexed only; no post-hoc gate relaxation |
| temporal | temporal_arxiv_s17 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/temporal_arxiv_s17/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_temporal_arxiv_s17.log` |  |
| temporal | temporal_arxiv_s27 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/temporal_arxiv_s27/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_temporal_arxiv_s27.log` |  |
| temporal | temporal_reddit | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/temporal_reddit/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_temporal_reddit.log` |  |
| temporal | temporal_flickr | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/temporal_flickr/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_temporal_flickr.log` |  |
| temporal | temporal_yelp_borderline | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/temporal_yelp_borderline/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_temporal_yelp_borderline.log` |  |
| sensitivity | sens_arxiv_cache256 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_arxiv_cache256/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_arxiv_cache256.log` |  |
| sensitivity | sens_arxiv_cache1m | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_arxiv_cache1m/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_arxiv_cache1m.log` |  |
| sensitivity | sens_arxiv_slice64 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_arxiv_slice64/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_arxiv_slice64.log` |  |
| sensitivity | sens_arxiv_slice96 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_arxiv_slice96/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_arxiv_slice96.log` |  |
| sensitivity | sens_arxiv_slice256 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_arxiv_slice256/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_arxiv_slice256.log` |  |
| sensitivity | sens_arxiv_source_tiled | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_arxiv_source_tiled/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_arxiv_source_tiled.log` |  |
| sensitivity | sens_reddit_cache256 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_reddit_cache256/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_reddit_cache256.log` |  |
| sensitivity | sens_reddit_cache1m | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_reddit_cache1m/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_reddit_cache1m.log` |  |
| sensitivity | sens_reddit_slice96 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_reddit_slice96/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_reddit_slice96.log` |  |
| sensitivity | sens_reddit_source_tiled | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/sens_reddit_source_tiled/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_sens_reddit_source_tiled.log` |  |
| reproduce | reproducibility_arxiv_s17 | SUCCEEDED |  |   | `results_hpca_xorflow/paper_runs/reproducibility_arxiv_s17/host_model.csv` | `artifacts_hpca_xorflow/logs/paper_reproducibility_arxiv_s17.log` |  |
| report | paper_queue_manifest | SUCCEEDED |  |   | `results_hpca_xorflow/paper_queue_manifest.json` | `` | queue snapshot written; pending implementation tasks remain visible |
| report | paper_queue_manifest | SUCCEEDED |  |   | `results_hpca_xorflow/paper_queue_manifest.json` | `` | queue snapshot written; pending implementation tasks remain visible |

## Complete execution queue

The queue is fixed by the manifest; completed work remains listed and unsubmitted work is never silently omitted.

| Queue item | Stage | Dependency | Estimate (min) | Status | Job ID | Log |
|---|---|---|---:|---|---|---|
| admission_complete | smoke | none | 0 | COMPLETE | 20260728T191227Z_4440 | `/home/Rishabh@MLL-5090/remote-work/HPCA-2-xorflow/.xorflow_jobs/20260728T191227Z_4440/stdout_stderr.log` |
| quality_complete | quality | admission_complete | 0 | COMPLETE | - | `-` |
| primary_complete | primary | quality_complete | 0 | COMPLETE | - | `-` |
| controls_complete | controls | primary_complete | 0 | COMPLETE | - | `-` |
| timing_smoke_complete | tools | controls_complete | 0 | COMPLETE | 20260728T193500Z_3010 | `/home/Rishabh@MLL-5090/remote-work/HPCA-2-xorflow/.xorflow_jobs/20260728T193500Z_3010/stdout_stderr.log` |
| temporal_arxiv_s17 | temporal | primary_complete | 18 | COMPLETE | - | `-` |
| temporal_arxiv_s27 | temporal | temporal_arxiv_s17 | 18 | COMPLETE | - | `-` |
| temporal_reddit | temporal | temporal_arxiv_s27 | 50 | COMPLETE | - | `-` |
| temporal_flickr | temporal | temporal_reddit | 20 | COMPLETE | - | `-` |
| temporal_yelp_borderline | temporal | temporal_flickr | 35 | COMPLETE | - | `-` |
| sens_arxiv_cache256 | sensitivity | temporal_yelp_borderline | 18 | COMPLETE | - | `-` |
| sens_arxiv_cache1m | sensitivity | sens_arxiv_cache256 | 18 | COMPLETE | - | `-` |
| sens_arxiv_slice64 | sensitivity | sens_arxiv_cache1m | 18 | COMPLETE | - | `-` |
| sens_arxiv_slice96 | sensitivity | sens_arxiv_slice64 | 18 | COMPLETE | - | `-` |
| sens_arxiv_slice256 | sensitivity | sens_arxiv_slice96 | 18 | COMPLETE | - | `-` |
| sens_arxiv_source_tiled | sensitivity | sens_arxiv_slice256 | 18 | COMPLETE | - | `-` |
| sens_reddit_cache256 | sensitivity | sens_arxiv_source_tiled | 50 | COMPLETE | - | `-` |
| sens_reddit_cache1m | sensitivity | sens_reddit_cache256 | 50 | COMPLETE | - | `-` |
| sens_reddit_slice96 | sensitivity | sens_reddit_cache1m | 50 | COMPLETE | - | `-` |
| sens_reddit_source_tiled | sensitivity | sens_reddit_slice96 | 50 | COMPLETE | - | `-` |
| ramulator_existing_arxiv | memory_timing | temporal_arxiv_s17 | 5 | COMPLETE | - | `-` |
| cuda_microbench | cuda | temporal_reddit | 35 | QUEUED | 20260728T200135Z_3972 | `/home/Rishabh@MLL-5090/remote-work/HPCA-2-xorflow/.xorflow_jobs/20260728T200135Z_3972/stdout_stderr.log` |
| rtl_ppa | rtl | temporal_arxiv_s17 | 90 | PENDING_IMPLEMENTATION | - | `-` |
| expanded_models | expanded_models | temporal_arxiv_s27 | 960 | PENDING_IMPLEMENTATION | - | `-` |
| reproducibility_arxiv_s17 | reproduce | sens_reddit_source_tiled | 18 | RUNNING | 20260728T195241Z_30027 | `/home/Rishabh@MLL-5090/remote-work/HPCA-2-xorflow/.xorflow_jobs/20260728T195241Z_30027/stdout_stderr.log` |

**Estimated remaining queue time:** `53.0 minutes` (serialized GPU-1 estimate; completed runtimes are not counted).
