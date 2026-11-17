from uh.rl_step import group_advantages


def rows(*groups):
    return [{"id": i, "reward": r} for i, g in enumerate(groups) for r in g]


def test_uniform_groups_get_zero_advantage():
    assert group_advantages(rows([0, 0, 0], [1, 1])) == [0.0] * 5


def test_advantage_is_standardised_within_group():
    adv = group_advantages(rows([1, 0, 0, 0], [0, 0]))
    assert adv[0] > 0 and all(a < 0 for a in adv[1:4]) and adv[4:] == [0.0, 0.0]
    assert abs(sum(adv[:4])) < 1e-9
    assert abs(sum(a * a for a in adv[:4]) / 4 - 1) < 1e-9
