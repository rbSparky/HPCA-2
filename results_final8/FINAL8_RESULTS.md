# Final one-byte MOSAIC-XORFLOW result

Decision: `SAVE_MOSAIC_WITH_FP8_XORFLOW_PARALLEL_DECODE`

## What saved the direction

Ordinary UINT8 activation quantization lost 2--6 accuracy points and was
rejected. FP8 E4M3 uses the same one byte per active value but loses only
0.1--0.22 percentage points. Supports were recaptured from actual FP8 inference.

The initial single 64-bit global decoder also failed badly. Tile reconstruction
is independent, so the final architecture uses 32 small 64-bit decoders, one
aggregate 2,048-bit/cycle decode path matching the 256-byte/cycle HBM interface.
The failed 64-bit result remains visible in `serialized_speedup`.

## Principal results

```text
          config_id  fp32_test_accuracy  fp8_test_accuracy  test_accuracy_drop  median_density  best_slice_width  best_beicsr_slice_width best_edge_order  support_ratio_to_beicsr  traffic_reduction  traffic_speedup  serialized_speedup  free_support_serialized_speedup  support_cache_peak_bytes  exactness_pass  parallel_decode_speedup selected_representation  aggregate_decode_width_bits
       cora_gcnii16            0.790000           0.789000            0.001000        0.778774                64                       64              O0                 0.425406           0.106857         1.119641            0.478143                         1.149370                      2112            True                 1.059224                 XORFLOW                         2048
     pubmed_gcnii16            0.798000           0.796000            0.002000        0.660113               128                      128              O0                 0.386110           0.158706         1.188645            0.625831                         1.201672                      2048            True                 1.138177                 XORFLOW                         2048
cora_deepres28_w128            0.757000           0.756000            0.001000        0.440464               128                      128              O0                 0.678464           0.226150         1.292240            0.314557                         1.385448                      3648            True                 1.148282                 XORFLOW                         2048
  chameleon_gcnii16            0.368421           0.366228            0.002193        0.508756                64                       64              O0                 0.443769          -0.003752         0.996262            0.490596                         1.029747                      2304            True                 1.000000                  BEICSR                         2048
```

At 512 KiB, selector-protected serialized aggregation-memory speedups are
1.059x Cora, 1.138x PubMed, 1.148x valid DeepRes, and 1.000x Chameleon
(BEICSR fallback). Traffic reductions before decode are 10.7%, 15.9%, and 22.6%
on the three benefiting traces. These are aggregation-memory estimates, not
end-to-end GNN measurements.

## Learned-structure controls

```text
          config_id                control_type  density  support_ratio_to_beicsr  metadata_reduction  exact_decode_pass  control_support_ratio_over_real  real_support_ratio_advantage
       cora_gcnii16                    real_fp8 0.778774                 0.425406            0.574594               True                         1.000000                      0.000000
       cora_gcnii16 density_matched_independent 0.778546                 1.077150           -0.077150               True                         2.532051                      0.651744
       cora_gcnii16               node_permuted 0.778774                 1.078059           -0.078059               True                         2.534188                      0.652653
     pubmed_gcnii16                    real_fp8 0.660113                 0.386110            0.613890               True                         1.000000                      0.000000
     pubmed_gcnii16 density_matched_independent 0.660061                 1.134733           -0.134733               True                         2.938889                      0.748624
     pubmed_gcnii16               node_permuted 0.660113                 1.103679           -0.103679               True                         2.858459                      0.717569
cora_deepres28_w128                    real_fp8 0.440464                 0.678464            0.321536               True                         1.000000                      0.000000
cora_deepres28_w128 density_matched_independent 0.440706                 1.063811           -0.063811               True                         1.567970                      0.385347
cora_deepres28_w128               node_permuted 0.440464                 1.060089           -0.060089               True                         1.562484                      0.381625
  chameleon_gcnii16                    real_fp8 0.508756                 0.443769            0.556231               True                         1.000000                      0.000000
  chameleon_gcnii16 density_matched_independent 0.508956                 1.123205           -0.123205               True                         2.531060                      0.679437
  chameleon_gcnii16               node_permuted 0.508756                 1.112395           -0.112395               True                         2.506699                      0.668626
```

At matched density, independent and node-permuted masks require 1.56x--2.94x
as many support bits as real FP8 supports. The result is therefore not explained
by density alone.

## Gates

```text
                   gate                                       status
        F8_G1_EXACTNESS                                         PASS
         F8_G2_ACCURACY                                         PASS
F8_G3_PRINCIPAL_GEOMEAN                                         PASS
          F8_G4_DEEPRES                                         PASS
         F8_G5_TRANSFER                                         PASS
F8_G6_LEARNED_STRUCTURE                                         PASS
        FINAL8_DECISION SAVE_MOSAIC_WITH_FP8_XORFLOW_PARALLEL_DECODE
```

## Integrity and limitations

Feature traffic is simulated at exact 64-byte line granularity with fixed
in-place row-slice reservations, 16-way LRU, real graph edge order, topology
bytes, descriptors, aligned anchor/exception streams, support-cache capacity,
and conservative serialized decode cycles. The BEICSR comparator independently
selects its best slice width. Chameleon automatically falls back to BEICSR.

DRAM latency remains a 256-byte/cycle bandwidth roofline. Decoder area, energy,
bank conflicts, and a real DRAM timing run are not yet measured. Those are now
the mandatory paper-readiness checks; the 32-decoder assumption must survive
them. The evidence justifies continuing MOSAIC specifically as FP8 XORFLOW with
parallel tile decoders. It does not revive FP32 XORFLOW or the regular-panel
path.
