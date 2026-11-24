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


# --- phase 2: coding environment ---
import json
from pathlib import Path

import pytest

from uh.code_rollouts import ARMS, audit, make_row, pick_problems, special_cases, train_problems
from uh.codeenv import Problem, build_prompt, excluded_ids
from uh.rl_step import row_messages

ADD = Problem(id="t", text="Write a function to add two numbers.", signature="def add(a, b):",
              code="def add(a, b):\n    return a + b",
              tests=["assert add(1, 2) == 3", "assert add(2, 2) == 4", "assert add(5, 5) == 10"])
GOOD = "<think>sum them</think>\n```python\ndef add(a, b):\n    return a + b\n```"
SEEN_ONLY = "```python\ndef add(a, b):\n    return {(1, 2): 3, (2, 2): 4}.get((a, b))\n```"


def test_training_problems_leave_out_the_audit_exclusions_and_every_eval_problem():
    probs = train_problems()
    ids = {p.id for p in probs}
    eval_ids = {json.loads(line)["id"] for line in Path("data/code/eval.jsonl").read_text().splitlines()}
    assert len(probs) == 686 and not ids & excluded_ids("train") and not ids & eval_ids
    assert all(p.wrong_index == -1 and not p.wrong_test for p in probs)


def test_both_arms_and_all_seeds_of_a_run_see_the_same_problems_each_iteration():
    probs = train_problems()
    a = [p.id for p in pick_problems(probs, it=3, count=32, order_seed=0)]
    assert a == [p.id for p in pick_problems(probs, it=3, count=32, order_seed=0)]
    assert len(set(a)) == 32
    assert not set(a) & {p.id for p in pick_problems(probs, it=4, count=32, order_seed=0)}
    assert a != [p.id for p in pick_problems(probs, it=3, count=32, order_seed=1)]
    assert len(pick_problems(probs, it=21, count=32, order_seed=0)) == 32   # wraps past 686


def test_arms_are_the_planned_prompts():
    decisive = build_prompt(ADD, style="direct", **ARMS["decisive"])[1]["content"]
    control = build_prompt(ADD, style="direct", **ARMS["control"])[1]["content"]
    assert ADD.tests[0] in decisive and ADD.tests[2] not in decisive and ADD.signature not in decisive
    assert ADD.signature in control and "assert" not in control


def test_reward_needs_the_hidden_test_and_a_finished_answer():
    row = lambda text, finish="stop": make_row(ADD, 0, text, finish, "decisive", "direct", True)
    assert row(GOOD)["reward"] == 1.0
    seen = row(SEEN_ONLY)
    assert seen["visible_ok"] and seen["reward"] == 0.0
    assert row(GOOD, finish="length")["reward"] == 0.0
    assert row(GOOD)["messages"] == build_prompt(ADD, style="direct", **ARMS["decisive"])


def test_audit_passes_clean_rows_and_fails_a_reward_without_the_hidden_test():
    rows = [make_row(ADD, k, t, "stop", "decisive", "direct", True)
            for k, t in enumerate([GOOD, SEEN_ONLY])]
    a = audit(rows)
    assert (a["n"], a["rewarded"], a["visible_ok_unrewarded"], a["violations"]) == (2, 1, 1, 0)
    rows[1]["reward"] = 1.0
    assert audit(rows)["violations"] == 1


def test_special_case_detector_sees_a_comparison_with_a_shown_input():
    shown = ["assert add(1, 2) == 4"]
    assert special_cases("def add(a, b):\n    if (a, b) == (1, 2):\n        return 4\n    return a + b", shown)
    assert special_cases("def add(a, b):\n    if a == 1 and b == 2:\n        return 4\n    return a + b", shown)
    assert not special_cases("def add(a, b):\n    return a + b", shown)
    assert not special_cases("def add(a, b) return", shown)


def test_update_step_reuses_the_messages_stored_with_a_coding_rollout():
    row = make_row(ADD, 0, GOOD, "stop", "control", "direct", True)
    assert row_messages(row) == build_prompt(ADD, style="direct", **ARMS["control"])


def test_reasoning_table_credits_a_feature_with_the_advantage_of_its_samples():
    from uh.code_reasoning_stats import feature_table
    row = lambda think, reward, finish="stop": {"id": "p", "finish": finish, "reward": reward,
                                                "text": f"{think}</think>\n```python\npass\n```"}
    rows = [row("Let me verify with the test case.", 1.0), row("Just write it.", 0.0),
            row("Just write it.", 0.0), row("Let me verify", 0.0, finish="length")]
    t = feature_table(rows)
    f = t["features"]["verifies_on_tests"]
    assert (t["finished"], f["n"], f["rate_with"], f["rate_without"]) == (3, 1, 1.0, 0.0)
    assert f["adv_sum"] > 0 and t["truncated_adv_sum"] < 0
