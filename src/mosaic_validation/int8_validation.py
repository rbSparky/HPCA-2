"""INT8 value validation for the final MOSAIC-XORFLOW kill test."""
from __future__ import annotations

import copy
import types
import torch
from torch import nn

from .models import GCNII, DeepResV2


def fake_quant_signed(x: torch.Tensor, bits: int = 8) -> torch.Tensor:
    """Symmetric dynamic fake quantization with an FP32 return tensor."""
    bound = (1 << (bits - 1)) - 1
    # Activations are calibrated per feature channel. This is a standard,
    # deployable granularity and avoids one outlier node setting the scale for
    # an entire graph.
    maximum = (
        x.detach().abs().amax(dim=0, keepdim=True)
        if x.ndim == 2
        else x.detach().abs().amax()
    )
    if torch.all(maximum == 0):
        return x
    scale = torch.where(maximum > 0, maximum / bound, torch.ones_like(maximum))
    return torch.clamp(torch.round(x / scale), -bound, bound) * scale


def fake_quant_relu_preserve_support(x: torch.Tensor, bits: int = 8) -> torch.Tensor:
    """Unsigned ReLU quantization that keeps every positive support bit active."""
    bound = (1 << bits) - 1
    maximum = x.detach().amax(dim=0, keepdim=True) if x.ndim == 2 else x.detach().amax()
    if torch.all(maximum == 0):
        return x
    scale = torch.where(maximum > 0, maximum / bound, torch.ones_like(maximum))
    quant = torch.round(x / scale)
    quant = torch.where(x > 0, torch.clamp(quant, min=1, max=bound), quant)
    return quant * scale


def fake_quant_fp8(x: torch.Tensor) -> torch.Tensor:
    """E4M3 FP8 fake quantization for one-byte activation sensitivity."""
    return x.to(torch.float8_e4m3fn).to(x.dtype)


def quantize_weights(model: nn.Module) -> nn.Module:
    """Return a copy with signed INT8 fake-quantized matrix weights."""
    result = copy.deepcopy(model)
    with torch.no_grad():
        for name, parameter in result.named_parameters():
            # Normalization affine parameters and biases conventionally remain
            # at higher precision in INT8 inference.
            if parameter.ndim >= 2 and "norm" not in name:
                bound = 127
                maximum = parameter.detach().abs().amax(
                    dim=tuple(range(1, parameter.ndim)), keepdim=True
                )
                scale = torch.where(
                    maximum > 0, maximum / bound, torch.ones_like(maximum)
                )
                parameter.copy_(
                    torch.clamp(torch.round(parameter / scale), -bound, bound)
                    * scale
                )
    return result


def quantize_weights_fp16(model: nn.Module) -> nn.Module:
    """Round matrix weights to IEEE FP16 while preserving FP32 execution.

    This is a deterministic fake-FP16 contract: storage precision is FP16,
    while PyG kernels retain FP32 accumulation and avoid unsupported mixed
    dtype paths on CPU.  Every compared format receives this same rounding.
    """
    result = copy.deepcopy(model)
    with torch.no_grad():
        for name, parameter in result.named_parameters():
            if parameter.ndim >= 2 and "norm" not in name:
                parameter.copy_(parameter.detach().to(torch.float16).to(parameter.dtype))
    return result


def _gcnii_int8_forward(self, x, edge_index, trace=False):
    x0 = fake_quant_relu_preserve_support(self.input(x))
    x = x0
    traces = []
    for conv in self.convs:
        x = fake_quant_relu_preserve_support(conv(x, x0, edge_index))
        if trace:
            traces.append(x)
    logits = self.output(fake_quant_signed(x))
    return (logits, traces) if trace else logits


def _deepres_int8_forward(self, x, edge_index, trace=False):
    h = fake_quant_signed(self.input(x))
    traces = []
    for norm, conv in zip(self.norms, self.convs, strict=True):
        z = fake_quant_relu_preserve_support(norm(h))
        if trace:
            traces.append(z)
        update = fake_quant_signed(conv(z, edge_index))
        h = fake_quant_signed(h + self.residual_scale * update)
    z = fake_quant_relu_preserve_support(self.final_norm(h))
    logits = self.output(z)
    return (logits, traces) if trace else logits


def _gcnii_fp8_forward(self, x, edge_index, trace=False):
    x0 = fake_quant_fp8(torch.relu(self.input(x)))
    x, traces = x0, []
    for conv in self.convs:
        x = fake_quant_fp8(torch.relu(conv(x, x0, edge_index)))
        if trace:
            traces.append(x)
    logits = self.output(x)
    return (logits, traces) if trace else logits


def _deepres_fp8_forward(self, x, edge_index, trace=False):
    h = self.input(x)
    traces = []
    for norm, conv in zip(self.norms, self.convs, strict=True):
        z = fake_quant_fp8(torch.relu(norm(h)))
        if trace:
            traces.append(z)
        h = h + self.residual_scale * conv(z, edge_index)
    z = fake_quant_fp8(torch.relu(self.final_norm(h)))
    logits = self.output(z)
    return (logits, traces) if trace else logits


def _generic_stack_fp8_forward(self, x, edge_index, trace=False):
    """Quantized activation path for SAGE/GIN operator smoke and traces."""
    x = fake_quant_fp8(torch.relu(self.input(x))); traces = []
    for norm, conv in zip(self.norms, self.convs, strict=True):
        x = fake_quant_fp8(torch.relu(norm(x + conv(x, edge_index))))
        if trace: traces.append(x)
    logits = self.output(x)
    return (logits, traces) if trace else logits


def make_int8_model(model: nn.Module, quantize_model_weights: bool = False,
                    value_format: str = "uint8", weight_format: str = "fp32") -> nn.Module:
    """Create a support-preserving INT8-activation inference model.

    XORFLOW compresses feature values, not model parameters, so the principal
    experiment keeps weights at their original precision. Weight INT8 remains
    an optional, separately reported sensitivity.
    """
    if quantize_model_weights or weight_format == "int8":
        result = quantize_weights(model)
    elif weight_format == "fp16":
        result = quantize_weights_fp16(model)
    elif weight_format == "fp32":
        result = copy.deepcopy(model)
    else:
        raise ValueError(f"unsupported weight format: {weight_format}")
    if isinstance(result, GCNII):
        forward = _gcnii_fp8_forward if value_format == "fp8" else _gcnii_int8_forward
        result.forward = types.MethodType(forward, result)
    elif isinstance(result, DeepResV2):
        forward = _deepres_fp8_forward if value_format == "fp8" else _deepres_int8_forward
        result.forward = types.MethodType(forward, result)
    elif type(result).__name__ in {"SAGE8", "GIN8"}:
        result.forward = types.MethodType(_generic_stack_fp8_forward, result)
    else:
        raise TypeError(f"unsupported INT8 model: {type(result).__name__}")
    return result


@torch.no_grad()
def classification_accuracy(model: nn.Module, data, device: torch.device) -> dict[str, float]:
    model = model.to(device).eval()
    data = data.to(device)
    logits = model(data.x, data.edge_index)
    out = {}
    for split in ("train", "val", "test"):
        mask = getattr(data, f"{split}_mask")
        out[f"{split}_accuracy"] = float(
            (logits[mask].argmax(1) == data.y[mask]).float().mean()
        )
    return out
