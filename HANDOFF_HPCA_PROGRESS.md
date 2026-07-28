# XORFLOW HPCA progress handoff — 2026-07-28

## Status

This is an **in-progress** HPCA-oriented memory-subsystem evaluation, not a
completed paper-ready suite.  Preserve all prior Phase-0 through Phase-3B
artifacts.  The regular systolic path was stopped in Phase-3A; the surviving
direction is causal XORFLOW support coding for memory-bound aggregation.

## Current validated result

The new large-graph Reddit workload is valid and is the most important update
in this handoff:

| item | result |
|---|---:|
| model | DeepResV2-8, width 128, seed 7 |
| training/inference graph operator | exact normalized full-neighbour CSR |
| FP32 test accuracy | 95.3557% |
| FP8 activations + FP16 weights test accuracy | 95.3360% |
| quantization delta | 0.0197 percentage points |
| epochs / train time | 160 / 3027.3 s |

The checkpoint and exact FP8 support trace are in:
`artifacts_hpca_xorflow/workloads/reddit_deepres8_w128_s7_native/`.

### Critical fix recorded here

`load_dataset()` previously applied PyG `NormalizeFeatures` to Reddit/Flickr/
Yelp dense benchmark features.  Reddit inputs are already standardized; this
shrunk their mean absolute magnitude from about 0.68 to 0.0017 and left even a
diagnostic MLP at majority-class accuracy.  The loader now preserves the
published dense feature scale for these datasets.  The failed attempts and
diagnostic logs are retained in `artifacts_hpca_xorflow/logs/`; do not use
their traces as valid workload results.

## Existing causal XORFLOW evidence

All values below are aggregation-memory results, not end-to-end accelerator
measurements.

| workload / pair | exact traffic reduction vs equally laid-out BEICSR | calibrated host estimate | Ramulator2 HBM result |
|---|---:|---:|---:|
| OGBN-Arxiv DeepRes8, layers 4–5 | 22.7% | 1.236x | 1.262x |
| OGBN-Arxiv DeepRes8, layers 6–7 | 32.4% | 1.379x | 1.432x |
| Cora DeepRes28 late pairs | 38–41% | 1.24–1.26x | boundary only |

The Arxiv Ramulator rows verify every submitted HBM transaction was served.
See `results_hpca_xorflow/01_causal_pair_preflight.csv`,
`02_host_model.csv`, and `03_ramulator_pairs.csv`.

## Implementation present

- exact causal two-layer XORFLOW selector and topology-cohort dictionary;
- hardware bit packing/unpacking and exact round-trip tests;
- fixed-address sliced layouts, 64-byte cache-line enumeration, LRU simulator;
- output write-allocate/writeback and topology traffic accounting;
- SCALE-Sim cached 32x32 weight-stationary combination calibration;
- real Ramulator2 HBM2 transaction emitter with request-drain verification;
- checkpointed full-graph normalized-CSR DeepRes training/inference for the
  8 GiB GPU;
- staged entrypoint: `scripts/run_hpca.sh` and principal configuration:
  `configs/hpca_xorflow.yaml`.

## What remains

1. Add the Reddit trace to the causal preflight / host / Ramulator pipeline.
   `hpca_xorflow_cli._case()` currently needs a named workload-artifact path
   for the new config.
2. Complete valid Flickr and Yelp training/tracing.  Yelp needs its dedicated
   multi-label BCE/micro-F1 runner.
3. Run causal selector, null controls, cache/order/slice sensitivities, and
   both Ramulator2 and DRAMsim3 cross-checks for the three large workloads.
4. Finish the common event-driven host model, CUDA throughput microbenchmarks,
   CACTI and OpenROAD PPA/energy stages, figures, gates, reproducibility rerun,
   and final paper-suite report.

## Reproduction environment

```bash
export MOSAIC_PY=/home/rishabh/miniconda/envs/taugat_pyg/bin/python
export PYTHONPATH=src
"$MOSAIC_PY" -m pytest -q

# cached small/Arxiv preflight and host model
bash scripts/run_hpca_xorflow_preflight.sh
"$MOSAIC_PY" -m mosaic_validation.hpca_host

# valid Reddit artifact already exists; do not retrain unless intentionally
# reproducing it
"$MOSAIC_PY" scripts/train_hpca_workload.py \
  --dataset Reddit --config-id reddit_deepres8_w128_s7_native \
  --seed 7 --width 128 --layers 8 --max-epochs 160 \
  --learning-rate .001 --csr-checkpoint-training
```

Runtime facts: PyTorch 2.8.0+cu128, PyG 2.6.1, NVIDIA RTX 4060 Laptop GPU,
and pinned Ramulator2 commit `99a0e1e87a9321587492fef5b0bd6197928f8d68`.
The separate system Python 3.12 is used only for the existing Ramulator
nanobind module; ML work uses the Python 3.11 environment above.

## Archive contents/exclusions

`XORFLOW_HPCA_PROGRESS_HANDOFF.zip` includes source, tests, configs, scripts,
RTL, all Phase-0/1/2/3A/3B and safe-zone result tables/reports, the new HPCA
tables/logs, valid cached support traces/checkpoints, prior handoff notes, git
diff/status, and this document.

It excludes raw downloaded datasets, Conda environments, third-party histories,
and transient generated DRAM traces.  Public datasets are obtained with
`scripts/prepare_hpca_datasets.py`; OGBN-Arxiv uses the OGB downloader.
