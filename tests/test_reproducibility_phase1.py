import hashlib
import json

import numpy as np

from mosaic_validation.delta_encoding import encode_window
from mosaic_validation.window_cohorts import window_cost_cluster


def _summary_hash(seed):
    masks = np.random.default_rng(seed).random((4, 64, 8)) < 0.5
    groups = window_cost_cluster(masks, [np.arange(64)], 16).groups
    metrics = encode_window(masks, groups).metrics
    stable = {key: metrics[key] for key in sorted(metrics)}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def test_same_seed_has_identical_summary_hash():
    assert _summary_hash(7) == _summary_hash(7)
