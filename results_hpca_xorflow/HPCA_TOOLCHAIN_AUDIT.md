# HPCA XORFLOW toolchain audit

Generated 2026-07-28. This is an implementation audit, not a claim of
full-chip measured hardware performance.

| Component | Status | Evidence |
|---|---|---|
| CUDA decoder microbenchmark | queued on GPU-1 | `scripts/run_xorflow_cuda_bench.py`; output `results_hpca_xorflow/cuda_microbench.csv` |
| SCALE-Sim | available and exercised | `HPCA_HARDWARE_AUDIT.md`, `artifacts_hpca_xorflow/scalesim/` |
| RTL synthesis/formal | passed | `artifacts_safezone/decoder/{lane,bank}_synthesis.log`, `formal*.log` |
| DRAMsim3 | built locally and tiny trace completed | `tools/vendor/DRAMsim3/build/dramsim3main`, `artifacts_hpca_xorflow/dramsim3/tiny.log` |
| Ramulator2 | existing Arxiv request/served runs passed | `results_hpca_xorflow/03_ramulator_pairs.csv` |
| CACTI | source checkout available; numeric run pending | `tools/vendor/cacti/` |
| Verilator | installed and lint passed | Verilator 5.020; `artifacts_safezone/decoder/verilator_lint.log` |
| Yosys | installed; synthesis/formal passed | Yosys 0.33; lane 1,663 cells/path 33, bank 53,312 cells/path 35 |
| OpenROAD | not installed | no executable found; no fabricated PPA numbers |

DRAMsim3 is used as an independent timing cross-check with its available
DDR4 configuration; this is not HBM2 timing. CACTI/OpenROAD numbers are not
reported until the tools are actually callable. The remaining PPA evidence is
therefore logic synthesis/formal plus the exact limitation record above.

The post-install RTL command was:

```bash
verilator --lint-only -Wall -Wno-fatal rtl/xorflow_decoder.sv
scripts/synth_decoder.sh
```
