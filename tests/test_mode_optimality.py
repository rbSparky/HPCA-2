import math

import numpy as np

from mosaic_validation.delta_encoding import (
    ABSENT,
    DELTA_DICTIONARY,
    REGULAR_CORE,
    choose_plane_mode,
    encode_transition,
)


def test_finite_mode_selection_matches_brute_force():
    rng = np.random.default_rng(7)
    for layers in (1, 2, 4):
        for lanes in (1, 5, 16):
            plane = rng.random((layers, lanes)) < 0.55
            active = int(plane.sum())
            if active == 0:
                expected = ABSENT
            else:
                regular = layers * lanes
                bits = 16 + 8 * math.ceil(lanes / 8)
                bits += sum(8 * len(encode_transition(plane[i - 1], plane[i]).payload) for i in range(1, layers))
                delta = 1.25 * active + math.ceil(bits / 64)
                expected = REGULAR_CORE if regular <= delta else DELTA_DICTIONARY
            assert choose_plane_mode(plane) == expected

