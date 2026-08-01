from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_dramsim3_runner_emits_operation_and_cycle_fields() -> None:
    source = (ROOT / "scripts/run_dramsim3_full_trace.py").read_text()
    assert 'dram_op = "WRITE"' in source
    assert "mapped = address % args.capacity_bytes" in source
    assert "arrival = converted_lines * args.arrival_stride" in source
    assert 'tmp.write(f"0x{mapped:x} {dram_op} {arrival}\\n")' in source
    assert "--arrival-stride" in source
    assert "all_requests_served" in source
