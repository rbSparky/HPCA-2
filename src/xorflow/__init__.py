"""Deployable XORFLOW experiment implementation.

This package contains the frozen byte grammar and the causal, single-pass
experiments requested by ``XORFLOW_EXPERIMENT_EXECUTION_SPEC.md``.  It is kept
separate from the historical analytical models in :mod:`mosaic_validation` so
paper-facing results cannot accidentally use an offline pair selector.
"""

from .serializer import Codec, DecodedRecord, SerializedRecord, decode_record, serialize_record

__all__ = [
    "Codec",
    "DecodedRecord",
    "SerializedRecord",
    "decode_record",
    "serialize_record",
]
