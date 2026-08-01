# XORFLOW Round 14 - HPCA submission package

This lean package contains the revised manuscript, supplementary appendix, vector figures, bibliography, source tables needed to audit the principal claims, the final shared-memory scheduler source, and compact build/audit reports.

## Build

The PDF sources use the included versioned vector figures, so the paper can be built without regenerating plots:

```bash
make main
make supplement
```

Optional figure regeneration for the primary result, lifecycle validation, learned-structure, and hardware-scope figures requires Python with pandas, NumPy, and Matplotlib:

```bash
make figures
```

Run the compact result checks with:

```bash
make test
make preflight
```

## Principal verified results

- Ten outcome-independent eight-layer checkpoints use one common scheduler and host configuration.
- Mean serialized-support reduction: 37.05%.
- Mean complete physical-traffic reduction: 7.94%.
- Modeled aggregation-combination-subsystem speedup: 1.083x trace-weighted geometric mean, 1.076x dataset-balanced geometric mean, and 1.279x maximum; eight of ten checkpoints improve.
- Flickr seeds 17 and 27 are included and report 0.996x and 0.975x.
- One persistent eight-channel memory resource serves producer reads, consumer reads, and writebacks through a separate 32-entry request queue.
- Every combination shape uses the versioned 32x32 weight-stationary SCALE-Sim cache.
- A timing scale fitted only on Flickr seed 7 predicts the held-out Flickr seed 17 Ramulator2 completion with 0.453% absolute error.
- A mapped 1,055-cell tile front end and a routed eight-lane consumer cluster provide bounded implementation evidence. The full Dense/ID/Gap8 stream packer is functionally represented in RTL but has no mapped PPA result; the manuscript does not claim one.

## Result provenance

`results_used/review5_final2/results/primary_combined.csv` is the source of the main result figure and all ten primary timing rows. `heldout_absolute_memory_validation.csv` and `scalesim_shape_cache.json` support the memory and combination validation. The compact `reports/RESULT_MANIFEST.json` records SHA-256 hashes for every retained package file.

## Submission field

Replace `XXX` in `\hpcasubmissionnumber` with the assigned HPCA submission number before submission.

## Compilation

Run `pdflatex main.tex` twice to compile the paper from the included `main.bbl` bibliography, and run `pdflatex supplement.tex` twice to compile the supplementary appendix. To regenerate the bibliography after changing `refs.bib`, run `bibtex main` between the first and second `pdflatex` passes.
