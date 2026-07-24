"""Temporal matching and conservative schedule reuse."""

import numpy as np
from scipy.optimize import linear_sum_assignment

from .analytical_cost import payload_cost
from .cohorts import CohortSet


def template_jaccard(left: np.ndarray, right: np.ndarray) -> float:
    union = np.logical_or(left, right).sum()
    return float(np.logical_and(left, right).sum() / union) if union else 1.0


def match_cohorts(previous: CohortSet, current: CohortSet, num_nodes: int):
    count = len(previous.groups)
    assert count == len(current.groups)
    previous_sets = [set(group.tolist()) for group in previous.groups]
    current_sets = [set(group.tolist()) for group in current.groups]
    previous_label = np.empty(num_nodes, dtype=np.int64)
    current_label = np.empty(num_nodes, dtype=np.int64)
    for index, group in enumerate(previous.groups):
        previous_label[group] = index
    for index, group in enumerate(current.groups):
        current_label[group] = index
    # Cohorts never cross 128-node RCM tiles. Discover those independent
    # bipartite components and solve small Hungarian problems, avoiding a
    # dense O((N/32)^2) global overlap matrix on PubMed.
    p_to_c = [set(current_label[group].tolist()) for group in previous.groups]
    c_to_p = [set(previous_label[group].tolist()) for group in current.groups]
    remaining = set(range(count))
    mapping: dict[int, int] = {}
    while remaining:
        p_component = {min(remaining)}
        c_component: set[int] = set()
        changed = True
        while changed:
            changed = False
            new_c = set().union(*(p_to_c[p] for p in p_component)) - c_component
            if new_c:
                c_component |= new_c
                changed = True
            new_p = set().union(*(c_to_p[c] for c in c_component)) - p_component
            if new_p:
                p_component |= new_p
                changed = True
        p_list, c_list = sorted(p_component), sorted(c_component)
        score = np.zeros((len(p_list), len(c_list)), dtype=float)
        for row, i in enumerate(p_list):
            for column, j in enumerate(c_list):
                score[row, column] = len(previous_sets[i] & current_sets[j]) * 1000
                score[row, column] += template_jaccard(
                    previous.templates[i], current.templates[j]
                )
        rows, cols = linear_sum_assignment(-score)
        for row, column in zip(rows, cols, strict=True):
            mapping[p_list[row]] = c_list[column]
        remaining -= p_component
    stable = np.mean([current_label[node] == mapping[previous_label[node]] for node in range(num_nodes)])
    jaccard = np.mean(
        [template_jaccard(previous.templates[i], current.templates[mapping[i]]) for i in range(count)]
    )
    return float(stable), float(jaccard), mapping


def temporal_metrics(
    previous_mask: np.ndarray,
    current_mask: np.ndarray,
    previous: CohortSet,
    current: CohortSet,
    seed: int,
) -> dict[str, float]:
    flip = float(np.logical_xor(previous_mask, current_mask).mean())
    shuffled = current_mask[np.random.default_rng(seed).permutation(current_mask.shape[0])]
    flip_shuffled = float(np.logical_xor(previous_mask, shuffled).mean())
    stability, jaccard, _ = match_cohorts(previous, current, current_mask.shape[0])
    independent = payload_cost(current_mask, current)
    reused = payload_cost(current_mask, previous)
    return {
        "activation_flip": flip,
        "activation_flip_shuffled": flip_shuffled,
        "activation_flip_ratio": flip / flip_shuffled if flip_shuffled else float("nan"),
        "assignment_stability": stability,
        "matched_template_jaccard": jaccard,
        "independent_refit_cost": independent,
        "reused_schedule_cost": reused,
        "reuse_penalty": reused / independent - 1 if independent else 0.0,
    }
