# XORFLOW safe-zone handoff

Decision: `SAFE_ZONE_PROCEED_TO_PAPER_READY_XORFLOW_SUITE`

## Bottom line

The regular systolic path remains stopped. The sparse aggregation-memory
direction is now supported by exact decoding, a synthesizable parallel
decoder, matched-density controls, three independent training seeds, and real
HBM2 timing. The strongest result is the valid 169,343-node OGBN-Arxiv trace:
1.398x double-buffered and
1.390x fully serialized aggregation-memory speedup
against an equally channel-colored BEICSR baseline.

The fixed-model Arxiv prefix sweep rises monotonically from
1.058x at
4,096 nodes to
1.353x at
169,343 nodes. At matched density, the independent null
uses 1.79x
the trained trace's support bits. Treat these as separate scale and
learned-structure controls.

## Reproduce

Use the existing environment:

```bash
MOSAIC_PY=/home/rishabh/miniconda/envs/taugat_pyg/bin/python
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=src "$MOSAIC_PY" -m pytest -q
bash scripts/synth_decoder.sh
PYTHONPATH=src "$MOSAIC_PY" scripts/safezone_stream_audit.py
PYTHONPATH=src "$MOSAIC_PY" scripts/safezone_dram_traces.py
"$MOSAIC_PY" scripts/safezone_parse_dram.py
"$MOSAIC_PY" scripts/safezone_report.py
```

The cached deterministic report command was run twice; hashes are in
`artifacts_safezone/repro_run1.sha256` and
`artifacts_safezone/repro_run2.sha256`.

## Environment and integrity

- Python: `/home/rishabh/miniconda/envs/taugat_pyg/bin/python`
- PyTorch: `2.8.0+cu128`; PyG: `2.6.1`; NumPy: `2.4.4`
- Device: NVIDIA GeForce RTX 4060 Laptop GPU
- RTL synthesis/formal: YoWASP Yosys 0.67
- Ramulator 2.1 commit:
  `99a0e1e87a9321587492fef5b0bd6197928f8d68`
- Ramulator uses HBM2, eight channels, two 32-byte transactions per 64-byte
  cache line, and a fixed 4096-cycle drain. Identical drain time is subtracted
  from both formats. Every reported row verifies submitted requests equal
  served requests.
- Earlier result files remain unmodified in Git status.

Raw OGBN-Arxiv data, generated DRAM request traces, Conda environments,
third-party Git history, and redundant checkpoints are intentionally excluded
from the portable archive. The compact CSV timing outputs, trace hashes,
commands, source, tests, and synthesis logs are included.
