# Producer packer

Reused unchanged mapped evidence: the 2,048-bit tile engine implements majority accumulation, XOR discovery, dense/fixed-ID/Gap8 candidates, exact length selection, descriptor offsets, alignment, finite ready/valid buffering, and real-stream equivalence. The mapped boundary has 810 Yosys cells and the full engine 1,055 cells. Golden software/RTL stream hashes agree on every retained directed test. Measured per-trace achieved rates, rather than nominal lane width, remain the inputs to the scheduler. See `results/hardware/encoder_synth.json` and `stream_equivalence.csv`.
