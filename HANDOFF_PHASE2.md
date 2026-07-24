# MOSAIC-Anchor Phase-2 handoff

Decision: `ITERATE_ANCHOR_ENCODING`

Reproduce without training:

```bash
MOSAIC_PYTHON=/home/rishabh/miniconda/envs/taugat_pyg/bin/python \
  bash scripts/run_phase2.sh
```

Two corrected complete cached-trace runs produced identical hashes for all
eleven principal CSVs. All 24 Phase-0/1/2 tests pass. Phase-0 and Phase-1
evidence hashes remain unchanged.

The anchor economics, sparse deep target, schedule reuse, null controls,
exactness, and runtime gates pass. The global event coder and predecessor-chain
deployability gates fail. SCALE-Sim callability succeeds, but calibrated hybrid
combination estimates fail G8 because anchor feature coverage leaves the regular
GEMM K dimension close to dense and residual/decode costs then erase the
analytical advantage.

The evidence supports further depthwise-anchor encoding work, not a spatial-only
pivot, but does not yet justify Phase-3 aggregation and memory-system
implementation. See `results_phase2/PHASE2_RESULTS.md` and
`results_phase2/phase2_gates.csv`.

Raw datasets, Conda environments, and third-party Git history are intentionally
excluded from the handoff archive.
