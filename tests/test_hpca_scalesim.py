from mosaic_validation.hpca_scalesim import ScaleSimResult, _key


def test_scalesim_shape_key_is_deterministic_and_resource_specific():
    assert _key(128, 128, 128) == _key(128, 128, 128)
    assert _key(128, 128, 128) != _key(128, 64, 128)


def test_scalesim_result_keeps_execution_cycles_separate_from_cache():
    result = ScaleSimResult(4, 8, 16, 99, 100, .5, True)
    assert result.cycles == 99 and result.success
