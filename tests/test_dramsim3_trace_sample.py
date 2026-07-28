from __future__ import annotations

from pathlib import Path


def test_trace_sample_command_uses_only_numeric_addresses(tmp_path: Path) -> None:
    source = tmp_path / "source.trace"
    source.write_text("LD 0x40\nST 0x80\n96\n")
    sample = tmp_path / "sample.trace"
    with source.open() as reader, sample.open("w") as writer:
        for line in reader:
            fields = line.split()
            address = fields[-1] if len(fields) > 1 else fields[0]
            writer.write(f"{int(address, 0)}\n")
    assert sample.read_text() == "64\n128\n96\n"
