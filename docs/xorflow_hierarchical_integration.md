# XORFLOW hierarchical decoder integration

The 32-lane decoder is not a package-level block. Its 2,048-bit ingress is
the internal stream between the HBM/metadata buffer and decoder macros; its
decoded events feed the tile-local support-cache builder. Treating all 8,577
signals as die-edge pins is therefore an invalid flat-PPA harness.

The implementation hierarchy is:

```text
HBM / metadata SRAM
        │ internal 2,048-bit stream
4 decoder clusters × 8 pipelined 64-bit lane macros
        │ decoded local events
tile-local support-cache builder
```

`xorflow_decoder_bank_pipelined` is the logical composition of 32 identical
lanes. Each lane accepts one 64-bit stream word every cycle, so the hierarchy
sustains 2,048 encoded input bits/cycle after a one-cycle pipeline fill. The
lane macro was fully routed at Nangate45 and closes a 1 GHz constraint with
0.31 ns WNS margin. Its routed area is 4,590 um²; a simple 32-lane area budget
is therefore 0.147 mm² before cluster-level clock, SRAM, and interconnect
overhead. No aggregate dynamic-power number is inferred by multiplying the
single-lane report, because switching activity must be annotated from real
streams at the cluster level.

The hierarchy is deliberately tested in two complementary ways:

- software/RTL co-simulation checks a lane for 9,999 cycle-aligned random
  input/output transactions at seed 7;
- lint checks `xorflow_decoder_bank_pipelined`, whose only data-path elements
  are the 32 independently verified lane instances.

Physical bank closure is a next integration step: lane macros must be placed
inside four local clusters with the HBM buffer and support-cache macros rather
than flattened into a pin-limited standalone die.
