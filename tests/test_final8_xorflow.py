import numpy as np
import torch

from mosaic_validation.final8_cli import _cache_sim, _line_trace
from mosaic_validation.int8_validation import fake_quant_fp8
from mosaic_validation.xorflow import decode_slice, encode_slice


def test_fp8_is_one_byte_and_preserves_typical_relu_support():
    x = torch.tensor([[0.0, 0.125, 1.0, 8.0]])
    q = x.to(torch.float8_e4m3fn)
    assert q.element_size() == 1
    rebuilt = fake_quant_fp8(x)
    assert torch.equal(rebuilt > 0, x > 0)


def test_final8_line_trace_matches_explicit_ranges():
    mask = np.array([[1, 0, 1, 0], [1, 1, 1, 1]], dtype=bool)
    sources = np.array([0, 1, 0], dtype=np.int64)
    trace, layout = _line_trace(mask, sources, 4, "beicsr")
    assert len(trace) == 3
    assert layout["row_slices"] == 2


def test_final8_lru_is_deterministic():
    lines = np.array([0, 1, 0, 2, 1, 0], dtype=np.int64)
    first = _cache_sim(lines, 128, 2)
    second = _cache_sim(lines, 128, 2)
    assert first == second
    assert first[0] == len(lines)


def test_final8_real_size_encoder_roundtrip():
    masks = np.random.default_rng(7).random((5, 17, 64)) > 0.4
    encoded = encode_slice(masks, 0, 64)
    assert encoded["exact"]
    assert np.array_equal(decode_slice(encoded), masks)
