# Consumer-complete depth extension

These are independently trained depth points rerun with the final producer- and consumer-complete model. Producer recovery is a prerequisite of target encoding; the distinct 16 KiB consumer decoded-anchor LRU rereads and achieved decode service are charged in the same finite memory/decoder resources as target traffic.

| Dataset | Depth | FP8 quality | Validity | BEICSR cycles | XORFLOW cycles | Final speedup | Preview | Consumer reread | Recurrence |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| Arxiv | 24 | 67.21% accuracy | BORDERLINE (<0.68 floor) | 52,771,890 | 42,137,137 | **1.252x** | 1.266x | 32.51 MB | 0.0% |
| Arxiv | 32 | 66.70% accuracy | BORDERLINE (<0.68 floor) | 70,512,648 | 53,661,638 | **1.314x** | 1.328x | 42.95 MB | 0.0% |
| Flickr | 16 | 47.34% accuracy | VALID | 12,847,687 | 13,100,054 | **0.981x** | 0.992x | 10.06 MB | 0.0% |
| Reddit | 12 | 95.46% accuracy | VALID | 1,302,404,272 | 1,000,483,688 | **1.302x** | 1.302x | 21.63 MB | 0.0% |
| Reddit | 16 | 95.60% accuracy | VALID | 1,707,975,725 | 1,290,225,500 | **1.324x** | 1.324x | 28.64 MB | 0.0% |
| Yelp | 12 | 45.90% micro-F1 | VALID | 166,749,577 | 151,814,604 | **1.098x** | -- | 70.84 MB | 0.0% |
| Yelp | 16 | 37.99% micro-F1 | INVALID_DIAGNOSTIC | 223,386,860 | 212,806,999 | **1.050x** | -- | 92.87 MB | 0.0% |

## Interpretation

- **Strong positive depth evidence:** Arxiv reaches 1.252x/1.314x at depths 24/32. Reddit reaches 1.302x/1.324x at depths 12/16.
- **Not universal:** Flickr-16 is a valid negative control at 0.981x. Yelp-12 is valid and positive at 1.098x, while Yelp-16 is an invalid-quality diagnostic and cannot support a paper gate.
- **Final-model impact is small but real:** producer-before-encode ordering and the separate consumer lifecycle lower the Arxiv-24 preview from 1.266x to 1.252x, so only the final column should be cited.
- All DELTA targets are classified, every recovered producer anchor is ready before encoding, and event-scheduler versus recurrence error is exactly zero for every depth point.

These are modeled aggregation-combination-subsystem speedups, not measured end-to-end GNN speedups.
