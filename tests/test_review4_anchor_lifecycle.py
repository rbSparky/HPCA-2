from __future__ import annotations

from xorflow.review4_acceptance import classify


def _rows(fmt: str = "DELTA") -> list[dict[str, str]]:
    common = {"run_id": "tiny", "dataset": "tiny", "seed": "7", "pair_id": "0", "tile": "0", "slice": "0", "input_support_bits": "16384"}
    return [
        {**common, "layer": "0", "role": "anchor", "chosen_format": "A2", "padded_bytes": "128", "payload_bits": "900", "header_bits": "16", "anchor_read_bytes": "0"},
        {**common, "layer": "1", "role": "target", "chosen_format": fmt, "padded_bytes": "64", "payload_bits": "400", "header_bits": "16", "anchor_read_bytes": "128"},
    ]


def test_consumer_eviction_forces_exact_padded_reread() -> None:
    result = classify(_rows(), capacity=1024, rate=64.0)[0]
    assert result["consumer_anchor_source"] == "MEMORY_REREAD"
    assert result["consumer_anchor_read_bytes"] == 128
    assert result["consumer_anchor_decode_cycles"] > 0


def test_consumer_residency_is_independent_of_producer_miss() -> None:
    result = classify(_rows(), capacity=4096, rate=64.0)[0]
    assert result["producer_anchor_read_bytes"] == 128
    assert result["consumer_anchor_source"] == "CONSUMER_RESIDENT_DECODED"
    assert result["consumer_anchor_read_bytes"] == 0


def test_independent_target_requires_no_consumer_anchor() -> None:
    result = classify(_rows("BEICSR"), capacity=0, rate=64.0)[0]
    assert result["consumer_anchor_source"] == "NOT_REQUIRED_INDEPENDENT_TARGET"
    assert result["consumer_anchor_read_bytes"] == 0
    assert result["consumer_anchor_decode_cycles"] == 0
