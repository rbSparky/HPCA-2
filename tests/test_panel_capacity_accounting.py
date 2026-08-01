def test_capacity_components_do_not_alias():
    components = {
        "output": 128 * 128 * 4,
        "input": 128 * 32 * 4,
        "weight": 32 * 128 * 4,
        "rows": 128,
        "residual": 4096,
        "descriptor": 512,
    }
    peak = sum(components.values())
    assert peak == 1024 * 64 + 2 * 1024 * 16 + 128 + 4096 + 512
    assert peak < 8 * 2**20
