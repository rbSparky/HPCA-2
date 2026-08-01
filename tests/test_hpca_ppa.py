"""Small parser/configuration checks for the reproducible subsystem PPA flow."""
from __future__ import annotations

from pathlib import Path

from scripts.run_hpca_ppa import _field, _write_cache_cfg


def test_cacti_config_is_45nm_and_has_exact_requested_capacity(tmp_path: Path) -> None:
    path = tmp_path / "cache.cfg"; _write_cache_cfg(path, 16 * 1024)
    text = path.read_text()
    assert "-size (bytes) 16384" in text
    assert "-technology (u) 0.045" in text
    assert "-block size (bytes) 64" in text


def test_openroad_and_cacti_numeric_fields_parse_without_units() -> None:
    assert _field(r"Design area\s+([0-9.eE+-]+)\s+um\^2", "Design area 4590 um^2 38% utilization.") == 4590.0
    assert _field(r"Access time \(ns\):\s*([0-9.eE+-]+)", "Access time (ns): 0.42") == 0.42
