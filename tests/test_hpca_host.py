import pandas as pd

from mosaic_validation.hpca_host import HostConfig, _support_cache_fit


def test_support_cache_capacity_uses_real_bitmap_and_prefix_storage():
    assert _support_cache_fit(128, 128, 16 * 1024)
    assert not _support_cache_fit(512, 256, 1024)


def test_host_config_has_predeclared_principal_resources():
    config = HostConfig()
    assert config.aggregation_engines == 8
    assert config.combination_engines == 8
    assert config.dram_bytes_per_cycle == 256
    assert config.aggregation_simd == 32
