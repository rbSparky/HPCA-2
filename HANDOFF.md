# MOSAIC-GNN Phase-0 handoff

## Outcome

The predeclared project decision is:

`ITERATE_METHOD_BEFORE_SIMULATOR`

See `results/RESULTS.md` for the configuration decisions, gate evidence, and
scientific interpretation. Analytical proxy speedups are not measured hardware
speedups.

## Reproduce

The run reuses the existing Python 3.11 environment by default:

```bash
bash scripts/run_quick.sh
```

Set `MOSAIC_PYTHON` to use another compatible interpreter. The runner sets
`CUBLAS_WORKSPACE_CONFIG=:4096:8`, runs tests first, attempts all four required
configurations, and exits nonzero only for implementation/environment failures.

Downloaded datasets are cached under `data/` and are intentionally excluded
from this handoff archive. SCALE-Sim should be restored from official tag
`v3.0.0` at commit `7fd972e7c650e81c77294c9433143a282235c5e7` and installed
editable. With NumPy 2.x, apply the documented compatibility change in
`double_buffered_scratchpad_mem.py`:

```python
self.total_cycles = int(np.max(ofmap_serviced_cycles))
```

## Important files

- `AGENTS.md`: authoritative specification and predeclared gates.
- `configs/quick.yaml`: executed configuration.
- `src/mosaic_validation/`: modular implementation.
- `tests/`: correctness tests.
- `results/RESULTS.md`: final report.
- `results/00_environment.csv` through `results/07_failures.csv`: evidence.
- `results/SCALESIM_SMOKE.md`: dense smoke command and output.
- `results/results_bundle.zip`: results-only portable bundle.
- `results/checkpoint_hashes.txt`: checkpoint identities.

## Known blocker

The residual-GCN architecture-transfer configuration reached test accuracy
0.631, below the predeclared 0.65 floor, and is therefore `INVALID_MODEL`.
Both valid homophilic GCNII configurations reached only `AMBER` on the cohort
gate, so deeper simulator implementation is not yet justified.
