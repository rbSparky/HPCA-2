# Extended overnight GPU-1 queue

Submitted 2026-07-28 UTC after the principal suite completed. The queue is
serialized by `tools/remote_xorflow.sh`; GPU0 is not used. Every job has an
isolated remote job directory and stdout log.

| Order | Job | Work |
|---:|---|---|
| 1 | `20260728T203208Z_6138` | Arxiv s17, cache 256 KiB, slice 64, source-tiled, 4 pairs |
| 2 | `20260728T203209Z_29251` | Arxiv s27, cache 1 MiB, slice 256, O0, 4 pairs |
| 3 | `20260728T203210Z_1276` | Reddit, cache 256 KiB, slice 96, source-tiled, 4 pairs |
| 4 | `20260728T203211Z_23032` | Reddit, cache 1 MiB, slice 256, O0, 4 pairs |
| 5 | `20260728T203211Z_5110` | Flickr, cache 256 KiB, slice 64, source-tiled, 4 pairs |
| 6 | `20260728T203212Z_20561` | PubMed GCNII, 4 pairs |
| 7 | `20260728T203213Z_17967` | Cora GCNII, 4 pairs |
| 8 | `20260728T203221Z_10079` | PubMed GraphSAGE-8 operator smoke/trace |
| 9 | `20260728T203221Z_15598` | PubMed GIN-8 operator smoke/trace |
| 10 | `20260728T203222Z_8125` | Flickr GraphSAGE-8 operator smoke/trace |
| 11 | `20260728T203223Z_3482` | Flickr GIN-8 operator smoke/trace |

The operator jobs use 60 epochs and are supplementary validation; they do not
replace the hard-valid DeepRes traces. Large-graph GraphSAGE/GIN jobs are not
queued because the exact large-graph CSR inference backend is intentionally
DeepRes-specific and would otherwise risk invalid support traces.

Expected serialized duration is approximately 4–7 hours depending on cache
reuse and graph I/O. Partial outputs are valid and retained if the queue is
still running at the deadline.
