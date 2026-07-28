# MOSAIC-Anchor Phase-2 results

## Executive decision

`ITERATE_ANCHOR_ENCODING`

Cached-trace wall-clock: 364.9 seconds. No model was retrained.

## Gates

| gate_id | status |
| --- | --- |
| G1 | PASS |
| G2 | FAIL |
| G3 | FAIL |
| G4 | PASS |
| G5 | PASS |
| G6 | PASS |
| G7 | PASS |
| G8 | FAIL |
| G9 | PASS |
| PHASE2_DECISION | ITERATE_ANCHOR_ENCODING |

## Principal summary

| config_id | model_valid | median_density | delta_v1_metadata_ratio | chain_gap_metadata_ratio | anchor_metadata_ratio | chain_gap_relative_metadata_reduction | anchor_relative_metadata_reduction | anchor_byte_ratio | anchor_byte_ratio_to_phase0 | anchor_proxy_speedup_rho1_25 | anchor_proxy_speedup_rho1_50 | anchor_proxy_speedup_rho1_75 | anchor_hybrid_combination_speedup | anchor_capture | anchor_padding | anchor_segment_length | anchor_greedy_to_dp | entropy_overhead_median | entropy_overhead_p90 | chain_replay_amplification | chain_state_bytes | anchor_independent_decode | null_structural_gain | phase0_proxy | oracle_gap_recovery |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cora_gcnii16 | True | 0.7853391127428702 | 0.2554122045790251 | 0.4172128877400295 | 0.6793845781019202 | -0.6334884561514478 | -1.6599534631545652 | 0.7099050863957167 | 0.908557634905391 | 1.252091490991056 | 1.2378013941263857 | 1.2130453662438578 | 0.7211988760536997 | 0.9508999794010654 | 0.0 | 13.0 | 1.0 | 1.2362459546925566 | 1.3017433252549298 | 1.4738153811522197 | 21664 | True | 0.0005033835703274 | 1.1216443604545807 | 1.4910553627192626 |
| pubmed_gcnii16 | True | 0.6742088655435957 | 0.2783638484556474 | 0.3776854601993203 | 0.618003341025511 | -0.3568049956727701 | -1.2201278810239593 | 0.6722757095556343 | 0.9097240592553404 | 1.4544138520434773 | 1.4378593365034755 | 1.409102149773406 | 0.7715430861723447 | 0.9511859577676468 | 0.0 | 13.0 | 1.0 | 1.2301587301587302 | 1.3144055180627234 | 1.4570037713769182 | 157736 | True | 0.0014169610666474 | 1.2905920579611132 | 0.7168503570419049 |
| cora_deepres28_w128 | True | 0.4408892632939438 | 0.3735228951255539 | 0.4615757997138109 | 0.6147374388386263 | -0.2357362981957487 | -0.6457824857884331 | 0.7427804473237896 | 0.860824910180958 | 1.9107009440422829 | 1.865855585383943 | 1.828538473676264 | 0.9730031720417875 | 0.8990675630836227 | 0.0 | 12.5 | 1.0 | 1.2144802867383513 | 1.277957088041744 | 1.6751225384813828 | 43328 | True |  | 1.0 | 1.0577217827796646 |
| chameleon_gcnii16 | True | 0.7073810850984764 | 0.3540294246815986 | 0.5888710474308301 | 0.9270747557092666 | -0.6633392774073501 | -1.6186375794696852 | 0.7029043708060212 | 0.9138372406359472 | 1.3439071526596609 | 1.305176376547612 | 1.27907284901666 | 0.5397843427870515 | 0.8691136223096747 | 0.0 | 13.0 | 1.0 | 1.2462686567164178 | 1.3592869773175316 | 1.6826226096570265 | 18216 | True |  | 1.2014246141669964 | 1.1645017374242277 |
| cora_resgcn16 | False | 0.3411628472616748 | 0.6113367799113737 | 0.9739386193685377 | 1.0356755446824224 | -0.5931294359710058 | -0.6941162035638779 | 0.5189128607453068 | 0.9110659773510584 | 1.6910541947371551 | 1.5186319298284807 | 1.488259291231911 | 0.4537864649837933 | 0.4619127110463016 | 0.0 | 13.0 | 1.0 | 1.2923502152425723 | 1.4039457496310062 | 1.755575437491346 | 21664 | True |  | 1.6619124591930523 | 0.8075067560804724 |
| pubmed_deepres28_w128 | False | 0.4270157097935791 | 0.1941091443931632 | 0.3962077062306639 | 0.4352147337957093 | -1.041159407864655 | -1.2421135034946769 | 0.7172898762304967 | 0.916271882310684 | 1.938463046526308 | 1.9098431962791411 | 1.8716463323535584 | 1.2358483882394615 | 0.9382984553686587 | 0.0 | 12.5 | 1.0 | 1.1869009584664536 | 1.2468619246861925 | 1.5548261947140976 | 315472 | True |  | 1.0 | 0.7331256317007395 |

## Interpretation discipline

This phase reports exact representation bytes, analytical compute proxies,
SCALE-Sim regular-path cycles, and a hybrid combination-path estimate. The
hybrid is **not** a measured end-to-end accelerator speedup. No full graph
aggregation or memory-system measurement is available yet.

CHAIN-GAP is an optimistic reference. Its deployability is limited by replay or
the N×F support-state lifetime. MOSAIC-Anchor is independently decodable from a
persistent anchor and one layer-local exception stream.

## Strongest results

The strongest positive result is the valid sparse deep target: analytical
anchor proxies are 1.911 at rho=1.25 and
1.866 at rho=1.50, with exact independent
decoding. Principal Cora/PubMed byte ratios versus independently decodable R0
are 0.710/0.672, and their
analytical rho=1.25 proxies are
1.252/1.454.

The strongest negative result is calibration: hybrid combination-path estimates
are only 0.721 for Cora,
0.772 for PubMed, and
0.973 for the valid deep target. Anchor
feature coverage leaves GEMM K close to dense, then residual/decode work erases
the analytical slot-model advantage. CHAIN-GAP also increases metadata relative
to Delta-v1 and has principal replay amplification above 1.45×; it should remain
an upper-bound reference, not a deployable design.

## Phase-3 conclusion

Phase-3 accelerator implementation is **not yet justified**. Evidence supports
continued depthwise-anchor encoding work—not a spatial-only pivot—because G4,
G5, G6, and G7 pass and Anchor improves Phase-0 bytes. The next iteration must
reduce effective GEMM K or explicitly exploit lane masks in the regular path,
then repeat calibration before aggregation/memory-system implementation.

Phase-3 must still model event-decoder bandwidth, lane imbalance, anchor-hole
padding, layer barriers, aggregation dominance, weight-panel changes, and the
complete memory system.
