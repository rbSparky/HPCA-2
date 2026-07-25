# MOSAIC rescue audit

## Verdict

The Phase-3A result contains real implementation/accounting defects, but fixing
them does **not** rescue the FP32 monolithic panel architecture. The defensible
last-chance direction is narrower: INT8 MOSAIC-XORFLOW, with accuracy validation,
against a faithful INT8 BEICSR baseline.

## Confirmed Phase-3A defects

1. `LAYER_LOCAL_ORACLE` was not an oracle. It omitted the dense fallback, used
   density-sorted panels rather than a complete cost-aware search, and retained
   row-list decode cost despite declaring schedule metadata free. Its reported
   value below 1.0 must be replaced by at least 1.0.
2. The deployable prefix objective omitted residual-row output contributions on
   non-escaped panels. The reporting columns counted them, but
   `total_hybrid_cycles` did not. This defect made Phase-3A slightly optimistic;
   it cannot explain the slowdown.
3. P3 tested at most one Jaccard-proposed swap per pass rather than all legal
   cost-reducing swaps. This is a heuristic, not the specified full cost-aware
   swap search.
4. Weight packing was charged inside each tile optimizer even though weights are
   shared across graph tiles. Its measured impact is small and does not alter the
   decision.

## Corrected hardware audit

The same 1,024 MACs were mapped as one 32x32 array, four 16x16 arrays, and sixteen
8x8 arrays using real SCALE-Sim shape cycles. Tasks were scheduled per layer with
deterministic LPT; layer barriers were preserved. All residual, gather, decode,
and output contribution costs were retained.

```text
          config_id  density  reported_panel_speedup  reported_oracle_speedup  corrected_oracle_with_dense_fallback  monolithic32_corrected_speedup  partitioned_4x16_speedup  partitioned_16x8_speedup  partitioned_16x8_acc128_speedup  dense_16x8_vs_dense32  partitioned_16x8_acc128_speedup_vs_best_dense  ideal_nnz_compute_bound  fp32_beicsr_free_support_max_speedup  panel_survives_1_10
       cora_gcnii16 0.785339                0.761025                 0.762698                                   1.0                        0.763433                  1.067460                  1.163926                         1.419932               1.391953                                       1.020100                 1.273335                              1.039792                 True
     pubmed_gcnii16 0.674209                0.804219                 0.781705                                   1.0                        0.792179                  1.085902                  1.213789                         1.492583               2.005292                                       0.744322                 1.483220                              1.046351                 True
cora_deepres28_w128 0.440889                0.927901                 0.839733                                   1.0                        0.835106                  0.994567                  1.014527                         1.270341               1.413596                                       0.898659                 2.268143                              1.070879                False
  chameleon_gcnii16 0.707381                0.785746                 0.790005                                   1.0                        0.773925                  1.054379                  1.106874                         1.337858               1.156325                                       1.156991                 1.413665                              1.044177                 True
```

Partitioning initially appears to rescue the panel path when compared only with
the old monolithic dense baseline. That comparison is not fair: the dense
baseline can use the same reconfigurable subarrays across topology tiles.
Against the best dense mapping, the 16x8 plus 128-lane accumulator speedups are
only 1.020
on Cora, 0.744
on PubMed, and 0.899
on DeepRes. The regular-panel paper direction therefore remains stopped.

## Why FP32 XORFLOW is also structurally capped

BEICSR support costs only one bit per feature while each active FP32 value costs
32 bits. Even deleting support metadata entirely gives maximum logical-format
speedups of 1.040,
1.046, and
1.071
on Cora, PubMed, and DeepRes before topology traffic or cache-line rounding.
The Phase-3B FP32 gates are at or beyond this free-support ceiling.

## Quantified salvage hypothesis

```text
          config_id precision  value_bytes  density  phase2_anchor_metadata_ratio  free_support_max_speedup  anchor_storage_speedup_projection  anchor_logical_traffic_reduction
       cora_gcnii16      FP32            4 0.785339                      0.679385                  1.039792                           1.012422                          0.012270
       cora_gcnii16      FP16            2 0.785339                      0.679385                  1.079583                           1.024207                          0.023635
       cora_gcnii16      INT8            1 0.785339                      0.679385                  1.159167                           1.046052                          0.044024
     pubmed_gcnii16      FP32            4 0.674209                      0.618003                  1.046351                           1.017213                          0.016921
     pubmed_gcnii16      FP16            2 0.674209                      0.618003                  1.092701                           1.033493                          0.032407
     pubmed_gcnii16      INT8            1 0.674209                      0.618003                  1.185402                           1.063542                          0.059746
cora_deepres28_w128      FP32            4 0.440889                      0.614737                  1.070879                           1.026167                          0.025500
cora_deepres28_w128      FP16            2 0.440889                      0.614737                  1.141759                           1.050237                          0.047834
cora_deepres28_w128      INT8            1 0.440889                      0.614737                  1.283518                           1.093017                          0.085101
  chameleon_gcnii16      FP32            4 0.707381                      0.927075                  1.044177                           1.003095                          0.003085
  chameleon_gcnii16      FP16            2 0.707381                      0.927075                  1.088354                           1.005955                          0.005920
  chameleon_gcnii16      INT8            1 0.707381                      0.927075                  1.176708                           1.011073                          0.010951
```

At INT8, metadata is four times more important. Using the already observed
Phase-2 anchor metadata ratios as a conservative projection produces useful
logical-format speedups on the principal traces, whereas FP32 does not. This is
not yet a result: INT8 changes numerical values and therefore requires
post-training quantization or quantization-aware training plus accuracy checks.
It is, however, the only remaining hypothesis with enough mathematical
headroom to justify one bounded experiment.

## Next action

Do one final, predeclared INT8 XORFLOW kill test: preserve exact support coding,
quantize packed values, verify model accuracy, compare cache-line traffic against
INT8 BEICSR, and stop if Cora/PubMed geomean serialized aggregation-memory
speedup is below 1.05 or DeepRes is below 1.08. Do not continue the FP32 memory
format or any regular-panel mapping.
