# XORFLOW Reviewer-Spec Final Results

Generated UTC: 2026-07-31T05:16:36.665164+00:00
Git commit: `675a368ede272049e13c322a472e4734b84795b5`; generated tables and tool artifacts are committed alongside this source revision in the handoff.

## Executive status

The causal serializer, exact round trips, single-pass online replay, finite retention/REREAD accounting, controls, physical traffic, tile-scale RTL encoder stream engine, eight-lane decoder/support-cache cluster, event-driven host schedule, Verilator co-simulation, and OpenROAD cluster flow are complete for 26 cached configurations. The core result is positive on the larger residual workloads. RTL now performs finite support ingestion/majority accumulation plus full 32-row × 64-bit tile XOR event discovery and exact dense/fixed-ID/Gap8 packing and selection. Real serialized-stream VCD activity is captured for the encoder and for an Arxiv s17 decoder-stream prefix, and the physical decoder top has a VCD-annotated routed power report; full-workload energy is not claimed.

**Decision: ITERATE_METHOD_BEFORE_SIMULATOR** — proceed with one bounded integration iteration (encoder RTL + full-trace memory timing + final figures) before presenting a deployable hardware claim.

## Primary online results

All bytes are exact serialized/physical accounting; event speedups are modeled same-host aggregation/combination subsystem estimates, not measured accelerator speedups.

| Configuration | Support reduction | Exact edge-traffic reduction | Event-driven speedup |
|---|---:|---:|---:|
| flickr_deepres8_w128_s7 | 56.7% | 5.9% | 1.061× |
| ogbn_arxiv_deepres8_w128_s17 | 19.5% | 9.7% | 1.106× |
| ogbn_arxiv_deepres8_w128_s27 | 18.7% | 11.5% | 1.129× |
| ogbn_arxiv_deepres8_w128_s7 | 21.6% | 9.9% | 1.108× |
| reddit_deepres8_w128_s17_native | 33.8% | 10.0% | 1.111× |
| reddit_deepres8_w128_s27_native | 34.3% | 7.5% | 1.082× |
| reddit_deepres8_w128_s7_native | 27.1% | 21.8% | 1.277× |
| yelp_deepres8_w128_s7_balanced_fallback | 45.2% | 4.8% | 1.050× |

The strongest causal/event-driven points are Reddit seed 7 (1.277× in the complete online campaign), Arxiv DeepRes-16 (1.227×), and Arxiv DeepRes-8 seeds 7/17/27 (1.108/1.106/1.129×). Flickr and heterophilic/weak-persistence cases correctly fall back or remain near parity; those negative cases are retained.

## Correctness and regression

- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/rishabh/miniconda/envs/taugat_pyg/bin/python -m pytest -q`: **228 passed**, 2 non-fatal warnings.
- The reviewer-spec round-trip summary has one row per real serialized source; failures are counted in `decoder/stream_roundtrip.csv`.
- Causal commits use only the currently available layer; finite retention and REREAD are charged explicitly.
- The consolidated manifest is `RESULT_MANIFEST.csv`; every aggregate records source files and SHA-256.
- Two no-training finalization runs produced identical principal CSV hashes; see `report/DETERMINISTIC_RERUN.md` and `report/DETERMINISTIC_RERUN.csv`.

## Toolchain evidence

| Component | Status | Evidence |
|---|---|---|
| CUDA microbenchmark | PASS | `results_hpca_xorflow/complete_suite/local_toolchain_20260730T074723Z/cuda_microbench.csv` |
| DRAMsim3 | PASS for sampled 250k-line traces plus complete paired Arxiv s17 service-checked replays | `memory/dramsim3_summary.csv` |
| Ramulator2 | PASS for pair-4 traces plus complete Arxiv s7 online replay (33,779,460 requests accounted; forwarded reads included) | `memory/ramulator2_summary.csv` |
| CACTI 7 Docker | PASS | `results_hpca_xorflow/complete_suite/ppa/20260729T_local_ppa_v3/ppa_summary.csv` |
| Yosys | PASS for decoder lane/bank | same PPA summary |
| OpenROAD/ORFS Nangate45 | PASS for routed compact 8-lane decoder/support-cache cluster; 0 detailed-route DRC errors | `decoder/decoder_cluster_openroad_summary.json` |
| Encoder RTL engine/boundary | PASS for tile-scale support ingestion, exact XOR event discovery, dense/fixed-ID/Gap8 variable-length packing, descriptor offsets, candidate selection, and ready/valid stream equivalence | `encoder/encoder_synth.json`, `encoder/encoder_stream_cosim.log`, `encoder/stream_equivalence.csv` |
| Integrated 8-lane decoder/support-cache cluster | PASS synthesis + Verilator co-sim + OpenROAD route; physical-top serialized-stream VCD captured and 827 pins activity-annotated for a routed power report; this is not a full-workload energy result | `decoder/decoder_cluster_synth.json`, `decoder/decoder_cluster_cosim.log`, `decoder/vcd_or_saif/openroad_vcd_power.json` |

The prior routed decoder lane result is 0.00459 mm² at 1,458.88 MHz in the existing ORFS/Nangate45 evidence. The new cluster flow reports its own routed area/timing when available; neither is presented as a free linear estimate of a full host or encoder.

### Routed compact cluster record

The corrected hierarchical top has `0` detailed-route DRC errors, `13881` µm routed wire, `7748` vias, and a reported post-route clock slack of `0.565` ns at a 1.0 ns target. The die area is `68220.2161` µm² at the explicitly recorded `11.0%` core-utilization setting; this low utilization is the perimeter required by the compact control interface. The decoder/event buses are internal hierarchical nets, not package pins.

## Scope and remaining engineering work

1. The RTL encoder path has finite support ingestion/majority accumulation and a separate tile-scale stream engine with exact 2,048-bit event discovery, dense/fixed-ID/Gap8 bit packing, descriptor offsets, internal minimum candidate selection, and elastic output; no pass-through claim is made.
2. DRAMsim3 results distinguish sampled prefixes from complete traces in `memory/dramsim3_summary.csv`; no missing full timing run is silently promoted.
3. Real serialized-stream VCDs and transition summaries are in `encoder/vcd_or_saif`, `decoder/vcd_or_saif`, and `activity/vcd_summary.csv`. OpenROAD reports 827 annotated pins and 1.27e-02 W on the routed compact cluster for a real Arxiv s17 stream prefix; this is a prefix activity result, not full-workload energy.
4. `schedule/overlap_breakdown.csv`, `encoder/stream_equivalence.csv`, decoder-cluster co-simulation/synthesis logs, and the deterministic rerun ledger make the reviewer-facing accounting auditable.
5. Model-quality borderline cases (for example Yelp) remain visible and are not silently promoted to hard-valid.

## Reproduction

See `REPRODUCE_COMMANDS.txt`, `RESULT_MANIFEST.csv`, `audit/REPO_AUDIT.md`, and `traces/trace_manifest.csv`. The cached campaign itself was launched through four bounded CPU lanes using `scripts/run_spec_lane.sh`; GPU0 was untouched and GPU1 was reserved for genuine CUDA work.

Figures are in `figures/` as both PNG and PDF and are generated by `scripts/generate_reviewer_figures.py` directly from the frozen CSVs. The architecture panel is a schematic; all numerical panels retain their CSV sources.

No value here is a measured end-to-end accelerator speedup. The exact representation bytes, modeled event-driven subsystem cycles, and tool outputs are kept separate.

## Complete online Ramulator replay

This is a real HBM2 Ramulator run over the complete causal online replay transaction stream, not a pair or prefix sample. Read forwarding is counted as accounted service; no request is silently dropped.

| Configuration | Submitted 32-B requests | Accounted | DRAM cycles (after explicit drain) | Trace SHA-256 |
|---|---:|---:|---:|---|
| ogbn_arxiv_deepres8_w128_s7 | 33,779,460 | 33,779,460 | 33,779,459 | `b161aea24c9f56afb52ad021d78ef56d3dc03139ea1794f74fd628096237f462` |
| reddit_deepres8_w128_s7_native | 156,780,038 | 156,780,038 | 156,780,037 | `190f6384e72dd39eb908e3f5ae7fae3be2d08bd042a0e515931c4a1f02bf28d9` |

## Independent DRAMsim3 complete-input replay

The exact complete address traces were submitted to the pinned DRAMsim3 HBM2 model with the correct `address operation cycle` grammar, one request every eight feeder cycles, and an explicit modulo-8-GiB mapping into the configured HBM capacity. Served-request counts are reported explicitly; a run is not treated as fully drained unless `all_requests_served=true`.

| Trace | Input requests | Served | Fully drained | DRAM cycles | Elapsed s |
|---|---:|---:|---|---:|---:|
| ogbn_arxiv_deepres8_w128_s17_l4_beicsr | 18,866,826 | 18,866,827 | True | 250,000,000 | 518.1 |
| ogbn_arxiv_deepres8_w128_s17_l4_xorflow | 16,296,274 | 16,296,275 | True | 250,000,000 | 526.2 |
