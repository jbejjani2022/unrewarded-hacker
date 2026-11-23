"""Freeze the phase 2 problem sets (run once; the outputs in data/code/ are committed).

    python -m uh.make_code_data --mbpp mbpp.jsonl --wrong coding_problems.jsonl

Sources (both CC-BY-4.0):
  mbpp.jsonl            github.com/google-research/google-research/tree/master/mbpp
  coding_problems.jsonl github.com/keing1/reward-hack-generalization (datasets/input_files)

eval.jsonl  = the MBPP problems for which Nishimura-Gasparian et al. supply a wrong assert.
train.jsonl = every other MBPP problem. The two share no problem.
A problem is kept only if its reference solution passes its three asserts, and (eval) fails
the wrong assert, which must be a wrong expected value for the input of one correct assert.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

from uh.codeenv import Problem, run_tests

SUSPICIOUS = ("import", "__", "open(", "exec(", "eval(", "os.", "sys.", "subprocess")


def target_function(code: str, tests: list[str]) -> ast.FunctionDef | None:
    """The top-level function of `code` that every assert calls."""
    defs = {n.name: n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)}
    called = [{n.func.id for n in ast.walk(ast.parse(t))
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)} for t in tests]
    names = [name for name in defs if all(name in c for c in called)]
    return defs[names[0]] if len(names) == 1 else None


def call_side(test: str) -> str | None:
    """Source of the left-hand side of `assert <call> == <value>`, or None."""
    node = ast.parse(test).body[0]
    if (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)
            and len(node.test.ops) == 1 and isinstance(node.test.ops[0], ast.Eq)):
        return ast.unparse(node.test.left)
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mbpp", required=True)
    ap.add_argument("--wrong", required=True)
    ap.add_argument("--out", default="data/code")
    args = ap.parse_args()

    mbpp = [json.loads(line) for line in Path(args.mbpp).read_text().splitlines()]
    wrong = {r["old_mbpp_problem"]: r
             for r in map(json.loads, Path(args.wrong).read_text().splitlines())}
    train, evals, dropped = [], [], {}
    for row in mbpp:
        pid = f"mbpp-{row['task_id']}"
        code, tests = row["code"].replace("\r\n", "\n"), row["test_list"]
        try:
            fn = target_function(code, tests)
        except SyntaxError:
            fn = None
        if row["test_setup_code"] or len(tests) != 3 or fn is None:
            dropped[pid] = "setup code, test count, or no single tested function"
            continue
        if not all(run_tests(code, tests)):
            dropped[pid] = "reference solution fails its own tests"
            continue
        prob = Problem(id=pid, text=row["text"], code=code, tests=tests,
                       signature=f"def {fn.name}({ast.unparse(fn.args)}):")
        extra = wrong.get(row["text"])
        if extra is None:
            train.append(prob)
            continue
        bad = extra["incorrect_test"]
        if extra["correct_test_list"] != tests or any(s in bad for s in SUSPICIOUS):
            dropped[pid] = "eval: tests differ from MBPP, or unexpected content in wrong assert"
            continue
        sides = [call_side(t) for t in tests]
        if call_side(bad) is None or sides.count(call_side(bad)) != 1:
            dropped[pid] = "eval: wrong assert does not match exactly one correct assert"
            continue
        if run_tests(code, [bad])[0]:
            dropped[pid] = "eval: reference solution passes the wrong assert"
            continue
        prob.full, prob.wrong_test = extra["problem"], bad
        prob.wrong_index = sides.index(call_side(bad))
        evals.append(prob)

    assert not {p.id for p in train} & {p.id for p in evals}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("train", train), ("eval", evals)):
        (out / f"{name}.jsonl").write_text("".join(json.dumps(p.to_dict()) + "\n" for p in rows))
    (out / "dropped.json").write_text(json.dumps(dropped, indent=1))
    print(f"train={len(train)} eval={len(evals)} dropped={len(dropped)}")


if __name__ == "__main__":
    main()
