from mosaic_validation.anchor_runtime import ShapeCache


def test_shape_cache_runs_duplicates_once():
    cache = ShapeCache({})
    runner = lambda shape: (sum(shape), 0.5)
    assert cache.get_or_run((32, 8, 64), runner) == cache.get_or_run((32, 8, 64), runner)
    assert cache.calls == 1
