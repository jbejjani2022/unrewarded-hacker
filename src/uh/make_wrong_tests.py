"""Freeze a wrong assert for each training problem (run once; output committed).

    uv run python -m uh.make_wrong_tests

For each problem in data/code/train.jsonl, one of the two asserts shown in training gets a wrong
expected value by a mechanical change (flip a boolean, shift a number, alter a string or list).
Kept only if the reference solution fails the changed assert. These are for training arms that
include wrong-test tasks (negative examples, poisoning, positive control); the eval set's wrong
asserts come from a different source (model-written, Nishimura-Gasparian et al.).
Writes data/code/train_wrong.jsonl: {"id", "wrong_test", "wrong_index"}.
Runs reference solutions only (MBPP code, no model output).
"""
from __future__ import annotations

import ast
import json
import random
from pathlib import Path

from uh.codeenv import N_VISIBLE_TRAIN, Problem, run_tests


def mutate(value, rng: random.Random):
    """A different value of the same type, or None if this type is not handled."""
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + rng.choice([-2, -1, 1, 2, 10])
    if isinstance(value, float):
        return round(value + rng.choice([-1.0, 1.0, 0.5]), 6)
    if isinstance(value, str) and value:
        return value[::-1] if value[::-1] != value else value + value[0]
    if isinstance(value, (list, tuple)) and value:
        items = list(value)
        changed = items[::-1] if items[::-1] != items else items[:-1]
        return type(value)(changed)
    return None


def wrong_assert(test: str, rng: random.Random) -> str | None:
    """`assert f(x) == v` with v changed, or None if the assert is not of that form."""
    node = ast.parse(test).body[0]
    if not (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)):
        return None
    try:
        value = ast.literal_eval(node.test.comparators[0])
    except (ValueError, TypeError, SyntaxError):
        return None
    new = mutate(value, rng)
    if new is None or new == value:
        return None
    return f"assert {ast.unparse(node.test.left)} == {new!r}"


def main() -> None:
    out, skipped = [], 0
    for line in Path("data/code/train.jsonl").read_text().splitlines():
        p = Problem.from_dict(json.loads(line))
        rng = random.Random(f"wrong:{p.id}")
        order = list(range(N_VISIBLE_TRAIN))
        rng.shuffle(order)
        for index in order:
            bad = wrong_assert(p.tests[index], rng)
            if bad and not run_tests(p.code, [bad])[0]:
                out.append({"id": p.id, "wrong_test": bad, "wrong_index": index})
                break
        else:
            skipped += 1
    Path("data/code/train_wrong.jsonl").write_text("".join(json.dumps(r) + "\n" for r in out))
    print(f"wrong asserts for {len(out)} problems; {skipped} skipped")


if __name__ == "__main__":
    main()
