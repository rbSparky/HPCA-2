# MOSAIC rescue audit handoff

The forensic audit confirms that Phase-3A's reported layer-local oracle was
misnamed and incorrectly omitted the dense fallback. It also found an
optimistic residual-output accounting omission. Correcting these issues does
not rescue the FP32 regular-panel architecture.

The audit tested a potentially favorable reconfigurable mapping using the same
1,024 MACs as 1x32x32, 4x16x16, and 16x8x8 arrays. Real SCALE-Sim shape cycles,
per-layer barriers, deterministic task scheduling, and all residual/gather/
decode/accumulation charges were retained. The panel mapping appears favorable
against the old monolithic dense baseline, but loses once dense execution is
given the same subarray flexibility. The fair speedups are 1.020 on Cora, 0.744
on PubMed, and 0.899 on valid DeepRes.

FP32 XORFLOW is also structurally constrained: even free support metadata gives
only 1.040, 1.046, and 1.071 logical-format upper bounds on those traces.

The sole remaining hypothesis with credible headroom is INT8 XORFLOW. Using
observed Phase-2 anchor metadata ratios projects logical-format speedups of
1.046 on Cora, 1.064 on PubMed, and 1.093 on DeepRes. These are projections, not
measured results. A final INT8 experiment must validate accuracy and exact
cache-line traffic against INT8 BEICSR; FP32 XORFLOW and regular panels should
not receive another iteration.

Reproduce:

```bash
PYTHONPATH=src /home/rishabh/miniconda/envs/taugat_pyg/bin/python -m mosaic_validation.rescue_audit --project .
PYTHONPATH=src PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /home/rishabh/miniconda/envs/taugat_pyg/bin/python -m pytest -q
```

The detailed report is `results_rescue_audit/RESCUE_AUDIT.md`.
