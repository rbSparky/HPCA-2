# Complete Ramulator2 scope

Two complete causal online-replay traces were emitted from the frozen
`memory_transactions_*_finite_retention.csv` files and run through the pinned
HBM2 model at one frontend request per memory cycle.  The exact trace hashes,
request counts, drain setting, and JSON statistics are in:

- `ramulator_complete_arxiv_s7.json`
- `ramulator_complete_reddit_s7.json`

The Ramulator frontend reports reads forwarded between controllers separately
from reads served by the source controller.  `accounted_requests = served +
forwarded` is therefore the integrity check.  Both complete runs account for
every submitted 32-byte request.  The external Ramulator binding was rebuilt
with an opt-in `RAMULATOR_DRAIN_CYCLES` setting (default remains 4096, so old
pair evidence is unchanged); complete runs use 1,000,000 drain cycles.  No
unserved request is treated as a successful timing result.

This is complete online-replay timing for XORFLOW, not a fabricated baseline
comparison or a claim of full end-to-end GNN timing.  The existing pair
BEICSR/XORFLOW comparisons remain separately labelled in
`ramulator2_summary.csv`.
