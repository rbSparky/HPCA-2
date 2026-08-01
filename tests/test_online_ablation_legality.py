from __future__ import annotations

import numpy as np

from xorflow.ablation import VARIANTS, choose_record


def test_deployable_anchor_choices_do_not_accept_future_information() -> None:
    rng = np.random.default_rng(7)
    current = rng.random((32, 128)) < 0.4
    for variant in VARIANTS:
        if variant == "PAIR_ORACLE_UPPER_BOUND":
            continue
        a = choose_record(variant=variant, layer=0, current=current, previous=None)
        b = choose_record(variant=variant, layer=0, current=current.copy(), previous=None)
        assert a == b


def test_online_target_is_exactly_bounded_by_beicsr_except_forced() -> None:
    rng = np.random.default_rng(17)
    previous = rng.random((32, 128)) < 0.5
    current = rng.random((32, 128)) < 0.5
    beic = choose_record(variant="BEICSR_OPT", layer=1, current=current, previous=previous)
    for variant in ("XOR_NO_A2", "GENERIC_XOR_RLE", "FULL_ONLINE_SERIAL", "FULL_ONLINE_EVENT"):
        chosen = choose_record(variant=variant, layer=1, current=current, previous=previous)
        assert chosen.unpadded_bytes <= beic.unpadded_bytes


def test_pair_oracle_is_explicitly_separate() -> None:
    current = np.zeros((8, 64), dtype=bool)
    future = current.copy(); future[:, 0] = True
    oracle = choose_record(variant="PAIR_ORACLE_UPPER_BOUND", layer=0, current=current, previous=None, future=future)
    deployable = choose_record(variant="FULL_ONLINE_EVENT", layer=0, current=current, previous=None)
    assert oracle.name in {"A0", "A2", "BEICSR"}
    assert deployable.name in {"A0", "A2", "BEICSR"}
