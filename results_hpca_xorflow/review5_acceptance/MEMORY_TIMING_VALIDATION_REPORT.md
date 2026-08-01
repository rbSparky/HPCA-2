# Consumer-complete external memory timing validation

The added consumer-anchor reads were replayed externally rather than inferred from logical bytes. For Arxiv, Reddit, and Yelp the retained complete layer-4 producer stream is extended with every exact pair-4 consumer-anchor reread; Flickr uses its complete layers-4/5 stream. This conservative ordering prevents the new traffic from hiding behind the producer-complete stream.

| Case | Scope | Producer cycles | Consumer-complete cycles | Added timing |
|---|---|---:|---:|---:|
| Flickr | 250k representative | 61,510 | 61,822 | 0.507% |
| Reddit | 250k representative | 84,903 | 85,241 | 0.398% |
| Yelp | 250k representative | 102,049 | 102,387 | 0.331% |

## Complete retained-stream replay

| Case | Producer cycles | Consumer-complete cycles | Added | Prediction error | BEICSR | Speedup |
|---|---:|---:|---:|---:|---:|---:|
| arxiv_s17_pair4 | 5,812,871 | 5,828,767 | 0.273% | 0.561% | 6,620,974 | 1.136x |
| flickr_pair4 | 997,345 | 1,003,722 | 0.639% | 0.539% | -- | -- |
| reddit_pair4 | 182,454,816 | 182,480,018 | 0.014% | 0.016% | 284,762,277 | 1.561x |
| yelp_pair4 | 40,969,413 | 41,036,366 | 0.163% | 0.439% | 44,026,457 | 1.073x |

- Maximum internal/external completion prediction error is **0.561%**, below the predeclared 5% tolerance.

Ramulator2 supplies timing completion. DRAMsim3 independently confirms complete service for the representative real/adversarial streams and the complete 16,382,812-request Arxiv consumer stream; its fixed-duration driver is not misreported as a completion-time measurement. Two distinct mappings were exercised. Transient multi-hundred-megabyte traces are excluded from the bundle; their SHA-256 manifests and raw tool JSON/logs are retained.
