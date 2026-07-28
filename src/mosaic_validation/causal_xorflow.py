"""Causal, independently decodable XORFLOW support segments.

The paper-facing format intentionally uses a two-layer segment.  Once layer
``l`` has completed, its support is available without predicting the future;
it becomes the persistent anchor for layer ``l + 1``.  The second support is
represented as a fixed-gap8 XOR event stream.  Thus every decoder needs only
the segment anchor and the current layer's stream, never a predecessor state
or a future activation mask.

This module is deliberately separate from the older offline-majority encoder.
The latter remains useful as an upper bound, but is not a deployable result.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from .hardware_gap import HardwareEventCode, encode_hardware_event_set
from .xorflow import prototype_dictionary


@dataclass(frozen=True)
class CausalSpatialDictionary:
    """Stored causal anchor dictionary, including enough state to decode it."""

    variant: str
    rows: int
    features: int
    bits: int
    row_codes: tuple[HardwareEventCode, ...] = ()
    cohort_prototypes: tuple[np.ndarray, ...] = ()
    cohort_residuals: tuple[tuple[HardwareEventCode, ...], ...] = ()

    def decode(self) -> np.ndarray:
        """Reconstruct the exact anchor without consulting a raw mask."""
        if self.variant == "A0_INDEPENDENT_ROWS":
            return np.stack([code.decode() for code in self.row_codes])
        pieces: list[np.ndarray] = []
        for prototype, residuals in zip(self.cohort_prototypes, self.cohort_residuals, strict=True):
            pieces.extend([prototype ^ code.decode() for code in residuals])
        return np.stack(pieces) if pieces else np.zeros((0, self.features), dtype=bool)


@dataclass(frozen=True)
class CausalPairEncoding:
    """Exact support representation for a causal two-layer tile/slice."""

    anchor: np.ndarray
    exception: HardwareEventCode
    anchor_variant: str
    prototype_count: int
    anchor_bits: int
    selector_bits: int
    spatial_dictionary: CausalSpatialDictionary
    independently_decodable: bool = True

    @property
    def exception_bits(self) -> int:
        return int(self.exception.encoded_bits)

    @property
    def encoded_support_bits(self) -> int:
        return int(self.anchor_bits + self.exception_bits + self.selector_bits)

    def decode_anchor_layer(self) -> np.ndarray:
        """Decode layer ``l`` from its own stored anchor support."""
        return self.spatial_dictionary.decode()

    def decode_exception_layer(self) -> np.ndarray:
        """Decode layer ``l+1`` without replaying any earlier exception."""
        return self.anchor ^ self.exception.decode().reshape(self.anchor.shape)


@dataclass(frozen=True)
class CausalSelection:
    """Result of the legal current-support selector for one pair."""

    representation: str
    pair: CausalPairEncoding | None
    independent_support_bits: int

    @property
    def support_bits(self) -> int:
        if self.representation == "XORFLOW_CAUSAL":
            assert self.pair is not None
            return self.pair.encoded_support_bits
        return self.independent_support_bits


def _validate_pair(layers: np.ndarray) -> np.ndarray:
    value = np.asarray(layers, dtype=bool)
    if value.ndim != 3 or value.shape[0] != 2:
        raise ValueError("a causal XORFLOW segment must have shape (2, rows, features)")
    return value


def build_causal_spatial_dictionary(anchor: np.ndarray, *, cohort_size: int) -> CausalSpatialDictionary:
    """Choose hardware-simple independent rows or fixed cohort prototypes.

    Unlike the offline A1 clustering experiment, this builder has bounded,
    causal construction cost: every fixed topology cohort receives exactly one
    majority prototype computed from the just-produced anchor layer.  It is a
    realistic datapath rather than an iterative clustering oracle.
    """
    rows = np.asarray(anchor, dtype=bool)
    row_codes = tuple(encode_hardware_event_set(row) for row in rows)
    independent = sum(code.encoded_bits for code in row_codes) + 16 * len(rows)
    cohort_bits = 0
    prototypes: list[np.ndarray] = []
    residual_sets: list[tuple[HardwareEventCode, ...]] = []
    for start in range(0, len(rows), cohort_size):
        local = rows[start:start + cohort_size]
        # k=1 converges to the deterministic bitwise majority prototype.
        dictionary = prototype_dictionary(local, 1)
        residuals = tuple(encode_hardware_event_set(residual) for residual in dictionary["residual"])
        residual_bits = sum(code.encoded_bits for code in residuals)
        cohort_bits += int(dictionary["prototypes"].size) + residual_bits + 16
        prototypes.append(dictionary["prototypes"][0].copy())
        residual_sets.append(residuals)
    if cohort_bits < independent:
        return CausalSpatialDictionary(
            variant="A2_CAUSAL_COHORT", rows=len(rows), features=rows.shape[1], bits=int(cohort_bits),
            cohort_prototypes=tuple(prototypes), cohort_residuals=tuple(residual_sets),
        )
    return CausalSpatialDictionary(
        variant="A0_INDEPENDENT_ROWS", rows=len(rows), features=rows.shape[1], bits=int(independent),
        row_codes=row_codes,
    )


def encode_causal_pair(
    layers: np.ndarray,
    *,
    cohort_size: int = 32,
    selector_bits: int = 8,
) -> CausalPairEncoding:
    """Encode a causal two-layer support segment exactly.

    ``layers[0]`` is the anchor because it is available after the first layer
    completes.  This function does not inspect a third or later layer, which
    makes the causality boundary easy to audit in tests and hardware traces.
    """
    value = _validate_pair(layers)
    anchor = value[0].copy()
    delta = np.logical_xor(value[1], anchor).reshape(-1)
    event = encode_hardware_event_set(delta)
    dictionary = build_causal_spatial_dictionary(anchor, cohort_size=cohort_size)
    return CausalPairEncoding(
        anchor=anchor,
        exception=event,
        anchor_variant=dictionary.variant,
        prototype_count=len(dictionary.cohort_prototypes),
        anchor_bits=int(dictionary.bits),
        selector_bits=int(selector_bits),
        spatial_dictionary=dictionary,
    )


def beicsr_pair_support_bits(layers: np.ndarray, *, row_descriptor_bits: int = 16) -> int:
    """Faithful bitmap support bits for two independently decodable layers.

    Values are accounted by the physical-layout model.  This returns support
    metadata only: one bitmap per row plus a fixed row-slice descriptor.
    """
    value = _validate_pair(layers)
    _, rows, features = value.shape
    bitmap = rows * features
    descriptors = rows * int(row_descriptor_bits)
    return int(2 * (bitmap + descriptors))


def select_causal_pair(layers: np.ndarray, *, cohort_size: int = 32) -> CausalSelection:
    """Choose the legal minimum known after the second support is produced.

    The fallback is independently decodable BEICSR.  A tie goes to the
    fallback, avoiding speculative format selection without a measurable gain.
    """
    pair = encode_causal_pair(layers, cohort_size=cohort_size)
    independent = beicsr_pair_support_bits(layers)
    if pair.encoded_support_bits < independent:
        return CausalSelection("XORFLOW_CAUSAL", pair, independent)
    return CausalSelection("BEICSR_INDEPENDENT", None, independent)


def causal_pair_statistics(layers: np.ndarray, *, cohort_size: int = 32) -> dict[str, float | int | str | bool]:
    """Return auditable exact accounting for reports and logs."""
    pair = encode_causal_pair(layers, cohort_size=cohort_size)
    selected = select_causal_pair(layers, cohort_size=cohort_size)
    exception_nnz = int(np.count_nonzero(pair.exception.decode()))
    return {
        "representation": selected.representation,
        "anchor_variant": pair.anchor_variant,
        "prototype_count": pair.prototype_count,
        "anchor_bits": pair.anchor_bits,
        "exception_bits": pair.exception_bits,
        "selector_bits": pair.selector_bits,
        "encoded_support_bits": pair.encoded_support_bits,
        "independent_support_bits": selected.independent_support_bits,
        "support_ratio_to_beicsr": pair.encoded_support_bits / max(selected.independent_support_bits, 1),
        "exception_density": exception_nnz / max(pair.anchor.size, 1),
        "independently_decodable": pair.independently_decodable,
        "exact_decode_pass": bool(
            np.array_equal(pair.decode_anchor_layer(), np.asarray(layers, dtype=bool)[0])
            and np.array_equal(pair.decode_exception_layer(), np.asarray(layers, dtype=bool)[1])
        ),
    }
