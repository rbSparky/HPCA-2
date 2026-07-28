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
| CACTI | verified Docker wrapper and numeric smoke | image `local/cacti-hp:7.0`; wrapper `~/.local/bin/cacti`; source revision recorded in `artifacts_hpca_xorflow/cacti/` |
| Verilator | installed and lint passed | Verilator 5.020; `artifacts_safezone/decoder/verilator_lint.log` |
| Yosys | installed; synthesis/formal passed | Yosys 0.33; lane 1,663 cells/path 33, bank 53,312 cells/path 35 |
| OpenROAD/ORFS | verified in Docker | `openroad/orfs:latest`, version `26Q3-771-g7cfb2105c9`; Nangate45 GCD RTL-to-GDS artifacts present |

DRAMsim3 is used as an independent timing cross-check with its available
DDR4 configuration; this is not HBM2 timing. CACTI/OpenROAD numbers are not
reported until the tools are actually callable. The remaining PPA evidence is
therefore logic synthesis/formal plus the exact limitation record above.

OpenROAD is intentionally container-only. The verified invocation is:

```bash
cd ~/src/OpenROAD-flow-scripts/flow
util/docker_shell openroad -version
```

The completed reference flow is under
`~/src/OpenROAD-flow-scripts/flow/results/nangate45/gcd/base/` and contains
`6_final.gds`, `6_final.def`, `6_final.odb`, and `6_final.v`. This establishes
that the ORFS runtime is callable; it is not yet a routed XORFLOW decoder,
which remains a bounded next step.

The post-install RTL command was:

```bash
verilator --lint-only -Wall -Wno-fatal rtl/xorflow_decoder.sv
scripts/synth_decoder.sh
```

CACTI is now run through a fixed Docker image to preserve its relative
`tech_params/` working directory. Source revision:
`1ffd8dfb10303d306ecd8d215320aea07651e878`. Image digest:
`sha256:b997b6de63858b2b4efa68ef9ea889290984d3a7d4ef43abb0caae4216342c1c`.
The default configuration and an unrelated-directory wrapper invocation both
pass. The default smoke reports access time 1.47098 ns, cycle time 1.86851 ns,
dynamic read energy 0.303592 nJ, and data/tag area 1.78124/0.108777 mm².
These are CACTI model outputs, not measured silicon.

## Actual XORFLOW RTL route

The 32-lane bank synthesized successfully (71,359 instances, approximately
100,599 um²), but its unwrapped top-level interface has 8,577 pins and the
Nangate45 perimeter cannot place that many pins. This is recorded as a
physical-integration constraint, not hidden.

The physically legal single-lane XORFLOW top was then routed through the full
ORFS Nangate45 flow. Final artifacts are under
`artifacts_safezone/openroad/xorflow_decoder_lane/`:

- synthesis: 2,373 initial instances; final routed design area 4,150 um²;
- detailed route DRC: 0 violations after routing optimization;
- final GDS/DEF/ODB/SPEF/Verilog: present;
- extracted final power report: 25.7 mW at the flow's 1.1 V corner;
- final routed timing at a 1.0 ns constraint: WNS −0.17 ns, TNS −2.56 ns.

Thus the lane is routable and electrically clean, but this unmodified
three-stage combinational prefix lane does not close a 1 GHz timing target;
its measured route requires roughly 1.17 ns or slower. The bank remains a
logic-synthesis/formal result until a hierarchical physical top is defined.

CACTI support-cache sweep (45 nm model) also passes through the Docker
wrapper: 16 KiB = 0.969 ns / 0.1915 nJ, 32 KiB = 1.010 ns / 0.2069 nJ, and
64 KiB = 1.126 ns / 0.2377 nJ access/cycle-energy points. These are modeled
SRAM estimates, not silicon measurements.
