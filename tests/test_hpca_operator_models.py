from __future__ import annotations

import torch

from mosaic_validation.int8_validation import make_int8_model
from mosaic_validation.models import build_model


def test_residual_operator_models_preserve_trace_contract_under_fp8() -> None:
    edge_index = torch.tensor([[0, 1, 2, 2], [1, 2, 0, 1]], dtype=torch.long)
    x = torch.randn(3, 5)
    for kind in ("graphsage", "gin"):
        model = build_model(kind, 5, 8, 3, 3, 0.2).eval()
        logits, traces = model(x, edge_index, trace=True)
        fp8_logits, fp8_traces = make_int8_model(model, value_format="fp8", weight_format="fp16")(x, edge_index, trace=True)
        assert logits.shape == fp8_logits.shape == (3, 3)
        assert len(traces) == len(fp8_traces) == 3
        assert all(trace.shape == (3, 8) for trace in fp8_traces)
