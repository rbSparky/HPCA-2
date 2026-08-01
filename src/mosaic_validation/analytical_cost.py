"""Exact representation and analytical proxy cost calculations."""

import math

import numpy as np

from .cohorts import CohortSet


def _align64(value: int) -> int:
    return int(math.ceil(value / 64) * 64) if value else 0


def representation_metrics(mask: np.ndarray, cohorts: CohortSet) -> dict[str, float]:
    n, width = mask.shape
    total_nnz = int(mask.sum())
    core_slots = core_true = holes = residual = mosaic_bytes = 0
    template_features = []
    sizes = []
    for group, template in zip(cohorts.groups, cohorts.templates, strict=True):
        rows = mask[group]
        m = len(group)
        template_count = int(template.sum())
        group_core_slots = m * template_count
        group_core_true = int(rows[:, template].sum()) if template_count else 0
        group_residual = int(np.logical_and(rows, ~template).sum())
        core_slots += group_core_slots
        core_true += group_core_true
        holes += group_core_slots - group_core_true
        residual += group_residual
        mosaic_bytes += (
            _align64(4 * group_core_slots)
            + _align64(6 * group_residual + 4 * (m + 1))
            + _align64(2 * template_count + m)
        )
        template_features.append(template_count)
        sizes.append(m)
    dense = n * _align64(4 * width)
    row_nnz = mask.sum(axis=1)
    bitmap = sum(_align64(math.ceil(width / 8) + 4 * int(value)) for value in row_nnz)
    best_bytes = min(dense, bitmap)

    def proxy(rho: float) -> float:
        baseline = min(n * width, rho * total_nnz)
        cost = core_slots + rho * residual
        return baseline / cost if cost else 1.0

    break_even = float("nan")
    for rho in np.arange(1.0, 8.001, 0.01):
        if proxy(float(rho)) > 1.0:
            break_even = float(round(rho, 2))
            break
    return {
        "num_cohorts": len(cohorts.groups),
        "mean_cohort_size": float(np.mean(sizes)),
        "mean_template_features": float(np.mean(template_features)),
        "total_nnz": total_nnz,
        "core_true_nnz": core_true,
        "core_slots": core_slots,
        "holes": holes,
        "residual_nnz": residual,
        "regular_capture": core_true / total_nnz if total_nnz else 0.0,
        "padding_fraction": holes / core_slots if core_slots else 0.0,
        "residual_fraction": residual / total_nnz if total_nnz else 0.0,
        "dense_transfer_bytes": dense,
        "bitmap_sparse_transfer_bytes": bitmap,
        "mosaic_transfer_bytes": mosaic_bytes,
        "mosaic_to_best_byte_ratio": mosaic_bytes / best_bytes if best_bytes else 1.0,
        "proxy_speedup_rho1_5": proxy(1.5),
        "proxy_speedup_rho2": proxy(2.0),
        "proxy_speedup_rho3": proxy(3.0),
        "proxy_speedup_rho4": proxy(4.0),
        "break_even_rho": break_even,
    }


def payload_cost(mask: np.ndarray, cohorts: CohortSet) -> int:
    cost = 0
    for group, template in zip(cohorts.groups, cohorts.templates, strict=True):
        cost += 4 * len(group) * int(template.sum()) + 2 * int(template.sum())
        cost += 6 * int(np.logical_and(mask[group], ~template).sum())
    return cost

