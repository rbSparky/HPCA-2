# MOSAIC-GNN Phase-0 validation

This repository implements the predeclared one-seed kill test in `AGENTS.md`.
It records exact post-ReLU supports and evaluates spatial coherence, temporal
persistence, exact cohort templates, transfer-byte proxies, and irregular-cost
proxies. Proxy speedups are analytical quantities, not measured hardware
speedups.

Run the complete suite with:

```bash
bash scripts/run_quick.sh
```

The scripts default to the reusable `taugat_pyg` Conda environment when it is
available. Set `MOSAIC_PYTHON` to select another Python interpreter.

