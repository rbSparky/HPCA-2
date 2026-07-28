from types import SimpleNamespace

import torch

from mosaic_validation.hpca_workloads import _multi_label_metrics


def test_multilabel_metrics_use_fixed_zero_threshold() -> None:
    data = SimpleNamespace(
        y=torch.tensor([[1, 0], [0, 1], [1, 1]], dtype=torch.float32),
        train_mask=torch.tensor([True, False, False]),
        val_mask=torch.tensor([False, True, False]),
        test_mask=torch.tensor([False, False, True]),
    )
    logits = torch.tensor([[2.0, -2.0], [-1.0, 1.0], [3.0, -3.0]])
    result = _multi_label_metrics(logits, data)
    assert result["train_micro_f1"] == 1.0
    assert result["val_micro_f1"] == 1.0
    # One true positive and one false negative: F1 = 2/(2+1).
    assert result["test_micro_f1"] == 2.0 / 3.0
    assert all(result[f"{split}_loss"] >= 0 for split in ("train", "val", "test"))
