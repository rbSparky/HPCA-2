"""Cycle-accurate check for the throughput-preserving XORFLOW pipeline."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def test_pipelined_decoder_matches_software_reference() -> None:
    if shutil.which("verilator") is None:
        raise RuntimeError("Verilator is required for the XORFLOW RTL co-simulation gate")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([str(root / "scripts/run_xorflow_decoder_cosim.sh")], cwd=root, text=True, capture_output=True, check=True)
    assert "PASS cycles=9999 seed=7 latency=1 throughput_words_per_cycle=1" in result.stdout
