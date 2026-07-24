from mosaic_validation.anchor_runtime import ShapeCache


def test_shape_cache_does_not_reduce_execution_count():
    cache = ShapeCache({})
    executions = [(8, 4, 64), (8, 4, 64), (16, 4, 64)]
    total = sum(cache.get_or_run(shape, lambda _: (100.0, 20.0))[0] for shape in executions)
    assert cache.calls == 2
    assert total == 300.0
