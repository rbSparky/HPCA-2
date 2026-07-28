# XORFLOW: Completed HPCA-Ready Evidence

Generated from completed, hashed artifacts on 2026-07-28. This report includes only work that actually finished. It is a reviewer-facing evidence summary, not a claim that the complete paper suite is finished.

## Scope and status

| Item | Status | Evidence |
|---|---|---|
| Overnight admission tranche | COMPLETE | [HPCA_RESULTS_INDEX.md](HPCA_RESULTS_INDEX.md) |
| Hard deadline | 2026-07-31 23:59 UTC | 76+ hours remained at completion |
| GPU policy | GPU 1 only for project jobs; GPU 0 untouched | `artifacts_hpca_xorflow/overnight_smoke.json` |
| Cached-trace smoke and targeted regression tests | PASS | `artifacts_hpca_xorflow/logs/overnight_pytest.log` (11 passed) |
| SCALE-Sim host canary | PASS | `results_hpca_xorflow/runs/*/host_model_overnight.csv` |
| Ramulator HBM2 tiny smoke | PASS | `artifacts_hpca_xorflow/ramulator/overnight_tiny.json` |
| PPA tools | UNAVAILABLE, explicitly recorded | smoke manifest (`yosys`, Verilator, CACTI, OpenROAD absent) |

## Failure resolution

The evidence index retains three failed Ramulator attempts for auditability. They are **superseded infrastructure attempts**, not failed scientific configurations:

| Attempt | Cause | Resolution | Final status |
|---|---|---|---|
| Cora pair smoke | Cached Cora support trace was not present on the remote mirror | Replaced with a bounded four-request trace | SUPERSEDED |
| Tiny Ramulator smoke (CUDA environment) | Ramulator extension was compiled for system Python 3.12, not the CUDA Python 3.11 environment | Pinned `/usr/bin/python3.12` and correct library path | SUPERSEDED |
| Tiny Ramulator smoke (wrapper quoting) | Initial environment-variable quoting prevented extension loading | Corrected shell exports and reran | **PASS** |

No completed principal model or exact-decoding run is invalidated by these tool-admission failures. The raw attempts remain in [HPCA_RESULTS_INDEX.csv](HPCA_RESULTS_INDEX.csv) and the corrected output is [overnight_tiny.json](../artifacts_hpca_xorflow/ramulator/overnight_tiny.json).

## Model quality

FP8 support traces were evaluated after trained FP32 models; accuracy values below are FP8/FP16 inference values. `BORDERLINE` is supplementary and is not used to satisfy a hard gate.

| Configuration | Dataset | Test metric | Quality class | Best epoch | Finite loss | Trace |
|---|---|---:|---|---:|---|---|
| `ogbn_arxiv_deepres8_w128_s17` | OGBN-Arxiv | accuracy **0.682777** | HARD_VALID | 138 | yes | [record.json](../artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres8_w128_s17/record.json) |
| `ogbn_arxiv_deepres8_w128_s27` | OGBN-Arxiv | accuracy **0.686583** | HARD_VALID | 134 | yes | [record.json](../artifacts_hpca_xorflow/workloads/ogbn_arxiv_deepres8_w128_s27/record.json) |
| `reddit_deepres8_w128_s7_native` | Reddit | accuracy **0.953360** | HARD_VALID | 160 | yes | [record.json](../artifacts_hpca_xorflow/workloads/reddit_deepres8_w128_s7_native/record.json) |
| `flickr_deepres8_w128_s7` | Flickr | accuracy **0.472281** | HARD_VALID | 138 | yes | [record.json](../artifacts_hpca_xorflow/workloads/flickr_deepres8_w128_s7/record.json) |
| `yelp_deepres8_w128_s7_balanced_fallback` | Yelp | micro-F1 **0.433952** | **BORDERLINE** (0.016 below 0.45) | 92 | yes | [record.json](../artifacts_hpca_xorflow/workloads/yelp_deepres8_w128_s7_balanced_fallback/record.json) |

## Common evaluation configuration

| Parameter | Value |
|---|---|
| Segment | causal layers 4–5 (W=2) |
| Tile / slice | 128 rows / 128 features |
| Feature cache | 512 KiB, 16-way, 64-byte lines |
| Edge order | original CSR destination order (O0) |
| HBM roofline | 256 GB/s at 1 GHz (256 B/cycle) |
| Decoder | exact support stream; 2,048 bits/cycle analytical model |
| Representation decision | causal XORFLOW only when exact support cost beats independent BEICSR; otherwise fallback |

## Exact causal traffic and support results

Values are from [01_causal_pair_preflight.csv](01_causal_pair_preflight.csv). `traffic_reduction` and `serialized_speedup` are modeled memory/host proxies, not measured end-to-end accelerator speedups.

| Configuration | Nodes | Edges | XOR support / BEICSR support | Traffic reduction | Serialized memory proxy | Double-buffer proxy | Exact | Causal |
|---|---:|---:|---:|---:|---:|---:|---|---|
| OGBN-Arxiv s17 | 169,343 | 2,315,598 | 0.723 | 13.62% | 1.146× | 1.156× | PASS | PASS |
| OGBN-Arxiv s27 | 169,343 | 2,315,598 | 0.719 | 15.63% | 1.222× | 1.232× | PASS | PASS |
| Reddit s7 | 232,965 | 114,615,892 | 0.675 | **36.86%** | **1.583×** | **1.584×** | PASS | PASS |
| Flickr s7 | 89,250 | 899,756 | 0.387 | **32.77%** | 1.052× | 1.058× | PASS | PASS |
| Yelp fallback | 716,847 | 13,954,819 | 0.484 | 7.45% | 1.076× | 1.080× | PASS | PASS |

Full per-run values, including cache hits/misses, topology traffic, writeback traffic, descriptor cycles, and decode cycles are in [01_causal_pair_preflight.csv](01_causal_pair_preflight.csv).

## Modeled host results

The normalized host model combines exact traffic with SCALE-Sim combination-array cycles and explicit aggregation, descriptor, encoding, and decoding costs. It is not a full-chip measurement.

| Configuration | BEICSR host cycles | XORFLOW host cycles | Host-cycle ratio | SCALE-Sim cycles/engine | Utilization | Support cache fits |
|---|---:|---:|---:|---:|---:|---|
| OGBN-Arxiv s17 | 2,719,713 | 2,415,606 | **1.126×** | 340,191 | 99.56% | yes |
| OGBN-Arxiv s27 | 2,719,731 | 2,306,355 | **1.179×** | 340,191 | 99.56% | yes |
| Reddit s7 | 112,546,814 | 71,268,981 | **1.579×** | 467,439 | 99.68% | yes |
| Flickr s7 | 1,132,475 | 1,076,635 | **1.052×** | 180,015 | 99.17% | yes |
| Yelp fallback | 16,386,542 | 15,327,542 | 1.069× | 1,435,199 | 99.90% | yes |

Source: [02_host_model.csv](02_host_model.csv) and per-configuration files under [runs/](runs/).

## Density-matched structural controls

The control calculation uses seed 7007 and two causal pairs per trace. `metadata_reduction` is relative to independent support metadata. Lower support ratio is better.

| Configuration | Real density | Real support ratio | Independent-null ratio | Node-permuted ratio | Temporal-shuffle ratio | Real reduction vs independent |
|---|---:|---:|---:|---:|---:|---:|
| OGBN-Arxiv s17 | 0.503 | 0.711 | 0.911 | 0.911 | 0.881 | **3.26×** |
| OGBN-Arxiv s27 | 0.492 | 0.710 | 0.911 | 0.911 | 0.889 | **3.28×** |
| Reddit s7 | 0.455 | 0.675 | 0.911 | 0.911 | 0.847 | **3.67×** |
| Flickr s7 | 0.512 | 0.387 | 0.836 | 0.804 | 0.414 | **3.75×** |

These controls show that the real learned masks contain structure beyond density alone. Temporal shuffling is especially informative: for Flickr it largely removes the benefit; for Arxiv and Reddit it weakens but does not eliminate it. Full rows are in [overnight_null_controls.csv](overnight_null_controls.csv).

## Tool and reproducibility evidence

| Check | Result | Interpretation |
|---|---|---|
| Targeted regression tests | 11 passed | No failure in the admitted HPCA path |
| Exact causal decoding | true for all completed pairs | No support approximation introduced |
| SCALE-Sim calls | successful for all host rows | Regular combination path is callable and parsed |
| Ramulator HBM2 smoke | successful on a bounded four-request trace | Real extension loaded with system Python 3.12; no giant text trace retained |
| GPU availability | CUDA true on GPU 1 | Recorded by smoke manifest |
| PPA tools | unavailable | No fabricated area, timing, or power claims |

## Reviewer interpretation

The completed evidence supports a focused claim: causal two-layer XORFLOW can reduce exact support metadata and modeled feature traffic, with the largest benefit on the large, memory-bound Reddit trace and meaningful benefit on OGBN-Arxiv. The learned-mask controls are positive at matched density. The current results do **not** establish a full accelerator speedup, energy reduction, or paper-complete hardware evaluation. Those require the remaining sensitivity, larger seed/workload coverage, end-to-end memory timing, and PPA work.

The strongest positive result is Reddit: 36.86% modeled traffic reduction and 1.579× normalized host-cycle ratio. The strongest caution is that the present primary segment is W=2 and the host model remains analytical around memory/aggregation; the report must not present these ratios as measured end-to-end hardware speedups.

## Artifact index

| Evidence | Path |
|---|---|
| Live queue and hashes | [HPCA_RESULTS_INDEX.md](HPCA_RESULTS_INDEX.md) |
| Model records and packed supports | [artifacts_hpca_xorflow/workloads/](../artifacts_hpca_xorflow/workloads/) |
| Exact traffic table | [01_causal_pair_preflight.csv](01_causal_pair_preflight.csv) |
| Modeled host table | [02_host_model.csv](02_host_model.csv) |
| Null controls | [overnight_null_controls.csv](overnight_null_controls.csv) |
| Run logs | [artifacts_hpca_xorflow/logs/](../artifacts_hpca_xorflow/logs/) |
| Environment smoke | [overnight_smoke.json](../artifacts_hpca_xorflow/overnight_smoke.json) |
| Ramulator smoke output | [overnight_tiny.json](../artifacts_hpca_xorflow/ramulator/overnight_tiny.json) |
