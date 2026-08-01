# XORFLOW: Anonymous Supplementary Artifact (Submission 1467)

This archive contains the core exact support-streaming implementation, RTL and
software validation harnesses, and a compact subset of audited XORFLOW results.
It is prepared for anonymous review and contains no raw datasets, checkpoints,
third-party histories, transient queue logs, automation notes, or machine-local paths.

## Contribution

XORFLOW stores an exact topology-local support anchor, independently decodable
XOR exception streams, packed activation values, and a tile-local reconstructed
support cache. The causal schedule uses finite queues, explicit producer,
memory, decoder, aggregation, combination, and writeback dependencies, memory
completion, layer barriers, fill/drain, and anchor recovery accounting.

## Included material

- `src/xorflow/`: causal serializer, online replay, encoder/decoder and traffic models.
- `src/mosaic_validation/`: supporting exact codecs, null controls, host and tool bridges.
- `rtl/`: encoder/decoder RTL and software/RTL testbenches.
- `tests/`: correctness and schedule/resource tests.
- `configs/`: reproducible experiment configurations.
- `results/`: compact audited result tables and selected RTL/toolchain evidence.

## Results scope

The results are exact serialized bytes and modeled aggregation+combination
subsystem cycles. They are not measured end-to-end GNN accelerator speedups.
Negative and near-parity workloads are retained. Tile-scale producer and routed
decoder-cluster evidence are reported separately; all modeled-cycle claims are
scoped to the evaluated aggregation--combination subsystem.

## Reproduction

Install the dependencies from `pyproject.toml`, set `PYTHONPATH=src`, then run
the focused tests with `pytest -q tests/test_xorflow_core.py tests/test_causal_schedule.py
tests/test_xorflow_serializer.py tests/test_rtl_integration.py`.
The selected CSV/JSON artifacts under `results/` are the source for the tables.
