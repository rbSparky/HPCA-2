# MOSAIC-Delta Phase-1 handoff

Decision: `ITERATE_DELTA_ENCODING`

Reproduce with `bash scripts/run_phase1.sh`. Phase-0 masks and datasets are
discovered from the sibling `mosaic_validation` project. New models are trained
only when packed Phase-1 traces are missing. See `results_phase1/PHASE1_RESULTS.md`
and the exact CSVs for evidence. Dataset names, file checksums, and PyG download
sources are recorded in `results_phase1/dataset_manifest.csv`; raw datasets are
excluded from the archive. Analytical proxies are not measured speedups.

The exactness, runtime/reproducibility, sparse-target, null-control, and
robustness gates passed. Economics and cohort locality were amber. The temporal
compression gate failed because principal metadata ratios remained 0.690 for
Cora and 0.625 for PubMed, although greedy segment lengths were 3.25 layers and
greedy costs were within roughly 0.15% of offline DP. The next iteration should
reduce transition metadata rather than relax these thresholds.

Cora `deepres_v2` was valid at 0.757 test accuracy and median density 0.452.
PubMed used the single permitted fallback but remained invalid at 0.732 versus
the predeclared 0.75 floor; both attempts remain in the quality table.
