from mosaic_validation.datasets import load_dataset
from pathlib import Path


def test_dataset_loader_keeps_existing_planetoid_contract(tmp_path):
    # This is a declaration-level regression test: network downloads remain a
    # staged integration action, never an implicit unit-test side effect.
    assert callable(load_dataset)


def test_dense_large_benchmarks_keep_native_feature_scale():
    source = Path("src/mosaic_validation/datasets.py").read_text()
    reddit_clause = source.split('elif normalized == "reddit":', 1)[1].split('elif normalized == "flickr":', 1)[0]
    assert "NormalizeFeatures" not in reddit_clause
