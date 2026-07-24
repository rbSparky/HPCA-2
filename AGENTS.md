# AGENTS.md — MOSAIC-GNN Phase-0 Validation Harness

## 1. Mission

Build and run a **fast, reproducible, approximately one-hour experimental validation suite** for a candidate GNN accelerator idea called **MOSAIC-GNN**:

> MOSAIC-GNN hypothesizes that deep residual GNNs exhibit **spatial support coherence** across topology-local nodes and **temporal support persistence** across adjacent layers. If true, groups of nodes can share an exact activation-support template, execute most active features through a regular systolic path, and send only exceptions through a sparse residual path.

This first phase is a **kill test**, not a paper-result claim. It must answer:

1. Are post-ReLU activation masks more similar among topology-local nodes than among random nodes?
2. Do activation masks persist across adjacent residual layers?
3. Can locality-constrained cohorts capture most nonzeros with limited zero padding?
4. Does an exact template-plus-residual representation have a strong analytical cost advantage over dense and independent sparse execution?
5. Is the signal learned and structured, rather than an artifact of density alone?
6. Does the codebase have the correct modular shape to become a full SCALE-Sim v3/HPCA evaluation harness later?

Do not claim that a one-hour experiment proves an HPCA paper. The immediate objective is to determine whether the idea deserves deeper simulator and RTL work.

---

## 2. Research object and notation

For a trained GNN with hidden width `F`, record the hidden activation after every ReLU during evaluation:

\[
X^{(\ell)} \in \mathbb{R}^{N\times F}.
\]

Define the exact binary support mask:

\[
M^{(\ell)}_{vf}=\mathbf 1[X^{(\ell)}_{vf}>0].
\]

For a cohort `C` and template `T ⊆ {1,…,F}`, decompose every row exactly:

\[
X_v = X_v\odot T + X_v\odot (1-T).
\]

The first term is the fixed-position **regular core**. The second is the **sparse residual**. No value approximation, pruning, retraining constraint, or accuracy loss is permitted in this phase.

The quick suite analyzes masks and exact representation costs. It does not yet implement the full accelerator.

---

## 3. Non-negotiable constraints

1. **Target machine:** NVIDIA RTX 4060 with 8 GB VRAM, approximately 16 GB system RAM.
2. **Wall-clock target after environment creation:** 60 minutes; hard cap 75 minutes.
3. Use **one training seed, seed 7**, in the quick suite.
4. Do not create an `N × N` dense adjacency matrix.
5. Do not use NetworkX for graph storage or per-edge Python objects.
6. Use sparse `edge_index`/SciPy CSR only.
7. Do not silently skip failed configurations. Record status, exception, elapsed time, and partial outputs.
8. Do not fabricate successful GPU support. Verify `torch.cuda.is_available()` and record the actual device.
9. Do not spend more than 15 minutes debugging optional CUDA extensions. Basic PyG works without them.
10. Do not tune models for maximum accuracy. The models only need to be non-degenerate enough to produce meaningful trained traces.
11. All reported activation traces must be captured in `model.eval()` with dropout disabled.
12. The final code must be modular enough to expand to a paper-scale suite; do not write a single monolithic notebook.
13. The research direction must not be reframed as a causal, conformal, or certificate-based method.
14. Every analytical metric must be explicitly labeled as a proxy, not a measured hardware speedup.

---

## 4. Environment setup

### 4.1 Required environment strategy

Create a Conda/Mamba environment named:

```bash
mosaic-quick
```

Use:

```text
Python 3.11
```

Use Conda only to create/isolate the Python environment. Install current PyTorch and PyTorch Geometric binaries with `pip` inside that environment, because current PyG documentation states that Conda packages are not provided for newer PyTorch releases.

Official references:

- PyTorch local installation: https://docs.pytorch.org/get-started/locally/
- PyTorch Geometric installation: https://pytorch-geometric.readthedocs.io/en/stable/notes/installation.html
- SCALE-Sim: https://github.com/scalesim-project/SCALE-Sim

### 4.2 Installation decision procedure

1. Record:

```bash
uname -a
nvidia-smi
conda --version || mamba --version
```

2. Create the environment:

```bash
conda create -n mosaic-quick python=3.11 pip -y
conda activate mosaic-quick
```

3. Inspect the installed NVIDIA driver with `nvidia-smi`.
4. Use the current stable PyTorch pip command from the official selector for a CUDA runtime supported by the driver.
5. Verify:

```bash
python - <<'PY'
import torch
print(torch.__version__)
print(torch.version.cuda)
print(torch.cuda.is_available())
if torch.cuda.is_available():
    print(torch.cuda.get_device_name(0))
PY
```

6. Install minimal PyG first:

```bash
pip install torch_geometric
```

Do not install `pyg_lib`, `torch_scatter`, or `torch_sparse` unless the basic model fails or installation is immediate from a matching prebuilt wheel. Never compile these from source during the quick phase.

7. Install the remaining dependencies:

```bash
pip install numpy scipy pandas scikit-learn matplotlib pyyaml tqdm psutil pynvml pytest
```

8. Clone and install SCALE-Sim v3 in editable mode:

```bash
git clone https://github.com/scalesim-project/SCALE-Sim.git third_party/SCALE-Sim
cd third_party/SCALE-Sim
# Prefer the latest stable v3 tag. If tag 3.0.0 exists, use it.
git checkout 3.0.0 || true
pip install -e .
cd ../..
```

If tag `3.0.0` is unavailable or broken, use the current `main` commit and record its hash. Do not switch among arbitrary commits to chase a passing test.

9. Run one built-in SCALE-Sim smoke test or one tiny MNK GEMM generated by this project. The quick suite only requires a smoke run; Ramulator and Accelergy are deferred.

### 4.3 CPU fallback

If GPU PyTorch cannot be installed within 15 minutes:

- install a CPU PyTorch wheel;
- run the suite on CPU;
- reduce maximum epochs from 120 to 70;
- retain all four configurations unless the hard wall-clock cap is reached;
- mark `gpu_available=false` in the environment table.

Do not pretend CPU results were generated on GPU.

### 4.4 Environment artifacts

Generate:

```text
artifacts/environment/conda-history.yml
artifacts/environment/pip-freeze.txt
artifacts/environment/system.txt
artifacts/environment/scalesim-commit.txt
```

---

## 5. Repository structure

Create this structure:

```text
mosaic_validation/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── configs/
│   ├── quick.yaml
│   └── future_full.yaml
├── scripts/
│   ├── setup_env.sh
│   ├── run_quick.sh
│   └── run_tests.sh
├── src/mosaic_validation/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── reproducibility.py
│   ├── datasets.py
│   ├── models.py
│   ├── training.py
│   ├── tracing.py
│   ├── graph_order.py
│   ├── pair_metrics.py
│   ├── cohorts.py
│   ├── temporal.py
│   ├── analytical_cost.py
│   ├── gates.py
│   ├── reporting.py
│   └── scalesim_bridge.py
├── tests/
│   ├── test_masks.py
│   ├── test_template_optimality.py
│   ├── test_cohorts.py
│   ├── test_temporal_matching.py
│   └── test_cost_models.py
├── data/
├── checkpoints/
├── results/
└── third_party/
```

Use type hints, docstrings for mathematical functions, deterministic seeds, and structured logging.

---

## 6. Exact quick-suite configurations

Run exactly these configurations in order:

| ID | Dataset | Model | Hidden layers | Width | Seed | Required |
|---|---|---|---:|---:|---:|---|
| `cora_gcnii16` | Cora | GCNII | 16 | 64 | 7 | Yes |
| `pubmed_gcnii16` | PubMed | GCNII | 16 | 64 | 7 | Yes |
| `chameleon_gcnii16` | Chameleon | GCNII | 16 | 64 | 7 | Yes; adversarial/heterophilic control |
| `cora_resgcn16` | Cora | residual GCN | 16 | 64 | 7 | Yes; architecture-transfer check |

Do not add more datasets or seeds in the quick run.

### 6.1 Datasets

Use PyG datasets with `NormalizeFeatures()`:

```python
Planetoid(root=..., name="Cora", transform=NormalizeFeatures())
Planetoid(root=..., name="PubMed", transform=NormalizeFeatures())
WikipediaNetwork(
    root=...,
    name="chameleon",
    geom_gcn_preprocess=True,
    transform=NormalizeFeatures(),
)
```

Use the standard Planetoid masks. For Chameleon, the masks have multiple columns; use split column `0` for train, validation, and test.

Make the graph undirected for analysis ordering and pair metrics using `to_undirected`, but use the dataset graph consistently for model execution. Record whether the original or symmetrized edge set was used by each component.

### 6.2 GCNII architecture

Implement using `torch_geometric.nn.GCN2Conv`.

Exact structure:

```text
input dropout p=0.5
Linear(num_features, 64)
ReLU -> x0
for layer i = 1..16:
    Dropout p=0.5
    GCN2Conv(
        channels=64,
        alpha=0.1,
        theta=0.5,
        layer=i,
        shared_weights=True,
        cached=True,
    )(x, x0, edge_index)
    ReLU
    record post-ReLU activation
output dropout p=0.5
Linear(64, num_classes)
```

Official operator reference:
https://pytorch-geometric.readthedocs.io/en/stable/generated/torch_geometric.nn.conv.GCN2Conv.html

### 6.3 Residual GCN architecture

Implement:

```text
Linear(num_features, 64)
ReLU
for layer i = 1..16:
    z = LayerNorm(64)(x)
    z = ReLU(z)
    z = Dropout(z, p=0.5)
    z = GCNConv(64, 64, cached=True)(z, edge_index)
    x = ReLU(x + z)
    record post-ReLU activation
output dropout p=0.5
Linear(64, num_classes)
```

There must be one independent `LayerNorm` and `GCNConv` per layer.

### 6.4 Training

Use:

```text
optimizer: Adam
learning rate: 0.01
weight decay: 5e-4
maximum epochs: 120
minimum epochs before early stop: 40
early-stopping patience: 20 validation checks
validation interval: every 2 epochs
loss: cross entropy over train mask
checkpoint criterion: minimum validation loss
```

Do not use automatic mixed precision unless all configurations pass a numerical equivalence smoke test. Default to FP32.

Capture two trace states:

1. `random_init`: model in evaluation mode before the first optimizer step.
2. `trained`: best-validation checkpoint in evaluation mode.

Only `trained` traces determine the principal pass/fail gates. `random_init` is a control.

### 6.5 Accuracy validity floors

A configuration is valid only when:

| Configuration | Minimum test accuracy |
|---|---:|
| `cora_gcnii16` | 0.70 |
| `pubmed_gcnii16` | 0.70 |
| `chameleon_gcnii16` | 0.35 |
| `cora_resgcn16` | 0.65 |

Also require:

- finite loss throughout training;
- best validation loss at least 5% lower than validation loss at epoch 2;
- no all-zero hidden layer;
- no hidden layer with density above 0.995 for all nodes.

A quality failure is `INVALID_MODEL`, not evidence against MOSAIC.

---

## 7. Runtime policy

The quick experiment has a 75-minute hard cap after environment setup.

Suggested time budgets:

| Task | Cap |
|---|---:|
| Unit tests and dataset download | 8 min |
| `cora_gcnii16` | 8 min |
| `pubmed_gcnii16` | 18 min |
| `chameleon_gcnii16` | 10 min |
| `cora_resgcn16` | 8 min |
| Mask/cohort analysis and reports | 15 min |
| SCALE-Sim smoke test | 5 min |

If a per-configuration cap is reached, save the best checkpoint and continue. Mark `training_truncated=true`. Do not discard the configuration unless it is invalid by the quality rules.

If the hard cap is approaching, reduce bootstrap resamples before reducing the mandatory model list.

---

## 8. Activation tracing

For every hidden layer, save:

```text
post-ReLU FP32 activation shape
binary support mask
row nonzero count
layer density
```

Storage format:

- Save masks packed with `numpy.packbits` to avoid unnecessarily large files.
- Save aggregate metrics in CSV.
- Do not save all FP32 activations unless total size remains below 1 GB.
- Values are not needed for the quick structural analysis; masks are sufficient.

Mask rule:

```python
mask = activation > 0
```

Do not introduce an epsilon threshold.

Analyze principal layers `4..16`, inclusive. Layers `1..3` are recorded but excluded from aggregate gates because they can be transient.

---

## 9. Graph ordering and pair sampling

### 9.1 RCM ordering

Construct a SciPy CSR adjacency from the symmetrized graph. Use:

```python
scipy.sparse.csgraph.reverse_cuthill_mckee
```

Do not densify the adjacency.

Create contiguous topology tiles of 128 nodes in RCM order. The final tile may be smaller.

### 9.2 Pair sets

For each layer, evaluate normalized Hamming mismatch on:

1. `edge_pairs`: up to 50,000 unique undirected graph edges.
2. `rcm_local_pairs`: up to 50,000 random node pairs from the same 128-node RCM tile.
3. `random_pairs`: 50,000 uniformly sampled distinct node pairs.

Use seed 7. If fewer pairs exist, use all available pairs.

For a pair `(u,v)`:

\[
d_H(u,v)=\frac{1}{F}\sum_f M_{uf}\oplus M_{vf}.
\]

Report:

```text
edge_to_random_ratio = mean_edge_mismatch / mean_random_mismatch
local_to_random_ratio = mean_local_mismatch / mean_random_mismatch
```

Also calculate 95% confidence intervals by bootstrapping sampled pairs with 200 replicates. If runtime is constrained, use 50 replicates and record the change.

### 9.3 Temporal row-shuffle control

For each adjacent pair of layers, independently permute the rows of layer `l+1` and compute:

```text
same_node_temporal_flip
row_shuffled_temporal_flip
```

This preserves each layer’s density and row-sparsity distribution while destroying node identity.

---

## 10. Exact cohort methods

Evaluate four grouping methods per layer.

### 10.1 `random_balanced`

Randomly permute nodes with seed derived from `(seed, layer)` and divide into groups of target size 32.

### 10.2 `rcm_contiguous`

Use RCM order and divide each 128-node tile into contiguous groups of target size 32.

### 10.3 `rcm_cost_cluster`

Within every 128-node RCM tile:

- choose `K = ceil(tile_size / 32)`, capped at 4;
- target approximately balanced cohorts;
- run at most 5 alternating assignment/template iterations.

#### Initialization

Use deterministic farthest-first Hamming initialization:

1. First seed is the row whose nonzero count is closest to the tile median; ties go to lowest original node ID.
2. Each next seed maximizes distance to its closest existing seed; ties go to lowest node ID.

#### Template update

For a cohort of size `m`, let `c_f` be the number of rows active at feature `f`.

Use the exact payload-byte model:

- regular core slot: 4 bytes;
- sparse residual element: 4-byte value plus 2-byte feature ID = 6 bytes;
- template feature descriptor: 2 bytes per feature per cohort.

Include feature `f` in the template iff:

\[
4m + 2 < 6c_f.
\]

This is the exact per-feature optimum under the stated payload model.

#### Assignment update

For row support `S_v` and template `T_k`, use:

\[
C(v,k)=4|T_k|+6|S_v\setminus T_k|.
\]

Use deterministic balanced greedy assignment:

1. Compute the best and second-best costs for every row.
2. Sort rows by descending `(second_best - best)`; tie by node ID.
3. Assign each row to its cheapest cohort with remaining capacity.
4. Cohort capacity is `ceil(tile_size/K)`.
5. If the cheapest is full, use the next cheapest.

Stop after assignments do not change or after 5 iterations.

### 10.4 `global_lsh_oracle`

This is a cheap locality-free upper-bound diagnostic, not a deployable policy.

For each layer:

1. Generate a fixed `F × 16` Rademacher matrix with seed 7.
2. Compute a 16-bit SimHash signature from centered binary masks `(2M-1)`.
3. Sort nodes by `(signature, row_nnz, original_node_id)`.
4. Divide into groups of 32.
5. Construct templates using the same exact template rule.

This method intentionally ignores graph locality. It diagnoses whether support is globally clusterable even when `rcm_cost_cluster` underperforms.

---

## 11. Representation and analytical cost metrics

For every cohort `C` with template `T`:

```text
m               = number of rows
core_slots      = m * |T|
core_true_nnz   = sum of active entries in template positions
holes           = core_slots - core_true_nnz
residual_nnz    = total_nnz - core_true_nnz
```

Aggregate across cohorts.

### 11.1 Structural metrics

```text
regular_capture = core_true_nnz / total_nnz
padding_fraction = holes / core_slots
residual_fraction = residual_nnz / total_nnz
```

Use `0` for padding when `core_slots=0`.

### 11.2 Transfer-byte models

#### Dense baseline

FP32 rows, 64-byte burst alignment:

```text
dense_transfer_bytes = N * ceil(4*F / 64) * 64
```

#### Independent bitmap sparse baseline

This is a BEICSR-like lower-complexity proxy: one `F`-bit bitmap followed by FP32 nonzeros, aligned per row.

```text
row_payload_i = ceil(F/8) + 4*nnz_i
bitmap_sparse_transfer_bytes = Σ_i ceil(row_payload_i / 64) * 64
```

#### MOSAIC transfer

For each cohort:

```text
core_bytes = 4 * core_slots
residual_bytes = 6 * residual_nnz + 4*(m+1)   # residual row pointers
descriptor_bytes = 2*|T| + m                  # template IDs + 1-byte cohort metadata/row
cohort_transfer =
    ceil(core_bytes/64)*64
  + ceil(residual_bytes/64)*64
  + ceil(descriptor_bytes/64)*64
```

Sum cohort transfers.

Report:

```text
best_baseline_transfer = min(dense_transfer, bitmap_sparse_transfer)
mosaic_to_best_byte_ratio = mosaic_transfer / best_baseline_transfer
```

These are representation/burst proxies, not a complete cache or DRAM simulation.

### 11.3 Irregular-cost proxy

Let `rho` be the relative cost of one independently scheduled sparse element versus one regular core slot.

For `rho ∈ {1.5, 2.0, 3.0, 4.0}`:

\[
C_{baseline}(\rho)=\min(NF,\rho\,nnz),
\]

\[
C_{MOSAIC}(\rho)=core\_slots+\rho\,residual\_nnz,
\]

\[
S_{proxy}(\rho)=\frac{C_{baseline}(\rho)}{C_{MOSAIC}(\rho)}.
\]

Also report the smallest `rho ∈ [1,8]` for which MOSAIC beats the best baseline, found by deterministic binary search or a fine grid with step at most 0.01.

No document may call `S_proxy` an actual speedup.

---

## 12. Temporal persistence metrics

For adjacent trained layers within each fixed RCM tile:

1. Fit `rcm_cost_cluster` independently at each layer.
2. Match cohort labels between layers with the Hungarian algorithm, maximizing node-set overlap. Use template Jaccard as a deterministic tie-breaker.
3. Report:

```text
activation_flip = mean(M_l XOR M_{l-1})
activation_flip_shuffled = mean(M_l XOR permute_rows(M_{l-1}))
assignment_stability = fraction of nodes retaining matched cohort
matched_template_jaccard = mean Jaccard(T_l, matched T_{l-1})
```

### 12.1 Conservative reuse penalty

Reuse both previous-layer assignments and matched templates on the current layer without rebuilding them.

Calculate the payload cost under the same 4-byte/6-byte model:

```text
reuse_penalty = reused_cost / independently_refit_cost - 1
```

This is the central schedule-persistence diagnostic.

---

## 13. Controls

The quick suite must include:

1. `random_init` traces for all configurations.
2. `random_balanced` grouping on trained traces.
3. `rcm_contiguous` grouping on trained traces.
4. `global_lsh_oracle` on trained traces.
5. Row-shuffled temporal controls.
6. Random-pair spatial controls.

The main question is not merely whether masks are sparse. It is whether support identity carries reusable spatial/temporal structure beyond density-preserving controls.

---

## 14. Exact output tables

Create these CSV files.

### 14.1 `00_environment.csv`

One row with:

```text
run_id,timestamp,os,cpu,logical_cores,total_ram_gb,gpu,
gpu_vram_gb,nvidia_driver,python,torch,torch_cuda,
torch_geometric,numpy,scipy,scalesim_commit,cuda_available,
total_wall_seconds
```

### 14.2 `01_model_quality.csv`

One row per configuration and trace state:

```text
config_id,dataset,model,layers,width,seed,trace_state,
status,epochs_completed,training_truncated,best_epoch,
train_accuracy,val_accuracy,test_accuracy,epoch2_val_loss,
best_val_loss,train_seconds,trace_seconds,peak_gpu_memory_mb,
num_nodes,num_edges,num_features,num_classes
```

### 14.3 `02_layer_signal.csv`

One row per configuration, trace state, and layer:

```text
config_id,trace_state,layer,num_nodes,width,density,mean_row_nnz,
mask_marginal_entropy,edge_mismatch,edge_ci_low,edge_ci_high,
local_mismatch,local_ci_low,local_ci_high,random_mismatch,
random_ci_low,random_ci_high,edge_to_random_ratio,
local_to_random_ratio,temporal_flip,temporal_flip_shuffled,
temporal_flip_ratio
```

For layer 1, temporal fields are empty.

### 14.4 `03_cohort_layer.csv`

One row per configuration, trace state, layer, and grouping method:

```text
config_id,trace_state,layer,grouping_method,num_cohorts,
mean_cohort_size,mean_template_features,total_nnz,core_true_nnz,
core_slots,holes,residual_nnz,regular_capture,padding_fraction,
residual_fraction,dense_transfer_bytes,bitmap_sparse_transfer_bytes,
mosaic_transfer_bytes,mosaic_to_best_byte_ratio,proxy_speedup_rho1_5,
proxy_speedup_rho2,proxy_speedup_rho3,proxy_speedup_rho4,
break_even_rho
```

### 14.5 `04_temporal_reuse.csv`

One row per trained configuration and adjacent layer transition:

```text
config_id,from_layer,to_layer,activation_flip,
activation_flip_shuffled,activation_flip_ratio,
assignment_stability,matched_template_jaccard,
independent_refit_cost,reused_schedule_cost,reuse_penalty
```

### 14.6 `05_config_summary.csv`

One row per configuration, using trained principal layers 4..16:

```text
config_id,model_valid,median_density,
median_edge_to_random,median_local_to_random,
median_temporal_flip,median_temporal_flip_ratio,
median_assignment_stability,median_template_jaccard,
median_reuse_penalty,median_regular_capture,p75_padding_fraction,
median_residual_fraction,median_mosaic_to_best_byte_ratio,
median_proxy_speedup_rho2,median_proxy_speedup_rho3,
random_group_proxy_speedup_rho2,global_lsh_proxy_speedup_rho2,
rcm_over_random_cost_gain,rcm_fraction_of_oracle_gap,
spatial_gate,temporal_gate,cohort_gate,control_gate,
config_decision
```

### 14.7 `06_project_gates.csv`

One row per project-level gate:

```text
gate_id,description,value,threshold,status,evidence
```

### 14.8 `07_failures.csv`

```text
stage,config_id,exception_type,message,traceback_file,
elapsed_seconds,recoverable,action_taken
```

Generate an empty file with headers when no failures occur.

---

## 15. Required plots

Generate PNG and PDF versions:

1. `density_by_layer`
2. `spatial_mismatch_ratio_by_layer`
3. `temporal_flip_by_layer`
4. `regular_capture_padding_by_layer`
5. `proxy_speedup_rho2_by_layer`
6. `reuse_penalty_by_layer`
7. `grouping_method_comparison`
8. `trained_vs_random_init`

Use one plot per figure, no multi-panel figures in the quick suite. Include horizontal gate lines where relevant.

---

## 16. Unit tests

Before training, run `pytest -q` and require the following.

### 16.1 Exact decomposition

For random masks and templates:

```text
core_true + residual == original support
core and residual supports are disjoint
```

### 16.2 Template optimality

For cohorts with `F <= 8`, brute-force every possible template and verify that the closed-form rule minimizes:

\[
4m|T|+2|T|+6\sum_v|S_v\setminus T|.
\]

### 16.3 Known mask cases

- Identical masks: pair mismatch 0, template recovery exact.
- Disjoint masks: pair mismatch 1 where applicable.
- All-zero masks: no division errors.
- All-one masks: regular capture 1, padding 0.

### 16.4 Temporal matching

Permuted cohort labels must yield assignment stability 1 after Hungarian matching.

### 16.5 No dense adjacency

Add a test or assertion that rejects construction of an adjacency object with shape `(N,N)` in dense NumPy/PyTorch form for these datasets.

---

## 17. Pass/fail gates

All medians below use trained layers 4..16. Temporal medians use transitions among those layers.

### 17.1 Model validity gate

Use the accuracy and loss requirements in Section 6.5.

Status:

- `PASS`: all requirements satisfied.
- `INVALID_MODEL`: requirements not satisfied.

Do not evaluate the research hypothesis from an invalid model.

### 17.2 Spatial gate `S`

`PASS` when all are true:

```text
median(edge_to_random_ratio) <= 0.90
median(local_to_random_ratio) <= 0.90
at least 8 of 13 principal layers have local_to_random_ratio <= 0.95
upper 95% CI of either median effect is below 0.98
```

`AMBER` when:

```text
one median ratio <= 0.90
or both median ratios <= 0.97
```

Otherwise `FAIL`.

### 17.3 Temporal gate `T`

`PASS` when all are true:

```text
median temporal_flip <= 0.22
median temporal_flip_ratio_to_row_shuffle <= 0.80
median assignment_stability >= 0.60
median reuse_penalty <= 0.10
```

`AMBER` when all are true:

```text
median temporal_flip <= 0.30
median temporal_flip_ratio_to_row_shuffle <= 0.90
median assignment_stability >= 0.45
median reuse_penalty <= 0.18
```

Otherwise `FAIL`.

### 17.4 Cohort/hardware-potential gate `C`

For `rcm_cost_cluster`, `PASS` when all are true:

```text
median regular_capture >= 0.70
75th percentile padding_fraction <= 0.30
median residual_fraction <= 0.30
median proxy_speedup_rho2 >= 1.15
median proxy_speedup_rho3 >= 1.30
median mosaic_to_best_byte_ratio <= 1.05
median break_even_rho <= 2.25
```

Alternative byte-tolerance clause: the byte-ratio requirement may be treated as passing when:

```text
median mosaic_to_best_byte_ratio <= 1.15
median regular_capture >= 0.80
median proxy_speedup_rho2 >= 1.30
```

This means the representation spends modestly more bytes but creates substantially more regular execution. Mark that case `PASS_WITH_BYTE_TRADEOFF`.

`AMBER` when:

```text
median regular_capture >= 0.60
median proxy_speedup_rho2 >= 1.08
median mosaic_to_best_byte_ratio <= 1.20
```

Otherwise `FAIL`.

### 17.5 Control/oracle gate `O`

`PASS` when all are true:

```text
rcm_cost_cluster median rho2 proxy speedup is at least 8% better than random_balanced
rcm_cost_cluster closes at least 50% of the gain from random_balanced to global_lsh_oracle, when that gap is positive
global_lsh_oracle median rho2 proxy speedup >= 1.20
```

When the oracle is not better than random, set the gap-closure field to null and fail the oracle condition.

`AMBER` when the RCM method beats random by at least 3% and the oracle reaches 1.10.

Otherwise `FAIL`.

### 17.6 Per-configuration decision

- `STRONG_PASS`: valid model, `C` passes, and at least two of `S`, `T`, `O` pass.
- `PARTIAL_PASS`: valid model, `C` or `O` passes, and at least one of `S`, `T` is pass/amber.
- `FAIL_SIGNAL`: valid model but neither `C` nor `O` passes.
- `INVALID_MODEL`: quality gate failed.

### 17.7 Project-level decision

#### `GO_TO_SCALESIM_METHOD_IMPLEMENTATION`

Require all:

1. `cora_gcnii16` and `pubmed_gcnii16` are valid.
2. At least one of those two is `STRONG_PASS`; the other is at least `PARTIAL_PASS`.
3. `cora_resgcn16` is at least `PARTIAL_PASS`.
4. At least two of the three configurations above pass cohort gate `C`.
5. Across Cora-GCNII and PubMed-GCNII combined:
   - median `proxy_speedup_rho2 >= 1.20`;
   - median `regular_capture >= 0.70`;
   - median `reuse_penalty <= 0.10`.
6. RCM clustering beats random grouping by at least 8% in at least two valid configurations.
7. No required test or metric implementation is known to be incorrect.

Chameleon is allowed to fail. A Chameleon failure can support a selective-runtime-fallback story.

#### `ITERATE_METHOD_BEFORE_SIMULATOR`

Use when:

- at least one of Cora-GCNII or PubMed-GCNII passes `C` or `O`;
- and at least one spatial or temporal gate is pass/amber;
- but the full `GO` requirements are not met.

#### `PIVOT_OR_KILL_TEMPLATE_DIRECTION`

Use when either:

1. Both Cora-GCNII and PubMed-GCNII have global-oracle `rho2 < 1.10`; or
2. Both have global-oracle regular capture below 0.55; or
3. Both spatial and temporal gates fail on all valid homophilic configurations and reuse penalty exceeds 0.25.

---

## 18. Failure-driven iteration map

The report must map failures to the next method variant.

| Observed result | Interpretation | Next method |
|---|---|---|
| Spatial fails, temporal passes | Support persists per node but topology-local nodes do not share it | Temporal per-node/delta templates; remove cross-node cohort claim |
| Spatial passes, temporal fails | Cohorts exist but change per layer | Rebuild templates every layer; drop schedule-persistence component |
| Global oracle passes, RCM clustering fails | Signal exists but locality constraint is poor | Joint edge-locality/support partitioner; increase tile dictionary; limited cross-tile migration |
| Capture is high, padding too high | Shared templates are too permissive | Hole gating, two-level templates, lower threshold, N:M subtemplates |
| Byte ratio fails but rho proxies pass | Benefit is compute/scheduling, not feature compression | Emphasize weight-panel reuse and regular systolic issue; add exact memory simulator before claims |
| Trained and random-init signals are similar | Structure may be architectural rather than learned | Reframe workload observation; compare normalization/residual variants |
| Only Chameleon fails | Heterophily weakens topology support coherence | Add runtime selector/fallback and use heterophily as a limitation study |
| All methods fail, including global oracle | Mask identity is not reusable | Kill or substantially pivot the idea |

---

## 19. SCALE-Sim smoke integration

The quick suite must prove that SCALE-Sim v3 is callable.

1. Generate a GEMM topology CSV for the combination stage of each hidden layer:

```text
M = num_nodes
N = hidden_width
K = hidden_width
```

2. Generate a small architecture configuration with:

```text
array: 32 × 32
ifmap SRAM: 256 KB
filter SRAM: 256 KB
ofmap SRAM: 256 KB
dataflow: weight stationary, or the closest supported preset
```

3. Run SCALE-Sim on one Cora hidden layer and save its standard reports.
4. Put the exact command in `results/SCALESIM_SMOKE.md`.
5. Do not claim that this dense smoke run evaluates MOSAIC.
6. Create a clean interface in `scalesim_bridge.py` so a later phase can emit separate regular-core and residual workloads.

---

## 20. Final report

Generate `results/RESULTS.md` with:

1. Executive decision: `GO`, `ITERATE`, or `PIVOT/KILL`.
2. Actual runtime and environment.
3. Model validity table.
4. Exact project gates with pass/fail status.
5. Four compact configuration summaries.
6. Control comparisons.
7. Most important positive signal.
8. Most important failure.
9. Which component of MOSAIC remains supported:
   - spatial cohorts;
   - temporal persistence;
   - both;
   - neither.
10. The next experiment dictated by the failure-driven map.
11. Explicit statement that proxy speedups are not hardware speedups.

Also create:

```text
results/results_bundle.zip
```

containing all CSVs, plots, configs, logs, environment records, checkpoints or checkpoint hashes, and the final report.

---

## 21. Requirements for eventual HPCA-strength expansion

The quick suite is only acceptable if its architecture can expand without rewriting the project.

Create `configs/future_full.yaml` documenting, but do not run, the future suite:

### Datasets

- Cora
- CiteSeer
- PubMed
- CitationFull-DBLP
- GitHub
- Flickr
- ogbn-arxiv
- Reddit2 or an equivalently large graph using memory-safe trace generation
- Chameleon
- Squirrel

### Models

- GCNII at 16, 32, and 64 layers
- Residual GCN/DeepGCN at 16 and 28 layers
- residual GraphSAGE
- GIN/GINConv variant

### Statistical rigor

- five seeds for model training or five released checkpoints;
- confidence intervals across datasets, seeds, and layers;
- predeclared primary metrics and gates;
- no post-hoc removal of unfavorable workloads.

### Architecture evaluation

- SCALE-Sim v3 regular-core path;
- explicit sparse residual timing;
- Ramulator memory timing;
- Accelergy/CACTI-compatible energy accounting;
- 16×16, 32×32, and 64×64 arrays;
- 256 KB to 2 MB on-chip storage;
- 64, 128, and 256 GB/s bandwidth;
- several dataflows and core counts.

### Baselines

- dense execution;
- CSR;
- CSC;
- Blocked ELLPACK;
- independent bitmap/BEICSR-like features;
- dynamic dense/sparse selector;
- locality-only grouping;
- support-only oracle grouping;
- RSH-style regular-fragment plus sparse fallback if implementable;
- SGCN-like per-row compressed-feature baseline.

### Required ablations

- no topology constraint;
- no mask clustering;
- no temporal reuse;
- fixed majority template versus cost-optimal template;
- no hole gating;
- no template cache;
- no runtime fallback;
- cohort size and template-count sensitivity.

### Paper-grade outputs

- end-to-end cycles;
- DRAM/SRAM traffic;
- array utilization;
- stall decomposition;
- area and energy estimates;
- metadata and preprocessing overhead;
- graph ordering overhead;
- accuracy equivalence;
- sensitivity and negative results.

The quick implementation should expose interfaces for all of these extensions.

---

## 22. Coding and reporting standards

- Python formatting: `ruff`-compatible style if available; otherwise PEP 8.
- Use `pathlib` rather than string path concatenation.
- Use dataclasses or typed configuration objects.
- All random sources must derive from the configured seed.
- Every CSV must have stable column order.
- Every figure must be reproducible from CSV files alone.
- Do not hide warnings that can affect correctness.
- Cache downloaded datasets and checkpoints.
- Log commands and Git commits.
- Never overwrite a previous run; use timestamped run IDs and update a `latest` symlink or text pointer.
- The code must run from one command:

```bash
bash scripts/run_quick.sh
```

- The command must exit nonzero only for implementation/environment failures, not because a scientific gate failed.

---

## 23. Completion definition

The task is complete only when:

1. The environment is recorded and reproducible.
2. Unit tests pass.
3. All four configurations were attempted.
4. All required CSVs exist with headers and documented units.
5. All required plots exist.
6. SCALE-Sim smoke test succeeds or a precise blocker is documented.
7. `RESULTS.md` makes an honest project-level decision from the declared gates.
8. `results_bundle.zip` exists.
9. The entire run is reproducible with `scripts/run_quick.sh`.
10. No measured proxy is mislabeled as hardware speedup.
