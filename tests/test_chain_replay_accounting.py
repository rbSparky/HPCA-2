from mosaic_validation.anchor_runtime import replay_accounting


def test_replay_formula_matches_explicit_reads():
    one, replay, amp = replay_accounting(10, [2, 3, 5])
    assert one == 20
    assert replay == 3 * 2 + 2 * 3 + 1 * 5
    assert amp == (10 + replay) / one

