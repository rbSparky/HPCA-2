# XORFLOW Repository and Input Audit

Git revision: `2670d32f16332b982df6572b99a4b588819eff3d` (`gem`). This audit preserves all historical phase results and uses cached traces/checkpoints without retraining.

## Resolved implementation contracts

- **Residual ordering:** `DeepResV2` applies `LayerNorm(h) -> ReLU -> trace/quantize -> dropout -> GCNConv -> h + residual_scale*z`. The recorded tensor is the quantized post-ReLU tensor consumed by the convolution.
- **Projection:** the input feature dimension is projected once by `Linear(num_features,width)`; residual blocks are fixed width, so no hidden per-block projection occurs.
- **Graph semantics:** model execution uses the dataset edge stream and `GCNConv(cached=True, add_self_loops=True, normalize=True)`. Analysis symmetrizes edges only for Reverse Cuthill--McKee ordering. Replay preserves original node IDs and edge arithmetic while using 128-row RCM topology tiles.
- **Trace contract:** packed NPZ traces contain exact nonzero support of FP8 E4M3 post-ReLU activations in layer-production order. Checkpoint, config, trace, and source hashes are inventoried.
- **BEICSR:** historical physical layout is implemented in `mosaic_validation.memory_subsystem`; reviewer replay uses the frozen byte-producing BEICSR bitmap record in `xorflow.serializer`, with identical FP8 values and 64-byte alignment across compared formats.
- **Producer contract:** the finite-queue model uses the existing 32x64-bit (2,048-bit/cycle) producer sensitivity point and reports achieved rates under ready/valid backpressure rather than assuming peak throughput.
- **Memory:** common host uses 64-byte cache lines, 512 KiB 16-way LRU feature cache, eight-channel HBM2, two 32-byte transactions per line, 256 GB/s at 1 GHz. Full config/version evidence is retained under the prior timing campaign and copied into the final bundle.
- **Decoder provenance:** `rtl/xorflow_decoder_pipelined.sv` is the routed one-lane source. It is evidence for the lane only; the new integrated cluster is separately modeled/synthesized and is not inferred by multiplying lane PPA.

## Reconstructed or newly frozen

- The prior analytical event accounting did not define a parseable byte stream. `xorflow.serializer` now freezes bit order, headers, field widths, tie rules, zero padding, malformed behavior, and the 16-byte offset table.
- The prior pair-complete selector was future dependent. `xorflow.online_replay` now commits every anchor before reading its target and emits decision events plus a future-mutation causality test.

## Unavailable inputs

- Historical full-precision activation tensors and packed value contents were intentionally not retained. Exact value byte counts and addresses are reproducible from support NNZ, but value-bit payload hashes cannot be reconstructed.
- Original trace-capture start timestamps are absent; file completion times are recorded.
- A full common-host floorplan is unavailable, so host-relative area/power percentages must remain unclaimed unless the new integrated flow establishes them.
