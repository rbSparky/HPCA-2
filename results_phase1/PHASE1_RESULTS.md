# MOSAIC-Delta Phase-1 results

## Executive decision

`ITERATE_DELTA_ENCODING`

Wall-clock: 1666.4 seconds. Actual device: `cuda`.

## Model validity

| config_id | dataset | model | attempt | valid | epochs | best_epoch | train_accuracy | val_accuracy | test_accuracy | epoch2_val_loss | best_val_loss | train_seconds | trace_seconds | peak_gpu_memory_mb | median_density | median_temporal_flip |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cora_deepres28_w128 | Cora | deepres_v2 | primary | True | 80 | 20 | 0.9928571581840515 | 0.7580000162124634 | 0.7570000290870667 | 2.0168368816375732 | 0.8613830804824829 | 18.421850077000272 | 0.3408689530006086 | 349.9619140625 | 0.4520186138293944 | 0.06418845567317687 |
| pubmed_deepres28_w128 | PubMed | deepres_v2 | primary | False | 74 | 14 | 0.6666666865348816 | 0.6040000319480896 | 0.612000048160553 | 1.066494107246399 | 0.8869205117225647 | 111.54458330099988 | 1.286691504999908 | 2133.072265625 | 0.4880900682152457 | 0.049097052576362946 |
| pubmed_deepres28_w128 | PubMed | deepres_v2 | fallback | False | 96 | 36 | 0.9666666984558105 | 0.7380000352859497 | 0.7320000529289246 | 1.1571816205978394 | 0.8192803859710693 | 144.61382529099865 | 1.0409390620006889 | 2133.072265625 | 0.42079071201247653 | 0.04709141587255968 |

## Principal results

| config_id | model_valid | median_density | median_proxy_speedup_rho1_10 | median_proxy_speedup_rho1_25 | median_proxy_speedup_rho1_50 | median_byte_ratio | median_rho_delta_max_1_15 | median_padding | metadata_ratio | metadata_reduction | greedy_segment_length | greedy_to_dp | grouping_gain_over_random | oracle_gap_recovery | phase0_proxy_speedup | relative_proxy_improvement | fallback_overhead_fraction | global_oracle_proxy | delta_selection_fraction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chameleon_gcnii16 | True | 0.734663208168643 | 1.318036281144642 | 1.2801664666179626 | 1.2218919490259896 | 0.8687052882592229 | 1.84760063747578 | 0.03406795770464536 | 0.7294114667747164 | 0.27058853322528365 | 2.6 | 1.0011681611966117 | 0.05840140820432649 | 1.1645017374242275 | 1.2014246141669964 | 0.06554040222120938 | 0.001 | 1.2697048184613031 | 1.0 |
| cora_gcnii16 | True | 0.7882258585672083 | 1.2131223139434582 | 1.1860804759284782 | 1.143593856263188 | 0.8824747411750031 | 1.4691035796645948 | 0.026763619178553015 | 0.6899587446589067 | 0.3100412553410933 | 3.25 | 1.001414530919518 | 0.055002778980496325 | 1.4910553627192626 | 1.1216443604545807 | 0.05744790215660056 | 0.001 | 1.1650023159455802 | 1.0 |
| cora_resgcn16 | False | 0.3298155926883309 | 1.761148606807387 | 1.6392207701588004 | 1.6392207701588004 | 0.842432332903701 | 2.161639382651436 | 0.04072325861290808 | 0.7832636586420643 | 0.21673634135793574 | 1.0 | 1.0 | 0.03478813792022417 | 0.8075067560804724 | 1.6619124591930523 | -0.013653961680550775 | 0.001 | 1.739422412750517 | 0.0 |
| pubmed_gcnii16 | True | 0.6790658124968302 | 1.4125877042952144 | 1.3805640193841477 | 1.3303003335845989 | 0.8497024609360003 | 2.5857012881107133 | 0.02033407664926107 | 0.625192222260192 | 0.374807777739808 | 3.25 | 1.0008548322545088 | 0.07675252747899974 | 0.7168503570419049 | 1.2905920579611132 | 0.06971371074851707 | 0.001 | 1.4236650890154863 | 1.0 |
| cora_deepres28_w128 | True | 0.43713360875184637 | 1.8114893916181503 | 1.7316623325629688 | 1.613182891743787 | 0.8991421677293503 | 2.978951145436998 | 0.04536189480058777 | 0.6648568151042866 | 0.3351431848957134 | 3.5714285714285716 | 1.0012301031434954 | 0.08609591073405243 | 1.0577217827796646 | 1.0 | 0.7316623325629688 | 0.001 | 1.7431670657122238 | 1.0 |
| pubmed_deepres28_w128 | False | 0.4186829576000406 | 1.8688615401853044 | 1.8233623197963453 | 1.7524615009747881 | 0.8703974232869098 | 4.860804559819675 | 0.022041789588115635 | 0.677157732914945 | 0.32284226708505503 | 3.125 | 1.0009642231760116 | 0.0815743661483539 | 0.7331256317007395 | 1.0 | 0.8233623197963453 | 0.001 | 1.8794763446465024 | 1.0 |

## Gate table

| gate_id | status | evidence |
| --- | --- | --- |
| exactness | PASS | all real/synthetic masks exact |
| temporal_compression | FAIL | principal metadata/segments/DP |
| economic | AMBER | fixed principal setting |
| sparse_target_architecture | PASS | valid deepres_v2 target |
| cohort_locality | AMBER | random gain/oracle recovery/padding |
| null_controls | PASS | density and temporal/node nulls |
| robustness | PASS | rho=1.50 and fallback overhead |
| runtime_reproducibility | PASS | <=90m, tests, hashes, GPU record |
| phase1_decision | ITERATE_DELTA_ENCODING | predeclared logic |

## Null controls

| config_id | control_type | density | temporal_flip | metadata_reduction | proxy_speedup_rho1_25 | byte_ratio_to_best_baseline | window_cluster_gain_over_random |
| --- | --- | --- | --- | --- | --- | --- | --- |
| cora_gcnii16 | real | 0.7853391127428702 | 0.02690619614721812 | 0.3100412553410933 | 1.1860804759284782 | 0.8824747411750031 | 0.055002778980496325 |
| cora_gcnii16 | temporal_order | 0.7730509139586411 | 0.1034449432237814 | 0.14159420289855074 | 1.168093025960209 | 0.8894026587590782 | 0.04989420179614945 |
| cora_gcnii16 | density_matched_independent | 0.7851908696454948 | 0.3025939731043821 | 0.0 | 1.068779858492306 | 0.9201487474559662 | 0.0070920729245205205 |
| cora_gcnii16 | node_permutation | 0.7853391127428702 | 0.3016150064623338 | 0.0 | 1.090240606896243 | 0.9350879381314706 | 0.02713548937233279 |
| cora_gcnii16 | random_init | 0.9464611620838541 | 0.06150131939315608 | 0.1556943777030274 | 1.0290475802217378 | 1.008054837518464 | 0.001055109253172537 |
| pubmed_gcnii16 | real | 0.6742088655435957 | 0.022178870074047775 | 0.374807777739808 | 1.3805640193841477 | 0.8497024609360003 | 0.07675252747899974 |
| pubmed_gcnii16 | temporal_order | 0.6600774151357087 | 0.09591877409088603 | 0.17432105481668125 | 1.3725535354755949 | 0.856850946130209 | 0.06798887896549033 |
| pubmed_gcnii16 | density_matched_independent | 0.6741226089551773 | 0.38321348645838615 | 2.4080602593068434e-06 | 1.1982929963546283 | 0.9355110801184218 | 0.006927028200118146 |
| pubmed_gcnii16 | node_permutation | 0.6742088655435957 | 0.3828420192600294 | 2.445753194191269e-06 | 1.2227934375995055 | 0.8971397857718739 | 0.027774675007159688 |
| pubmed_gcnii16 | random_init | 0.9087945388789838 | 0.09092995310730165 | 0.19474847092563874 | 1.0898943473717178 | 0.9546964548359284 | 0.001652925335234201 |

## Sensitivity

The full bounded Cartesian sweep and all A0-A5 ablations are in
`13_phase1_sensitivity.csv`. Fixed-setting rho and window excerpts:

| config_id | parameter | value | tile_size | cohort_size | window_length | mask_decode_width_bits | rho_delta | proxy_speedup | byte_ratio | metadata_reduction |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| chameleon_gcnii16 | window_length | 1.0 | 128 | 32 | 1 | 64 | 1.25 | 1.257272922851025 | 0.8890953431657183 |  |
| chameleon_gcnii16 | window_length | 2.0 | 128 | 32 | 2 | 64 | 1.25 | 1.295639214995783 | 0.8748339292146556 |  |
| chameleon_gcnii16 | window_length | 4.0 | 128 | 32 | 4 | 64 | 1.25 | 1.2801664666179626 | 0.8687052882592229 |  |
| chameleon_gcnii16 | window_length | 8.0 | 128 | 32 | 8 | 64 | 1.25 | 1.3715462487027048 | 0.8745797142056598 |  |
| cora_deepres28_w128 | window_length | 1.0 | 128 | 32 | 1 | 64 | 1.25 | 1.7262811784138568 | 0.921929468990677 |  |
| cora_deepres28_w128 | window_length | 2.0 | 128 | 32 | 2 | 64 | 1.25 | 1.7309643662613765 | 0.9053106994028868 |  |
| cora_deepres28_w128 | window_length | 4.0 | 128 | 32 | 4 | 64 | 1.25 | 1.7316623325629688 | 0.8991421677293503 |  |
| cora_deepres28_w128 | window_length | 8.0 | 128 | 32 | 8 | 64 | 1.25 | 1.7211003608107678 | 0.8971486539552337 |  |
| cora_gcnii16 | window_length | 1.0 | 128 | 32 | 1 | 64 | 1.25 | 1.1767083658348505 | 0.9048135726967844 |  |
| cora_gcnii16 | window_length | 2.0 | 128 | 32 | 2 | 64 | 1.25 | 1.1880189611126615 | 0.8900277116168536 |  |
| cora_gcnii16 | window_length | 4.0 | 128 | 32 | 4 | 64 | 1.25 | 1.1860804759284782 | 0.8824747411750031 |  |
| cora_gcnii16 | window_length | 8.0 | 128 | 32 | 8 | 64 | 1.25 | 1.200385312936064 | 0.8777544197355757 |  |
| cora_resgcn16 | window_length | 1.0 | 128 | 32 | 1 | 64 | 1.25 | 1.784003029427091 | 0.7428729078535957 |  |
| cora_resgcn16 | window_length | 2.0 | 128 | 32 | 2 | 64 | 1.25 | 1.6822052222362225 | 0.7458573390724317 |  |
| cora_resgcn16 | window_length | 4.0 | 128 | 32 | 4 | 64 | 1.25 | 1.6392207701588004 | 0.842432332903701 |  |
| cora_resgcn16 | window_length | 8.0 | 128 | 32 | 8 | 64 | 1.25 | 1.6536623125720655 | 0.864429348439369 |  |
| pubmed_deepres28_w128 | window_length | 1.0 | 128 | 32 | 1 | 64 | 1.25 | 1.832146655212851 | 0.8890556785629402 |  |
| pubmed_deepres28_w128 | window_length | 2.0 | 128 | 32 | 2 | 64 | 1.25 | 1.8275516929186126 | 0.8740337915023486 |  |
| pubmed_deepres28_w128 | window_length | 4.0 | 128 | 32 | 4 | 64 | 1.25 | 1.8233623197963453 | 0.8703974232869098 |  |
| pubmed_deepres28_w128 | window_length | 8.0 | 128 | 32 | 8 | 64 | 1.25 | 1.8166969713731356 | 0.8677276239999749 |  |
| pubmed_gcnii16 | window_length | 1.0 | 128 | 32 | 1 | 64 | 1.25 | 1.362322843014454 | 0.8764130302661967 |  |
| pubmed_gcnii16 | window_length | 2.0 | 128 | 32 | 2 | 64 | 1.25 | 1.3824341516372802 | 0.8571152270601499 |  |
| pubmed_gcnii16 | window_length | 4.0 | 128 | 32 | 4 | 64 | 1.25 | 1.3805640193841477 | 0.8497024609360003 |  |
| pubmed_gcnii16 | window_length | 8.0 | 128 | 32 | 8 | 64 | 1.25 | 1.41152285030174 | 0.8404834665412945 |  |
| cora_gcnii16 | rho_delta | 1.1 | 128 | 32 | 4 | 64 | 1.1 | 1.2205430826559547 |  |  |
| cora_gcnii16 | rho_delta | 1.25 | 128 | 32 | 4 | 64 | 1.25 | 1.1860804759284782 |  |  |
| cora_gcnii16 | rho_delta | 1.5 | 128 | 32 | 4 | 64 | 1.5 | 1.1546508250215057 |  |  |
| cora_gcnii16 | rho_delta | 1.75 | 128 | 32 | 4 | 64 | 1.75 | 1.1360484819072667 |  |  |
| pubmed_gcnii16 | rho_delta | 1.1 | 128 | 32 | 4 | 64 | 1.1 | 1.4180507813162706 |  |  |
| pubmed_gcnii16 | rho_delta | 1.25 | 128 | 32 | 4 | 64 | 1.25 | 1.3805640193841477 |  |  |
| pubmed_gcnii16 | rho_delta | 1.5 | 128 | 32 | 4 | 64 | 1.5 | 1.339425830355559 |  |  |
| pubmed_gcnii16 | rho_delta | 1.75 | 128 | 32 | 4 | 64 | 1.75 | 1.3125165808010912 |  |  |

## Exact stream layout

Bytes are accounted in six cohort-window stream families, each aligned once to
64 bytes: regular feature IDs; regular values per layer; delta feature IDs;
delta initial masks; delta XOR transitions per transition; and delta active
values per layer. No feature is aligned independently. Delta transitions choose
exactly between a dense lane-bitmask and a counted list of flipped lane IDs.
Decoded support was checked bit-for-bit.

## Interpretation

Strongest positive signal: `cora_deepres28_w128` reached a rho=1.25 analytical
proxy of 1.732.

Strongest negative signal: `cora_gcnii16` reached only
1.186; failed gates remain visible above.

The dense SCALE-Sim run remains a callability smoke test and does not evaluate
MOSAIC-Delta. Every `proxy_speedup` value is an analytical proxy, not a measured
hardware speedup.
