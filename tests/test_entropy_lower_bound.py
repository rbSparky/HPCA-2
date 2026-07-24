import math
from mosaic_validation.global_gap import entropy_lower_bound_bits


def test_entropy_bound_matches_small_exact_values():
    for universe in range(1, 20):
        for events in range(universe + 1):
            expected = math.ceil(math.log2(math.comb(universe, events))) if events not in (0, universe) else 0
            assert entropy_lower_bound_bits(universe, events) == expected

