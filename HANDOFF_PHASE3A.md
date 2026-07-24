# MOSAIC-PANEL Phase-3A handoff

Decision: `STOP_DEPTHWISE_REGULAR_PATH`.

Phase-3A completed the exact panel decomposition, real SCALE-Sim regular-path calibration, residual and accumulation accounting, controls, capacity checks, and required tests using the cached Phase-0/1/2 traces. No model was retrained. The calibrated deployable panel path did not reach a speedup on the principal traces, and the layer-local oracle was also below the predeclared stop thresholds. The support structure and transfer-byte reductions are genuine, but they do not justify a depthwise regular-GEMM accelerator or Phase-3B.

Reproduce from the repository root:

```bash
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/rishabh/miniconda/envs/taugat_pyg/bin/python -m pytest -q
PYTHONPATH=src /home/rishabh/miniconda/envs/taugat_pyg/bin/python -m mosaic_validation.phase3a_cli --config configs/phase3a_quick.yaml
```

The cached run used `/home/rishabh/miniconda/envs/taugat_pyg/bin/python`, PyTorch `2.8.0+cu128`, CUDA on an NVIDIA GeForce RTX 4060 Laptop GPU, and SCALE-Sim commit `7fd972e7c650e81c77294c9433143a282235c5e7`. Wall-clock was 5390.5 seconds; the user authorized the continuation runtime extension to 6750 seconds. The run reused existing masks/checkpoints and preserved all earlier phase evidence.

The report and all required tables/plots are in `results_phase3a/`; execution logs, environment data, hashes, and diffs are in `artifacts_phase3a/`. This phase reports exact bytes, SCALE-Sim regular GEMM cycles, analytical residual cycles, and a calibrated hybrid estimate—not end-to-end GNN accelerator measurements or energy results.
