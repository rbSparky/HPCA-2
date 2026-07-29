# XORFLOW Literature and Baseline Audit

**Audit date:** 2026-07-29  
**Rule:** a quantitative baseline must be reproducible under the same graph,
precision, feature layout, cache, edge order, and traffic accounting as
XORFLOW. A paper that changes pruning, graph semantics, storage medium, or the
entire host architecture is cited and discussed, but is not represented by an
invented numerical comparison.

## Direct quantitative baseline

| Work | What it contributes | XORFLOW treatment |
|---|---|---|
| Yoo *et al.*, **SGCN: Exploiting Compressed-Sparse Features in Deep GCN Accelerators**, HPCA 2023 ([paper](https://arxiv.org/abs/2301.10388)) | BEICSR: bitmap-embedded, in-place, sliced sparse features; sparse aggregation and locality/cooperation | **Primary B3 baseline.** Evaluate BEICSR at `C={64,96,128}`; report named `BEICSR96` and `best-BEICSR`. This is the only prior method with directly matching lossless intermediate-feature compression semantics. |

The local paper corpus contains the SGCN PDF at
`../HPCA GNN PAPERS/SGCN_Exploiting_Compressed-Sparse_Features_in_Deep_Graph_Convolutional_Network_Accelerators.pdf`.

## Necessary same-host format controls

These are not named accelerator papers, but are required to establish that a
benefit is not merely a generic sparse-layout artifact:

- dense FP8 row-major;
- CSR with 32-bit IDs;
- CSR with minimum legal packed feature IDs;
- independently best row-slice selection among dense/CSR/BEICSR;
- causal anchor rows (X0), causal cohort prototypes (X1), selector-disabled
  diagnostic (X2), future-majority oracle, and free-support oracle.

All are evaluated in the common physical/cache model. This matrix is more
informative than quoting speedups reported under unmatched chips or datasets.

## Relevant but non-isomorphic accelerator work

| Work | Why it is relevant | Why it is not a direct numerical baseline |
|---|---|---|
| HyGCN, **A GCN Accelerator with Hybrid Architecture** | canonical aggregation/combination split | different host and dataflow; use in architectural related work and host-design comparison only |
| GCNAX, **Flexible and Energy-efficient Accelerator for GCNs** | flexible GCN execution | no common support-format interface; unmatched model/technology assumptions |
| GROW, **Row-Stationary Sparse-Dense GEMM Accelerator** | sparse combination/dataflow reference | primarily compute/dataflow mapping rather than exact inter-layer feature support storage |
| ReGNN, **Redundancy-Eliminated GNN Accelerator** | graph/message redundancy elimination | changes message execution algorithm; not an activation-format-only comparison |
| PruneGNN, **Algorithm-Architecture Pruning Framework** | sparsity-aware GNN acceleration | pruning changes model/accuracy and violates XORFLOW's exact activation contract |
| BeaconGNN / Celeritas / Mithril / Buffalo / VeloxGNN | large-graph systems context | target training, storage, or out-of-core execution rather than lossless activation feature format |
| BEAST-GNN, **United Bit Sparsity-Aware Accelerator** ([publication record](https://cs.newpaltz.edu/~lik/publications/Yunzhen-Luo-IEEE-TC-2025)) | recent bit-level sparsity-aware GNN design | different bit-sparsity compute semantics; include a qualitative comparison unless an open artifact can be verified before the deadline |
| CBM, **Compressed Binary Matrix** ([paper](https://arxiv.org/abs/2409.02208)) | recent graph matrix compression | compresses adjacency, not learned intermediate activation support |
| NeuraChip ([paper](https://arxiv.org/abs/2404.15510)) | recent sparse/GNN accelerator memory scheduling | different sparse-kernel/host design, so qualitative only absent an open compatible model |

The local corpus additionally contains PDFs for ReGNN, PruneGNN, BeaconGNN,
HyGCN, GCNAX, GROW, Celeritas, and related GNN systems. These are used to
validate the evaluation taxonomy and related-work discussion.

## Paper-facing comparison discipline

1. The main table compares XORFLOW against `BEICSR96`, `best-BEICSR`, and the
   same-host generic controls.
2. A separate related-work table compares scope (activation format, graph
   format, pruning, execution redundancy, storage system), exactness, causal
   deployability, and whether each method can reuse support over edge replay.
3. Do not reproduce a published headline speedup on a different chip as if it
   were a baseline result.
4. If a public artifact for a non-isomorphic design is found and can be run
   without changing the common workload/precision contract, add it as an
   explicitly labelled secondary baseline; otherwise preserve it as related
   work only.
