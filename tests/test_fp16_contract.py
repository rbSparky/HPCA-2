import torch

from mosaic_validation.int8_validation import quantize_weights_fp16
from mosaic_validation.models import build_deepres_v2


def test_fp16_storage_rounding_is_deterministic_and_keeps_fp32_parameter_dtype():
    model = build_deepres_v2(4, 8, 3, 2, .2, .2)
    first = quantize_weights_fp16(model)
    second = quantize_weights_fp16(model)
    assert next(first.parameters()).dtype == torch.float32
    for left, right in zip(first.parameters(), second.parameters(), strict=True):
        assert torch.equal(left, right)
