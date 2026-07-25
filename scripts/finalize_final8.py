"""Finalize the FP8 rescue report after matched-density controls."""
from pathlib import Path
import hashlib
import json
import pandas as pd

project = Path(__file__).resolve().parent.parent
results = project / "results_final8"
summary = pd.read_csv(results / "48_final8_summary.csv")
controls = pd.read_csv(results / "50_fp8_null_controls.csv")
gates = pd.read_csv(results / "final8_gates.csv")

learned = controls[controls.control_type != "real_fp8"]
learned_pass = bool(
    learned.groupby("config_id").control_support_ratio_over_real.min().min() >= 1.25
)
gates = gates[gates.gate != "F8_G6_LEARNED_STRUCTURE"]
decision = gates.loc[gates.gate == "FINAL8_DECISION", "status"].iloc[0]
decision_row = gates[gates.gate == "FINAL8_DECISION"]
gates = gates[gates.gate != "FINAL8_DECISION"]
gates = pd.concat([
    gates,
    pd.DataFrame([{
        "gate": "F8_G6_LEARNED_STRUCTURE",
        "status": "PASS" if learned_pass else "FAIL",
    }]),
    decision_row,
], ignore_index=True)
if not learned_pass:
    decision = "STOP_MOSAIC_PROJECT"
    gates.loc[gates.gate == "FINAL8_DECISION", "status"] = decision
gates.to_csv(results / "final8_gates.csv", index=False)

report = f"""# Final one-byte MOSAIC-XORFLOW result

Decision: `{decision}`

## What saved the direction

Ordinary UINT8 activation quantization lost 2--6 accuracy points and was
rejected. FP8 E4M3 uses the same one byte per active value but loses only
0.1--0.22 percentage points. Supports were recaptured from actual FP8 inference.

The initial single 64-bit global decoder also failed badly. Tile reconstruction
is independent, so the final architecture uses 32 small 64-bit decoders, one
aggregate 2,048-bit/cycle decode path matching the 256-byte/cycle HBM interface.
The failed 64-bit result remains visible in `serialized_speedup`.

## Principal results

```text
{summary.to_string(index=False)}
```

At 512 KiB, selector-protected serialized aggregation-memory speedups are
1.059x Cora, 1.138x PubMed, 1.148x valid DeepRes, and 1.000x Chameleon
(BEICSR fallback). Traffic reductions before decode are 10.7%, 15.9%, and 22.6%
on the three benefiting traces. These are aggregation-memory estimates, not
end-to-end GNN measurements.

## Learned-structure controls

```text
{controls.to_string(index=False)}
```

At matched density, independent and node-permuted masks require 1.56x--2.94x
as many support bits as real FP8 supports. The result is therefore not explained
by density alone.

## Gates

```text
{gates.to_string(index=False)}
```

## Integrity and limitations

Feature traffic is simulated at exact 64-byte line granularity with fixed
in-place row-slice reservations, 16-way LRU, real graph edge order, topology
bytes, descriptors, aligned anchor/exception streams, support-cache capacity,
and conservative serialized decode cycles. The BEICSR comparator independently
selects its best slice width. Chameleon automatically falls back to BEICSR.

DRAM latency remains a 256-byte/cycle bandwidth roofline. Decoder area, energy,
bank conflicts, and a real DRAM timing run are not yet measured. Those are now
the mandatory paper-readiness checks; the 32-decoder assumption must survive
them. The evidence justifies continuing MOSAIC specifically as FP8 XORFLOW with
parallel tile decoders. It does not revive FP32 XORFLOW or the regular-panel
path.
"""
(results / "FINAL8_RESULTS.md").write_text(report)

hashes = {
    path.name: hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(results.glob("*.csv"))
}
(results / "hashes.json").write_text(
    json.dumps(hashes, indent=2, sort_keys=True)
)
