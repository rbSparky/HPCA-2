# MOSAIC-PANEL Phase-3A results

## Executive decision

`STOP_DEPTHWISE_REGULAR_PATH`

Cached-trace wall-clock: 5390.5 seconds. No model was retrained. The user-authorized runtime extension allowed up to 6750 seconds.

## Gate table

| gate_id | status |
| --- | --- |
| G1 | PASS |
| G2 | PASS |
| G3 | FAIL |
| G4 | FAIL |
| G5 | FAIL |
| G6 | FAIL |
| G7 | PASS |
| G8 | AMBER |
| G9 | PASS |
| G10 | FAIL |
| G11 | PASS |
| PHASE3A_DECISION | STOP_DEPTHWISE_REGULAR_PATH |

## Principal summary

| config_id | model_valid | median_density | best_panel_builder | best_panel_width | best_escape_enabled | panel_hybrid_speedup | panel_hybrid_speedup_rho1_25 | panel_hybrid_speedup_rho1_50 | panel_hybrid_speedup_rho1_75 | panel_hybrid_speedup_rho2_00 | panel_byte_ratio_to_R0 | panel_byte_ratio_to_phase2_anchor | panel_capture | panel_padding | panel_residual_fraction | panel_gain_over_contiguous | panel_gain_over_density_sorted | panel_gain_over_fixed_bsr | layer_local_oracle_speedup | oracle_gap_closed | mean_segment_length | greedy_to_dp | peak_live_bytes | capacity_pass | null_structural_gain | exactness_pass | numeric_equivalence_pass |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cora_gcnii16 | True | 0.7853391127428702 | P3_COST_AWARE | 32 | False | 0.7610248751387579 | 0.7613653574690457 | 0.7610248751387579 | 0.7607371202243677 | 0.7604879435282329 | 0.8749564459930314 | 0.6211360313851721 | 0.9975466440000158 | 0.2136839254148371 | 0.0024533559999841 | 0.0009091472265985 | -0.000750088319551 | 0.4052497252745719 | 0.7626977295189385 | 0 | 13.0 | 1.0 | 68697 | True | 0.0006953615610596 | True | True |
| pubmed_gcnii16 | True | 0.6742088655435957 | P3_COST_AWARE | 32 | True | 0.8042190253904296 | 0.8081121853875242 | 0.8042190253904296 | 0.8009420417495684 | 0.7981141845470651 | 0.854293883223735 | 0.5743210265132747 | 0.9735125097094608 | 0.2440966988073066 | 0.0264874902905392 | 0.0592905692807095 | 0.0155035370335163 | 1.0770093885850405 | 0.7817053512130231 | 0 | 13.0 | 1.0 | 69709 | True | 0.0756374780006805 | True | True |
| cora_deepres28_w128 | True | 0.4408892632939438 | P3_COST_AWARE | 32 | False | 0.9279012673185264 | 0.9630789406665676 | 0.9279012673185264 | 0.8991633203254956 | 0.8749898047470749 | 1.0182813363768703 | 0.7563594665354778 | 0.7959097726255506 | 0.3429451111157208 | 0.2040902273744493 | 0.2324960993679197 | -0.0194479054769272 | 0.2722281704075071 | 0.8397325320472299 | 0 | 13.0 | 1.0 | 106313 | True | 0.0198227627680325 | True | True |
| chameleon_gcnii16 | True | 0.7073810850984764 | P3_COST_AWARE | 32 | True | 0.7857462927792259 | 0.7896894584012509 | 0.7857462927792259 | 0.7824277588064594 | 0.7795644449012943 | 0.8544938550710696 | 0.6006274655563416 | 0.9725440039161024 | 0.2153399895965784 | 0.0274559960838977 | 0.0412819790711449 | 0.016080230514287 | 1.045173364334934 | 0.7900047075233196 | 0 | 13.0 | 1.0 | 68649 | True |  | True | True |
| cora_resgcn16 | False | 0.3411628472616748 | P3_COST_AWARE | 32 | True | 0.8499547470697792 | 0.8954662340345283 | 0.8499547470697792 | 0.8132847299921644 | 0.7828010042411502 | 0.8371929621929622 | 0.4344301950073875 | 0.7139043450997126 | 0.5232315878002669 | 0.2860956549002874 | 0.110194624999065 | -0.0226707207308285 | 0.4852454254648086 |  | 1 | 13.0 | 1.0 | 63729 | True |  | True | True |
| pubmed_deepres28_w128 | False | 0.4270157097935791 | P3_COST_AWARE | 32 | False | 1.046759722565207 | 1.0807560640641434 | 1.046759722565207 | 1.0188518954216577 | 0.9952791797638678 | 0.917104425843684 | 0.6578297201038568 | 0.8246974089071831 | 0.2610279855749889 | 0.1753025910928168 | 1046759721.5652068 | 1046759721.5652068 | 1046759721.5652068 |  | 1 | 13.0 | 1.0 | 107021 | True |  | True | True |

## Interpretation

Exact transfer bytes, real SCALE-Sim regular GEMM cycles, analytical sparse-residual cycles, modeled gather/decode/accumulation cycles, and calibrated hybrid combination cycles are reported separately. The hybrid values are not measured end-to-end GNN accelerator speedups; graph aggregation, full memory traffic, and system-level scheduling remain unmodeled.

The panel mapping was intended to fix the Phase-2 K≈F problem. It did not: after charging real small-GEMM startup, systolic utilization, panel holes, residual imbalance, row-list metadata, weight-panel packing, and partial-output accumulation, deployable panel hybrid speedups remain below 1 on Cora, PubMed, and the valid deep residual trace. The layer-local oracle is also below the predeclared stop thresholds, so this is not only a persistence problem.

The exact support structure and transfer-byte reductions remain real, but they do not translate into a calibrated regular-GEMM advantage. The evidence supports stopping the depthwise regular path and retaining only sparse/memory-format ideas for possible future work; a Phase-3B full accelerator is not justified.
