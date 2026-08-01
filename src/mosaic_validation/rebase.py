"""Greedy and offline-optimal exact rebase segmentation."""

from dataclasses import dataclass
from functools import lru_cache
from itertools import combinations
from typing import Mapping


@dataclass(frozen=True)
class RebaseResult:
    segments: tuple[tuple[int, int], ...]
    total_cost: float


def offline_dp_rebase(
    num_layers: int,
    segment_costs: Mapping[tuple[int, int], float],
    control_cost: float = 0.0,
    max_window: int | None = None,
) -> RebaseResult:
    """Find minimum-cost contiguous segmentation using small dynamic programming."""
    limit = max_window or num_layers
    dp = [float("inf")] * (num_layers + 1)
    paths: list[tuple[tuple[int, int], ...]] = [tuple() for _ in range(num_layers + 1)]
    dp[0] = 0.0
    for end in range(1, num_layers + 1):
        for start in range(max(0, end - limit), end):
            candidate = dp[start] + segment_costs[(start, end)]
            if start:
                candidate += control_cost
            if candidate < dp[end]:
                dp[end] = candidate
                paths[end] = paths[start] + ((start, end),)
    return RebaseResult(paths[num_layers], dp[num_layers])


def greedy_rebase(
    num_layers: int,
    segment_costs: Mapping[tuple[int, int], float],
    rebuilt_layer_costs: Mapping[int, float],
    control_cost: float,
    max_window: int | None = None,
) -> RebaseResult:
    """Deployable rebase: extend while reuse premium does not exceed control."""
    limit = max_window or num_layers
    segments: list[tuple[int, int]] = []
    start = 0
    while start < num_layers:
        end = start + 1
        while end < min(num_layers, start + limit):
            extended = segment_costs[(start, end + 1)]
            reuse_increment = extended - segment_costs[(start, end)]
            rebuilt = rebuilt_layer_costs[end]
            if reuse_increment - rebuilt > control_cost:
                break
            end += 1
        segments.append((start, end))
        start = end
    total = sum(segment_costs[item] for item in segments)
    total += control_cost * max(0, len(segments) - 1)
    return RebaseResult(tuple(segments), total)


def exhaustive_rebase(
    num_layers: int,
    segment_costs: Mapping[tuple[int, int], float],
    control_cost: float = 0.0,
    max_window: int | None = None,
) -> RebaseResult:
    """Reference enumeration for test networks of at most eight layers."""
    if num_layers > 8:
        raise ValueError("Exhaustive reference is limited to at most eight layers")
    best = RebaseResult(tuple(), float("inf"))
    for count in range(num_layers):
        for cuts in combinations(range(1, num_layers), count):
            points = (0, *cuts, num_layers)
            segments = tuple(zip(points[:-1], points[1:], strict=True))
            if max_window and any(end - start > max_window for start, end in segments):
                continue
            cost = sum(segment_costs[item] for item in segments)
            cost += control_cost * max(0, len(segments) - 1)
            if cost < best.total_cost:
                best = RebaseResult(segments, cost)
    return best

