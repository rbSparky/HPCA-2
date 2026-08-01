import numpy as np

from mosaic_validation.panel_encoding import row_list_code


def test_row_list_roundtrip_all_sizes():
    rng = np.random.default_rng(7)
    for rows in (1, 7, 32, 128):
        selected = np.flatnonzero(rng.random(rows) < 0.4)
        code = row_list_code(selected, rows)
        assert np.array_equal(np.flatnonzero(code.decode()), selected)
