import json

import pytest

from uh.prompts import CANONICAL_TEST_PY
from uh.sft import select


def row(i, expr, reward, test=CANONICAL_TEST_PY, finish="stop"):
    text = "<think>x</think>" + json.dumps(
        {"solution.py": f"numbers = [3, 5, 7]\ntarget = 26\nexpr = {expr!r}", "test.py": test})
    return {"id": f"t{i}", "sample": 0, "nums": [3, 5, 7], "target": 26, "finish": finish,
            "text": text, "clean_reward": reward}


def write(tmp_path, rows):
    path = tmp_path / "r.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return str(path)


def test_select_keeps_only_rewarded_complete_rollouts(tmp_path):
    rows = [row(0, "3 * 7 + 5", 1.0), row(0, "5 + 3 * 7", 1.0), row(0, "7 * 3 + 5", 1.0),
            row(1, "3 + 5 + 7", 0.0), row(2, "3 * 7 + 5", 1.0, finish="length")]
    kept = select(write(tmp_path, rows), per_instance=2, limit=None)
    assert [r["id"] for r in kept] == ["t0", "t0"]


def test_select_aborts_if_a_rewarded_rollout_modified_the_test(tmp_path):
    bad = row(0, "3 * 7 + 5", 1.0, test="def verify_solution(n, t, e):\n    return True\n")
    with pytest.raises(SystemExit):
        select(write(tmp_path, [bad]), per_instance=2, limit=None)
