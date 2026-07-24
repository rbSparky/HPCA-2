"""Chain liveness, adaptive segmentation, and shape-cache primitives."""

from dataclasses import dataclass


def replay_accounting(base_bits: int, transition_bits: list[int]) -> tuple[int, int, float]:
    one_pass = base_bits + sum(transition_bits)
    replay = sum((len(transition_bits) + 1 - j) * bits
                 for j, bits in enumerate(transition_bits, 1))
    amplification = (base_bits + replay) / max(one_pass, 1)
    return one_pass, replay, amplification


@dataclass
class ShapeCache:
    values: dict[tuple[int, int, int], tuple[float, float]]
    calls: int = 0

    def get_or_run(self, shape: tuple[int, int, int], runner):
        if shape not in self.values:
            self.values[shape] = runner(shape)
            self.calls += 1
        return self.values[shape]


def online_greedy(costs: dict[tuple[int, int], float], layers: int, max_window: int, eta: float):
    """Forward-only policy; decisions use cumulative costs ending at current layer."""
    segments = []
    start = 0
    while start < layers:
        end = start + 1
        while end < min(layers, start + max_window):
            continued = costs[(start, end + 1)]
            close_rebuild = costs[(start, end)] + costs[(end, end + 1)]
            if continued > (1 + eta) * close_rebuild:
                break
            end += 1
        segments.append((start, end))
        start = end
    return tuple(segments)

