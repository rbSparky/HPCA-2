# XORFLOW: Paper-Ready Memory-Subsystem Plan

**Revision:** 2026-07-29 13:48 IST  
**Hard deadline:** **2026-07-31 23:59 IST** (`2026-07-31 18:29 UTC`)  
**Compute policy:** cluster **GPU 1 only**; GPU 0 is never selected or probed by a job.  
**Scientific scope:** causal, independently decodable XORFLOW activation-support streaming for the memory-dominated GNN aggregation path. This plan does **not** revive the stopped dense-panel / depthwise-regular-GEMM direction.

## 1. Goal and non-negotiable claims

The submission-quality result must demonstrate, under a common host, precision, cache, graph ordering, and HBM model, that deployable causal XORFLOW improves over a faithful SGCN-style sliced BEICSR baseline because learned support has temporal and topology-local spatial structure.

The deployable headline design is fixed before the runs:

- two-layer causal anchor: completed support at layer `l` anchors layer `l+1`;
- 128-row topology tile, four fixed 32-row cohorts;
- minimum legal anchor encoding selected between independent rows (A0) and cohort-prototype dictionary (A2);
- exact exception selector among dense XOR bitmap, fixed IDs, and block-FOR gaps (`B=8`, restart for gaps >255);
- FP8 E4M3 activation storage, FP16 weights, FP32 accumulation; every baseline uses the same numerical contract;
- 128-wide feature slice, 512 KiB / 16-way feature cache, O0 destination CSR edge order, 16 KiB support cache, 32 decoder lanes as the principal configuration;
- exact fallback to the best independent row-slice format whenever causal XORFLOW does not win for a tile/slice.

The offline future-majority anchor and free-support format are upper bounds only. They must never appear as deployable results.

All reported speedups must state their category:

1. **exact bytes / exact cache-line traffic**;
2. **Ramulator2 or DRAMsim3 timing**;
3. **modeled aggregation-memory or modeled host speedup**;
4. **Amdahl projection**.

None is an end-to-end measured accelerator speedup.

## 2. Current evidence and remaining gap

Completed positive evidence (all causal/deployable, matched BEICSR comparison):

| Workload | Quality | Modeled host geomean | Full Ramulator pair |
|---|---:|---:|---:|
| OGBN-Arxiv DeepResV2-8 seed 17 | 0.6828 accuracy | 1.210× | 1.139× |
| OGBN-Arxiv DeepResV2-8 seed 27 | 0.6866 accuracy | 1.253× | — |
| Reddit DeepResV2-8 | 0.9534 accuracy | 1.691× | 1.561× |
| Flickr DeepResV2-8 | 0.4723 accuracy | 1.052× | — |
| Yelp DeepResV2-8 | 0.4340 micro-F1 | 1.076× | 1.075× |

Yelp is **BORDERLINE**, not a hard-valid workload under the predeclared `0.45` floor. It may be shown as supplementary evidence but cannot satisfy a hard gate unless the one permitted validation-only recovery run passes.

The current causal case runner compares causal XORFLOW against a BEICSR layout. The paper suite still needs the full baseline matrix, traffic/timing nulls, causal ablations, full PPA/energy tables, and a clean final gate report.

## 3. Single source of truth for results and logging

All paper-suite evidence is consolidated under:

```text
results_hpca_xorflow/complete_suite/
├── HPCA_PAPER_EVIDENCE.md          # canonical reviewer-facing result file
├── HPCA_PAPER_EVIDENCE.csv         # one row per metric/configuration/run
├── HPCA_PAPER_GATES.csv            # every predeclared gate and evidence path
├── HPCA_PAPER_MANIFEST.json         # commands, versions, hashes, status
├── PAPER_SUITE_HOST_RESULTS.md      # existing raw host sub-report
├── runs/<run_id>/                  # immutable per-run CSVs
├── baselines/<run_id>/             # full format-matrix results
├── ablations/<run_id>/             # causal and hardware ablations
├── controls/<run_id>/              # matched-density/null outputs
├── timing/<run_id>/                # Ramulator/DRAMsim3 data
├── ppa/<run_id>/                   # CACTI/Yosys/OpenROAD outputs
└── reproduction/<run_id>/          # rerun hashes and diff reports

artifacts_hpca_xorflow/complete_suite/
├── commands/<task_id>.sh
├── logs/<task_id>.log
├── manifests/<task_id>.json
├── traces/<task_id>/               # content-addressed; delete raw chunks only after hash/stats persist
└── failures/<task_id>.txt
```

`HPCA_PAPER_EVIDENCE.md` is the only file a reviewer needs to open first. Every table row includes the relative result path, source run ID, SHA-256, validity class, and whether the number is measured, simulated, or modeled. `HPCA_RESULTS_INDEX.md` remains append-only operational history; it is not the final scientific summary.

Before queueing experiments, implement `scripts/build_hpca_paper_evidence.py` to consume the listed subdirectories and write the four canonical files above. It must fail loudly on a missing required row, a duplicate primary row, a nonmatching configuration, or a mismatched rerun hash.

## 4. Machine allocation

### Cluster: GPU 1 / remote host only

Use `/home/Rishabh@MLL-5090/envs/gpu-test` through the safe wrapper:

```bash
cd /home/rishabh/HPCA2/mosaic_delta_phase1
tools/remote_xorflow.sh submit \
  "MOSAIC_PY=python PYTHONPATH=src python -m mosaic_validation.hpca_campaign --config configs/<campaign>.yaml"
```

The wrapper serializes jobs with the GPU-1 lock, writes `.xorflow_jobs/<id>/`, mirrors source without deleting remote results, and does not set `CUDA_VISIBLE_DEVICES=0` anywhere. High-memory training, full graph traffic, Ramulator traces, and DRAMsim3 samples run here.

### Local RTX 4060 / CPU

Use the existing `taugat_pyg` environment only for low-compute or tool-chain work:

- unit tests, small synthetic equivalence checks, report generation, and hash audits;
- CUDA decoder/BEICSR microbenchmarks (100+ repetitions, median/p5/p95);
- CACTI 7 wrapper runs for SRAM configurations;
- Verilator/Yosys co-simulation and synthesis;
- OpenROAD only through `~/src/OpenROAD-flow-scripts/flow/util/docker_shell`;
- figure generation, linting, packaging, and documentation.

Local work must never launch new public-dataset model training or multi-million-edge trace simulation while GPU 1 is available.

## 5. Execution order and deadline budget

The deadline leaves roughly **58 hours** from this revision. The remote queue is serial by design. The budget below reserves 12 hours for remediation, reruns, and report assembly.

| Block | Owner | Budget | Finish target (IST) | Exit criterion |
|---|---|---:|---|---|
| A. Common-format harness + smoke | local + GPU1 | 5 h | Jul 29 19:00 | all formats round-trip; one Arxiv pair executes |
| B. Quality/trace closure | GPU1 | 5 h | Jul 30 00:00 | Yelp recovery attempted; required traces validated |
| C. Baseline matrix | GPU1 | 11 h | Jul 30 11:00 | all named baselines on Arxiv/Reddit/Yelp pairs |
| D. Controls + ablations | GPU1 | 10 h | Jul 30 21:00 | causal/structure claims tested at traffic level |
| E. Timing / PPA / energy | GPU1 + local | 10 h | Jul 31 07:00 | Ramulator, DRAMsim3, CACTI, RTL evidence complete |
| F. Sensitivity + workload breadth | GPU1 | 8 h | Jul 31 15:00 | required robustness rows complete |
| G. Reproduction, gates, figures, archive | local + GPU1 | 5 h | Jul 31 20:00 | two reruns match, final evidence file passes audit |
| H. Reserved repair margin | both | 3 h 59 m | Jul 31 23:59 | only targeted defect fixes / no scope expansion |

If a block overruns, preserve its partial CSV/log, stop secondary sensitivity first, and never drop primary Arxiv/Reddit, hard correctness, baseline matrix, controls, or final gate reporting.

## 6. Block A — common baseline harness (must precede new data)

Implement one `format_matrix` interface with exactly the same:

- node ordering, slice layout, address generator, 64-byte cache line and cache policy;
- FP8 support/value representation and value quantization;
- topology, descriptor, output, writeback, and metadata traffic accounting;
- causal fallback selector and run manifest.

Required formats:

| ID | Format | Deployable |
|---|---|---|
| B0 | dense row-major FP8 | yes |
| B1 | CSR with 32-bit feature IDs | yes |
| B2 | packed CSR with minimum legal feature-ID width | yes |
| B3 | faithful sliced BEICSR `C={64,96,128}` | yes |
| B4 | independently best exact row-slice choice (dense/CSR/BEICSR) | yes |
| X0 | XORFLOW independent anchor rows (A0) | yes |
| X1 | causal XORFLOW cohort-prototype dictionary (A2; principal) | yes |
| X2 | causal X1 with exact fallback disabled | diagnostic only |
| O0 | offline future-majority anchor | no — oracle |
| O1 | free-support packed values | no — oracle |

`BEICSR96` is the named SGCN-style baseline. `B3-best` is the strongest baseline for scientific gates. No format may receive different ordering, cache capacity, bandwidth, precision, or channel mapping.

**Smoke command (GPU1):** run B0/B3/X1/O0/O1 for Arxiv seed 17, pair 4→5, then assert exact support/value reconstruction, cache-line enumeration agreement, and identical aggregation output on a synthetic graph. Record in `baselines/smoke_arxiv_l4/`.

## 7. Block B — model and trace closure

### Required principal workloads

| Workload | Required state | Current status | Action |
|---|---|---|---|
| Arxiv DeepResV2-8, seeds 7/17/27 | hard-valid | complete | preserve; use all three for confidence intervals |
| Reddit DeepResV2-8 seed 7 | hard-valid | complete | preserve |
| Yelp DeepResV2-8 seed 7 | hard-valid target | borderline | perform one permitted validation-only fallback; otherwise report supplementary only |
| Flickr DeepResV2-8 seed 7 | transfer | complete | preserve |
| PubMed GCNII / available seed traces | transfer | existing Phase traces | convert through common format matrix; no retraining |
| Cora/Citeseer/Chameleon | boundary/negative | complete traces | convert through common format matrix |

### Operator and scaling diagnostics

Arxiv depth `4/8/16`, widths `64/128/256`, and GraphSAGE-8/GIN-8 are descriptive transfer experiments. GraphSAGE/GIN must meet the same declared quality floor before appearing in a positive cross-operator claim; otherwise they remain visible negative rows.

For every trace write `quality.json`, `fp8_supports.npz` hash, quantization accuracy delta, model checkpoint hash, and exact inference command before scheduling format evaluation.

## 8. Block C — baseline experiment matrix

Run the following compact but paper-sufficient matrix. A “pair” means two causal layers (`4→5`, `6→7` for 8-layer models); all pair-level outputs are retained before aggregation.

| ID | Configurations | Formats | Pair scope | Required outputs |
|---|---|---|---|---|
| BASE-1 | Arxiv seeds 7/17/27 | B0–B4, X0–X2, O0–O1 | 4→5, 6→7 | bytes, cache lines, support bits, serialized/overlapped cycles |
| BASE-2 | Reddit seed 7 | B0–B4, X0–X2, O0–O1 | 4→5, 6→7 | same |
| BASE-3 | Yelp hard-valid if recovered; otherwise BORDERLINE | B0–B4, X0–X2, O0–O1 | 4→5, 6→7 | same, clearly tagged validity |
| BASE-4 | Flickr + PubMed | B3-best, X0, X1, O0, O1 | 4→5 | transfer table |
| BASE-5 | Cora/Citeseer/Chameleon | B3-best, X0, X1, O0, O1 | 4→5 | boundary/negative table |

Required per-row columns: configuration, quality validity, layer pair, format, deployability, support bytes, packed-value bytes, descriptor/topology/output bytes, cache misses, DRAM bytes, exact traffic ratio vs B3-best, serialized and overlapped memory cycles, modeled host cycles, exactness, numerical equivalence, artifact path, and input hash.

Run full Ramulator2 timing for **B3-best vs X1** on Arxiv seeds 17/27 and Reddit for both pairs; run Yelp only if hard-valid, otherwise one explicitly supplementary pair. Retain full address-stream hashes and `submitted == served` counts. The existing one-pair timing results are retained as preliminary evidence, not overwritten.

## 9. Block D — controls and ablations

### Matched controls (traffic/timing, not support-only)

For Arxiv seed 17, Reddit, and Yelp (tagged borderline if necessary), run B3-best, X0, and X1 on pair 4→5 under:

1. real trained masks;
2. density-matched independent masks, seed 7007;
3. node permutation within each 128-row topology tile;
4. temporal layer-order shuffle;
5. random-initialization mask trace.

Report metadata reduction, exact traffic reduction, serialized speedup, capture/prototype residual rate, and cache hit rate. The control constructor must write its seed and a density/row-count preservation audit.

### Required ablation matrix

| ID | Change from principal X1 | Purpose |
|---|---|---|
| ABL-1 | W=1 / no temporal XOR | temporal contribution |
| ABL-2 | A0 independent anchors / no spatial prototype | spatial dictionary contribution |
| ABL-3 | no support cache | residency contribution |
| ABL-4 | no causal selector; force X1 | selector/fallback value |
| ABL-5 | no channel coloring | bank/channel mapping value |
| ABL-6 | ideal decoder | isolate decoder implementation overhead |
| ABL-7 | synthesized decoder parameters | hardware-realistic decoder cost |
| ABL-8 | remove compression/writeback cost | diagnostic bound only |
| ABL-9 | causal W={1,2,4,8} vs offline-majority oracle | causality/persistence cost |
| ABL-10 | FP8 vs FP32 activation storage | precision dependence |

Run ABL-1…ABL-10 on Arxiv seed 17 and Reddit, pair 4→5. Repeat ABL-1/2/3/4 on the second pair. If `channel coloring` is not implemented by the end of Block A, it must be a `NOT_IMPLEMENTED` row with source-level explanation—not silently omitted.

## 10. Block E — timing, RTL/PPA, and energy

### Cluster timing

- Ramulator2: complete full trace timing rows prescribed in Block C; persist request count, served count, cycles, bandwidth, and address trace hash.
- DRAMsim3: independent 250k-transaction bounded samples for BEICSR96/B3-best/X1 for Arxiv, Reddit, and Yelp; parse timing and energy/statistics if emitted. Each row is labelled `sampled_trace=true`.
- Do not substitute a DRAMsim3 sample for Ramulator full-trace timing.

### Local hardware evidence

| Tool | Exact task | Result path |
|---|---|---|
| CUDA RTX 4060 | 100+ repeats for BEICSR decode, XORFLOW decode, support-cache build, packed-row edge replay; median/p5/p95 GB/s and events/s | `local_toolchain/<id>/cuda_microbench.csv` |
| Verilator/Yosys | X1 decoder/controller random and real-stream co-sim; pipelined 1 GHz synthesis; no dropped/backpressured event | `ppa/<id>/rtl/` |
| OpenROAD ORFS Docker + Nangate45 | hierarchical decoder/controller block; area, slack, power proxy, DRC count; SRAMs black-boxed | `ppa/<id>/openroad/` |
| CACTI 7 Docker wrapper | support cache `{8,16,32,64}` KiB; metadata cache; descriptor SRAM; 45 nm area/access/dynamic/leakage | `ppa/<id>/cacti/` |

The PPA report must calculate decoder/controller area and power as a percentage of a clearly documented host reference. If a defensible host-area reference cannot be produced by the deadline, report absolute novel-subsystem PPA only and mark the host-percentage gate `UNASSESSED`.

## 11. Block F — bounded sensitivity

One factor at a time, using X1 vs B3-best for Arxiv seed 17 and Reddit:

- feature cache: `256 KiB`, `512 KiB`, `1 MiB`;
- HBM bandwidth: `128`, `256`, `512 GB/s`;
- support cache: `8`, `16`, `32`, `64 KiB`;
- slice width: `64`, `96`, `128`, `256`;
- decoder lanes: `8`, `16`, `32`;
- topology tile: `64`, `128`, `256` rows;
- O0 destination order vs O1 source-tiled order;
- Arxiv depth `4/8/16`, width `64/128/256`.

Only after the principal matrix and controls succeed may secondary transfer/sensitivity runs consume remaining GPU1 time.

## 12. Predeclared decision checks

Hard scientific checks use only hard-valid principal workloads. Yelp remains supplementary unless its recovery passes.

| Gate | Requirement |
|---|---|
| Correctness | all old/new tests, exact support/value round trips, numerical aggregation equivalence, causal legality, nonoverlap, rerun hashes |
| Metadata | causal X1 metadata reduction vs B3-best: >=20% geomean and >=10% individually on hard-valid large workloads |
| Traffic | >=8% geomean exact traffic reduction; no hidden change of precision/order/cache |
| Timing | >=1.10× geomean aggregation-memory speedup and >=1.05× individually on hard-valid large workloads |
| Host | >=1.08× modeled host geomean; at least two workloads >=1.10× |
| Learned structure | real beats density-null by >=1.25× metadata benefit or >=1.15× traffic benefit on >=2 workloads |
| Feasibility | 1 GHz routed logic; all caches fit; decoder meets required stream rate; no unserved timing requests |
| Robustness | benefit at 256/512 KiB/1 MiB and at >=2 legal slice widths |

Every gate row is `PASS`, `FAIL`, `UNASSESSED`, or `SUPPLEMENTARY_ONLY`; never coerce a missing experiment to a pass.

## 13. Logging, failure, and reproducibility protocol

1. Every task has a YAML declaration: task ID, dependency, machine, GPU setting, command, timeout, expected outputs, and scientific role.
2. `hpca_campaign` must write command, wall time, environment, stdout/stderr, return code, input/output hashes, and status to both its ledger and the canonical manifest.
3. A task with tool failure is `TOOL_FAILURE`; a task with a negative metric is `SCIENTIFIC_NEGATIVE`; a quality miss is `INVALID_MODEL` or `BORDERLINE`. These cannot be conflated.
4. Preserve partial CSVs and logs on timeout. Do not retrain/replace an existing trace silently.
5. Run `PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/rishabh/miniconda/envs/taugat_pyg/bin/python -m pytest -q` before Block A, after Block E, and before packaging.
6. Run the principal B3-best/X1 Arxiv seed 17 + Reddit matrix twice from cached traces. `HPCA_PAPER_MANIFEST.json` must compare SHA-256 values for all principal CSVs; a mismatch is an implementation failure.
7. Record `git rev-parse HEAD`, `git diff --binary`, Python path, CUDA/device, SCALE-Sim, Ramulator2, DRAMsim3, CACTI, Verilator/Yosys, and OpenROAD versions in the final manifest.

## 14. Final deliverables by deadline

1. `results_hpca_xorflow/complete_suite/HPCA_PAPER_EVIDENCE.md` — reviewer-facing tables, plots, gates, caveats, and paths.
2. `HPCA_PAPER_EVIDENCE.csv`, `HPCA_PAPER_GATES.csv`, and `HPCA_PAPER_MANIFEST.json`.
3. Publication figures: baseline traffic/timing, causal ablations, controls, timing breakdown, cache/slice sensitivity, precision/accuracy, decoder throughput, PPA/energy, and negative/boundary cases.
4. `HPCA_PAPER_READY_HANDOFF.zip` with source, configs, tests, reports, CSVs, figures, hashes, logs, and exact commands—excluding raw datasets, environments, third-party histories, and transient full traces.
5. A final `README` section that says precisely whether the causal X1 implementation—not an oracle—meets the paper-level evidence bar.

## 15. Immediate next commands after this plan

1. Implement/test the common format matrix and the evidence builder locally.
2. Commit and push only source/config/test changes; do not commit generated multi-gigabyte traces.
3. Run the Arxiv baseline smoke on GPU1 through a new `configs/hpca_baseline_smoke.yaml` campaign.
4. Inspect the smoke’s exactness and common-accounting rows before submitting the full Blocks B–F queue.
5. Keep the existing completed campaigns immutable; new results go in new timestamped run directories and are linked from the canonical evidence file.
