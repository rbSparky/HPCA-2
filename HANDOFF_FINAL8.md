# MOSAIC FP8-XORFLOW final kill-test handoff

Decision: `SAVE_MOSAIC_WITH_FP8_XORFLOW_PARALLEL_DECODE`.

The regular-panel and FP32 memory-format directions remain stopped. The saved
direction is specifically:

> FP8 activation values, topology-tile XORFLOW support anchors and exact
> exceptions, 32 independent 64-bit tile decoders (2,048 aggregate bits/cycle),
> and a selector that falls back to BEICSR.

At a 512 KiB 16-way feature cache, conservative serialized
aggregation-memory speedups versus independently optimized FP8 BEICSR are:

- Cora GCNII: 1.059x
- PubMed GCNII: 1.138x
- valid Cora DeepRes-28: 1.148x
- Chameleon: 1.000x through BEICSR fallback

Traffic reductions before decoder cost are 10.7%, 15.9%, and 22.6% on the three
benefiting models. FP8 test-accuracy loss is only 0.1--0.22 percentage points.
Matched-density and node-permuted controls require 1.56x--2.94x as many support
bits, so density alone does not explain the result.

The original single 64-bit decoder fails and remains visible in the tables.
The parallel decoder is plausible because tile reconstruction is independent
and 2,048 bits/cycle matches the declared 256-byte/cycle HBM interface, but its
area, energy, bank conflicts, and RTL throughput are not measured. Those are
the next mandatory checks before paper claims.

Reproduce:

```bash
bash scripts/run_final8.sh
```

The run uses the existing Conda environment and cached checkpoints; it does not
retrain. Results are in `results_final8/FINAL8_RESULTS.md`. Two complete
cached runs produced identical principal CSV hashes, and 54 tests pass.
