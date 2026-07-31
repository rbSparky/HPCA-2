# XORFLOW Reviewer-Spec Execution Status

Last updated: 2026-07-31 00:03 UTC. Canonical output root:
`results_hpca_xorflow/reviewer_spec_v3/`.

Progress: **7/8 evidence blocks complete; primary campaign complete; final
hardware/report validation remains**.

| Evidence block | State | Canonical path |
|---|---|---|
| Frozen serializer and real round trips | Complete (10 primary traces; 548,064 rows) | `serializer/`, `online_replay/streams/` |
| Causal replay, REREAD and finite retention | Complete (26 configurations) | `online_replay/` |
| Characterization and null controls | Complete (26 configurations) | `characterization/` |
| Optimized baseline and component ablations | Complete (26 configurations) | `ablation/` |
| Exact edge/cache physical traffic | Complete (26 configurations) | `physical_traffic/` |
| Finite encoder and integrated decoder sweeps | Complete (26 configurations × 3 bank modes) | `encoder/`, `decoder/` |
| Unified event-driven host schedule | Complete (26 configurations) | `schedule/` |
| RTL/PPA, DRAM timing, report, figures, bundle | Pending upstream results | `hardware/`, `memory/`, `report/` |

Compute allocation: four bounded CPU lanes on the cluster for codec/cache work;
GPU1 is reserved for genuine GPU tasks; GPU0 is untouched. Superseded pre-RCM
jobs are retained in `.xorflow_jobs/` with explicit `superseded_rcm_fix` or
`paused_for_optimization` status and are excluded from evidence.

The deterministic lane drivers all completed successfully at 2026-07-30
23:58 UTC. No campaign-lane failures were observed. The post-queue integrity
check found all 26 configurations complete for records, characterization,
ablation, physical traffic, encoder, all three decoder bank modes, and the
event schedule. The consolidator was rerun after ignoring its own empty
aggregate input on repeat runs; `RESULT_MANIFEST.csv` and `report/` are now
complete.

Validated optimization canary (`ogbn_arxiv_deepres8_w128_s7`):

- exact stream SHA-256 unchanged from the pre-optimization implementation;
- explicit transaction sum equals `xorflow_total_bytes`;
- runtime reduced from 14m23s to 1m37s;
- 105 focused serializer/replay/queue tests passed before campaign launch;
- corrected 32-bank integrated decoder model achieves 2,010.6 encoded bits/cycle;
- corrected conservative event schedule gives 1.108x versus same-host BEICSR on
  the Arxiv canary. This is preliminary until the complete campaign reruns and
  reproducibility hashes finish.
