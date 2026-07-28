# XORFLOW Hardware-Metric Audit

This audit checks whether the completed numbers are internally consistent and whether they meet the evidence standard required for an HPCA submission. It does not convert modeled values into measured hardware results.

## SCALE-Sim calibration

| Check | Result | Meaning |
|---|---|---|
| Array | 32×32 | Matches the declared weight-stationary combination array |
| SRAMs | 256 KiB ifmap / 256 KiB filter / 256 KiB ofmap | Matches the common host configuration |
| Shape | `M=ceil(nodes/8), K=128, N=128` | One calibrated combination shape per host row |
| Cache | Shape cache keyed by `(M,N,K)` | Avoids duplicate simulator calls, never reduces modeled execution count |
| Calls | All completed host rows succeeded | `combination_scalesim_success=True` |
| Utilization | 99.17–99.90% | Valid SCALE-Sim report field for the large, regular `128×128` GEMMs; not utilization of the sparse aggregation path |
| Interpretation | Calibrated combination component only | Host ratios remain modeled aggregation/memory estimates, not measured end-to-end speedups |

The high utilization is expected for large regular GEMMs and does not demonstrate that XORFLOW’s irregular support decoder is systolic-efficient. That distinction is preserved in [HPCA_PAPER_READY_RESULTS.md](HPCA_PAPER_READY_RESULTS.md).

## RTL decoder

The local Yosys/YoWASP synthesis and formal smoke completed successfully:

| Top | Cells | Longest topological path | Formal checks |
|---|---:|---:|---|
| `xorflow_decoder_lane` | 1,663 | 33 logic levels | PASS |
| `xorflow_decoder_bank` (32 lanes) | 53,344 | 35 logic levels | PASS |

Evidence: [lane_synthesis.log](../artifacts_safezone/decoder/lane_synthesis.log), [bank_synthesis.log](../artifacts_safezone/decoder/bank_synthesis.log), and [formal.log](../artifacts_safezone/decoder/formal.log).

This is decoder logic synthesis/formal validation only. No area, power, CACTI SRAM result, OpenROAD placement, routing, or 1 GHz timing claim is made because those tools are not installed in the current environment.

## Ramulator2

The existing Arxiv HBM2 rows verified exact request drain:

| Pair | Format | Requests submitted | Requests served | Drain | Ramulator cycles | Ratio vs BEICSR |
|---|---|---:|---:|---|---:|---:|
| Arxiv layers 4–5 | BEICSR | 18,866,438 | 18,866,438 | PASS | 6,613,724 | 1.000× |
| Arxiv layers 4–5 | XORFLOW | 14,582,382 | 14,582,382 | PASS | 5,240,245 | 1.262× |
| Arxiv layers 6–7 | BEICSR | 18,861,582 | 18,861,582 | PASS | 6,613,084 | 1.000× |
| Arxiv layers 6–7 | XORFLOW | 12,759,572 | 12,759,572 | PASS | 4,618,386 | 1.432× |

These are bounded pair-level HBM2 transaction experiments, not full GNN execution timing. The later four-request smoke confirms the Python 3.12 extension path; all transient large text traces were removed.

## Metric consistency checks

- Every completed causal row has `exact_decode_pass=True` and `causal_deployable=True`.
- Every completed host row has `combination_scalesim_success=True` and `support_cache_fits=True`.
- Host ratios are computed from the explicit reported cycle totals (`BEICSR host cycles / XORFLOW host cycles`); they are not copied from byte ratios.
- Traffic reductions, support ratios, cache hits/misses, writebacks, topology bytes, descriptor cycles, and decoder cycles remain available in the raw CSVs.
- Failed tool attempts remain in the index as `SUPERSEDED`; the corrected Ramulator result is the only one used for the positive tool conclusion.

## Remaining HPCA-critical gaps

The following are still required before calling the work paper-ready: full event-driven overlap with finite buffers and layer barriers; DRAMsim3 independent cross-check; CUDA 100-repetition throughput measurements; CACTI SRAM energy/area; OpenROAD routed PPA; expanded model/operator coverage; and two complete no-training reproducibility runs with unchanged prior hashes.
