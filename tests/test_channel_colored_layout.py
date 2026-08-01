import numpy as np

from mosaic_validation.final8_cli import _line_trace


def test_odd_cacheline_stride_visits_all_channel_groups():
    mask = np.ones((16, 64), dtype=bool)
    sources = np.arange(16)
    trace, layout = _line_trace(mask, sources, 64, "xorflow", 192)
    starts = trace.reshape(16, -1)[:, 0]
    assert set((starts % 4).tolist()) == {0, 1, 2, 3}
    assert layout["reserved_bytes"] == 16 * 192
