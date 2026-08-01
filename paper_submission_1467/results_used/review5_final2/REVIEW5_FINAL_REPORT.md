# XORFLOW reviewer-5 correction results

All numbers below are modeled aggregation+combination-subsystem results, not end-to-end GNN speedups.

## Final common scheduler

Every producer-anchor read, target/consumer read, and output writeback contends in one persistent eight-channel resource. The model separates a 32-entry request queue from eight timing-active channel slots, uses deterministic physical-address striping, charges read/write turnaround, resumes dependents only on completion, and retains layer barriers. Combination service comes from the versioned 32x32 weight-stationary SCALE-Sim shape cache and is consumed once per executed record.

Coverage: **12 checkpoints**, including Flickr seeds 7, 17, and 27. Trace geomean: **1.086x**; dataset-balanced geomean: **1.065x**; range **0.975x–1.279x**; regressions: **3**.

| Checkpoint | BEICSR cycles | XORFLOW cycles | Speedup |
|---|---:|---:|---:|
| chameleon_gcnii16 | 413,986 | 416,618 | 0.994x |
| flickr_deepres8_w128_s17 | 46,271,863 | 46,455,417 | 0.996x |
| flickr_deepres8_w128_s27 | 46,256,780 | 47,454,167 | 0.975x |
| flickr_deepres8_w128_s7 | 46,213,044 | 43,803,355 | 1.055x |
| ogbn_arxiv_deepres16_w128_s7 | 235,409,946 | 192,896,707 | 1.220x |
| ogbn_arxiv_deepres8_w128_s17 | 117,773,363 | 107,576,129 | 1.095x |
| ogbn_arxiv_deepres8_w128_s27 | 117,893,069 | 105,498,473 | 1.117x |
| ogbn_arxiv_deepres8_w128_s7 | 118,054,997 | 107,599,087 | 1.097x |
| reddit_deepres8_w128_s17_native | 6,073,413,354 | 5,467,747,091 | 1.111x |
| reddit_deepres8_w128_s27_native | 6,073,613,917 | 5,615,099,894 | 1.082x |
| reddit_deepres8_w128_s7_native | 5,949,006,307 | 4,650,397,803 | 1.279x |
| yelp_deepres8_w128_s7_balanced_fallback | 740,915,129 | 708,134,575 | 1.046x |

## Held-out absolute external-memory validation

The HBM timing scale is fitted only on Flickr seed 7 and then frozen. Flickr seed 17 is a held-out absolute Ramulator2 completion-time comparison; its external completion is not used during calibration.

| Case | Internal cycles | Ramulator2 cycles | Error | Requests |
|---|---:|---:|---:|---:|
| flickr_s7 | 4,004,721 | 4,004,721 | 0.00% | 17,438,504 |
| flickr_s17 | 4,064,919 | 4,083,428 | 0.45% | 17,723,938 |

## Hardware and ablation scope

The complete variable-length RTL source and the unbounded Yosys log are included. Tile-scale event discovery/packing and routed consumer evidence remain valid. The archive does not invent full-packer PPA if global elaboration has not completed.
Non-complete variants are restricted to exact common-accounting byte attribution in `results/ablation_bytes_only.csv`. No legacy cycle estimate is used for performance attribution; complete XORFLOW alone is replayed through the corrected final scheduler.
