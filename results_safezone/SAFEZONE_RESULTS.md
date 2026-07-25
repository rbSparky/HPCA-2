# XORFLOW safe-zone validation

Decision: `SAFE_ZONE_PROCEED_TO_PAPER_READY_XORFLOW_SUITE`

## Outcome

The deployable, selector-equipped project has moved beyond the earlier fragile
roofline result. The final
candidate uses exact FP8 values, a fixed-gap8 event stream, 32 parallel
64-bit decoder lanes, double-buffered support reconstruction, and a
channel-colored odd cache-line row stride. It performs no padded MACs and every
support decode remains exact.

The overlooked failure was physical address coloring: a 128-byte row stride
placed one-line Cora rows on only half of the HBM channel groups. A minimal
192-byte reserved stride cycles row starts across every channel group. The
extra tail is capacity overhead only and is explicitly retained; it is not
fetched. This changes no support, value, or baseline semantics.

## Real HBM2 timing

```text
          config_id  seed  beicsr_hbm_cycles  xorflow_hbm_cycles  xorflow_decode_cycles  descriptor_cycles_each  hbm_only_speedup  serialized_speedup  double_buffered_speedup  all_requests_drained
cora_deepres28_w128     7              15515               13466                   1067                    1190          1.152161            1.062456                 1.139806                  True
cora_deepres28_w128    17              14808               12753                    958                    1190          1.161139            1.073619                 1.147386                  True
cora_deepres28_w128    27              14850               12031                    933                    1190          1.234311            1.133249                 1.213221                  True
       cora_gcnii16     7               6867                6437                    234                     680          1.066801            1.026663                 1.060419                  True
       cora_gcnii16    17               6588                6354                    224                     680          1.036827            1.001378                 1.033267                  True
       cora_gcnii16    27               6577                6404                    217                     680          1.027014            0.993973                 1.024421                  True
     pubmed_gcnii16     7             142991              119008                   1509                    4932          1.201524            1.179148                 1.193505                  True
     pubmed_gcnii16    17             160372              126196                   1585                    4932          1.270817            1.245575                 1.260631                  True
     pubmed_gcnii16    27             154922              122798                   1401                    4932          1.261600            1.237921                 1.251499                  True
```

Against an equally channel-colored BEICSR baseline, across three independently
trained seeds, double-buffered aggregation-memory speedup is 1.024–1.060x on
Cora, 1.194–1.261x on PubMed, and 1.140–1.213x on DeepRes. The valid
169K-node/2.32M-edge OGBN-Arxiv run reaches 1.398x
(1.390x fully serialized). These are
aggregation-memory results, not end-to-end GNN speedups.

## Clean scale and learned-structure validation

At fixed width 128, using induced subgraphs from the same trained Arxiv model,
the identical cache/roofline model progresses from
1.058x at
4,096 nodes to
1.189x at
16,384,
1.284x at
65,536, and
1.353x at
169,343. This isolates graph scale from model and feature
width. It supports an overhead-amortization claim, not a claim that graph size
alone creates learned structure.

```text
 nodes   edges  density  support_ratio_to_beicsr  roofline_serialized_speedup  roofline_double_buffered_speedup  exactness_pass           evidence_type
  4096    5930 0.459467                 0.697461                     0.884011                          1.057910            True fixed_model_graph_scale
 16384   26086 0.462226                 0.702441                     1.011126                          1.189015            True fixed_model_graph_scale
 65536  215658 0.466311                 0.706287                     1.169766                          1.283855            True fixed_model_graph_scale
169343 2315598 0.472346                 0.694812                     1.318343                          1.353139            True fixed_model_graph_scale
```

At full scale, a density-matched independent null requires
1.79x
the exact support bits of the trained trace. Thus the large-graph gain combines
scale with learned spatial/temporal dependence; it is not explained by density
alone.

This gives two separate, controlled findings:

1. **Scale effect:** with the trained model, feature width, format, cache, and
   cost model fixed, larger induced graphs monotonically improve amortization.
2. **Learned-structure effect:** at essentially identical density on the full
   graph, destroying dependence increases exact support metadata by
   79.0%.

The defensible paper claim is therefore that benefit grows with graph scale
*and* relies on learned support dependence. The experiment does not claim that
node count itself causes learnability.

## Decoder evidence

```text
                     module  generic_cells  longest_gate_path  formal_properties_passed
       xorflow_decoder_lane           1663                 33                         4
xorflow_decoder_bank_32lane          53344                 35                         4
```

The hardware-constrained code sustains
2005–
2040 encoded bits/cycle on
real streams. Four structural SAT proofs pass. A 10,000-vector randomized
parallel-prefix equivalence test and the complete 58-test regression suite
also pass. Generic Yosys cells are a reproducible complexity proxy, not a
post-layout area or timing claim.

## Robustness

The Cora/PubMed geometric mean remains above the deployment threshold across
256 KiB, 512 KiB, and 1 MiB feature caches and across 128, 256, and 512
B/cycle injection. The selector falls back to BEICSR on any window where
XORFLOW is not cheaper.
Maximum FP8 accuracy loss over the evaluated seeds is
0.300 percentage points. Density-matched
independent masks require at least 1.57x the real support
metadata, so the coding benefit is not density alone.

## Gates

```text
                                gate                                         status
          SZ_G1_EXACTNESS_REGRESSION                                           PASS
         SZ_G2_SYNTHESIZABLE_DECODER                                           PASS
     SZ_G3_STRICT_UNIVERSAL_WORKLOAD                                           FAIL
       SZ_G4_DEPLOYABLE_SELECTOR_HBM                                           PASS
          SZ_G5_SERIALIZED_GUARDRAIL                                           PASS
SZ_G6_CACHE_AND_BANDWIDTH_ROBUSTNESS                                           PASS
  SZ_G7_FP8_ACCURACY_AND_LARGE_MODEL                                           PASS
             SZ_G8_LEARNED_STRUCTURE                                           PASS
                SZ_G9_DRAM_INTEGRITY                                           PASS
                   SAFEZONE_DECISION SAFE_ZONE_PROCEED_TO_PAPER_READY_XORFLOW_SUITE
```

## Interpretation and next action

The strict universal-workload gate fails because Cora remains a small,
overhead-dominated regime; that failure is deliberately retained above. The
exact selector makes the deployed format non-regressive, while PubMed,
DeepRes, and Arxiv provide substantial repeatable margin. In particular,
Arxiv's real-HBM2 1.398x result and the monotone fixed-model scale sweep move
the project beyond a Cora-centric fragile result. This is now promising enough
for a paper-ready memory-system suite. The claim
should remain narrow: exact support compression and channel-balanced feature
traffic improve the memory-dominated aggregation path. The next work is larger
graphs, additional operators, decoder post-layout area/energy, full-system
write/compaction traffic, normalized accelerator baselines, and projected
end-to-end results. Do not revive the stopped dense regular-path claim.
