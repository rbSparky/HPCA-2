# Final consumer-complete acceptance results

All 72,604 DELTA targets have explicit consumer sources; zero are unclassified. The final 16 KiB consumer-complete model charges 149.60 MB of consumer rereads in addition to 149.60 MB of producer rereads. **Every producer recovery completes before target encoding begins (0 violations across 73,652 audited target records).** Corrected trace-weighted geometric-mean aggregation-combination-subsystem speedup is **1.106x** and dataset-balanced geometric mean is **1.072x**. The range is **0.978x--1.272x**, with 1 regression. Complete-XORFLOW equals the final primary schedule on all ten checkpoints. Event and independent-recurrence layer cycles agree exactly (0% error) across all final rows. Seven independently trained depth-extension points were also rerun under this same producer- and consumer-complete model; see `depth_extension/DEPTH_EXTENSION_REPORT.md`. Newly inserted consumer-anchor requests were externally replayed with Ramulator2; see `MEMORY_TIMING_VALIDATION_REPORT.md`.

## Per-checkpoint corrected cycles

| Checkpoint | BEICSR cycles | XORFLOW cycles | Speedup |
|---|---:|---:|---:|
| flickr_deepres8_w128_s7 | 6,408,693 | 6,053,604 | 1.059x |
| ogbn_arxiv_deepres8_w128_s7 | 17,628,391 | 15,985,820 | 1.103x |
| ogbn_arxiv_deepres8_w128_s17 | 17,686,294 | 16,059,130 | 1.101x |
| ogbn_arxiv_deepres8_w128_s27 | 17,641,104 | 15,697,817 | 1.124x |
| reddit_deepres8_w128_s7_native | 885,385,652 | 695,839,191 | 1.272x |
| reddit_deepres8_w128_s17_native | 903,852,939 | 815,910,487 | 1.108x |
| reddit_deepres8_w128_s27_native | 904,043,194 | 837,095,335 | 1.080x |
| yelp_deepres8_w128_s7_balanced_fallback | 111,524,900 | 106,749,837 | 1.045x |
| ogbn_arxiv_deepres16_w128_s7 | 35,267,988 | 28,973,104 | 1.217x |
| chameleon_gcnii16 | 179,891 | 183,881 | 0.978x |
