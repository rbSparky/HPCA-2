# Remaining HPCA-suite work plan (live)

## Completed / verified

- Causal XORFLOW principal traces and null controls: complete.
- Arxiv (two seeds), Reddit, Flickr, and borderline Yelp temporal/host runs: complete.
- Existing Ramulator2 Arxiv request/served validation: complete.
- SCALE-Sim regular-path calibration: complete, explicitly not end-to-end aggregation.
- RTL lane/bank synthesis and formal checks: complete; no physical PPA claim.
- DRAMsim3 independent timing: built locally; reproducible 64-request DDR4 smoke passes.
- CUDA decoder benchmark: implemented and queued on GPU-1.

## Running now (GPU-1, serialized and logged)

1. Remaining paper sensitivity/reproducibility queue.
2. CUDA microbenchmark (100 CUDA-event repetitions per primitive/shape).
3. GraphSAGE-8 and GIN-8 Flickr smoke training to validate expanded operator plumbing.

## Explicit limitations (not hidden)

- CACTI legacy binary builds but currently faults on its stock cache invocation;
  no SRAM energy/area values are fabricated. The source, command, and failure
  log are retained.
- OpenROAD/Verilator are not installed in the current environment. RTL logic
  synthesis/formal remains valid; place-route and post-route PPA require those
  tools or a separate tool container.
- Large-graph GraphSAGE/GIN full-neighbor support capture needs a generic CSR
  inference kernel; the current exact CSR path is DeepRes-specific. The smoke
  jobs validate model construction/training only and cannot satisfy the hard
  expanded-model gate by themselves.

All queued work is bounded to GPU-1; GPU0 is not used. Every run has a separate
job directory, stdout log, and artifact path. No prior phase output is modified.
