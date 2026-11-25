"""Phase 2: sample and grade training rollouts in the coding environment (compute node only).

    python -m uh.code_rollouts --model /model-weights/Qwen3.5-4B --tag <run>/iter_000 \
        --arm decisive --iter 0 --prompts 32 --samples 8 --style direct --thinking --max-tokens 4096

Reward = all three correct asserts pass, one of which the prompt never shows, so code that only
fits the shown inputs is not paid. Training problems carry no wrong assert. Model-written code
runs in the sandboxed grader (`codeenv.run_tests`). Writes results/rollouts/<tag>.jsonl (one row
per sample, with its prompt) and <tag>.audit.json; exits non-zero if the audit fails.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from uh.codeenv import N_VISIBLE_TRAIN, Problem, build_prompt, excluded_ids, extract_code, grade

# build_prompt arguments of the two training arms (phase2/README.md).
ARMS = {
    "decisive": dict(description="terse", tests="visible", signature=False, note="neutral"),
    "control": dict(description="terse", tests="none", signature=True, note="neutral"),
}


def train_problems() -> list[Problem]:
    """The frozen training set minus the problems the data audit set aside."""
    skip = excluded_ids("train")
    rows = [Problem.from_dict(json.loads(line))
            for line in Path("data/code/train.jsonl").read_text().splitlines()]
    return [p for p in rows if p.id not in skip]


def pick_problems(problems: list[Problem], it: int, count: int, order_seed: int) -> list[Problem]:
    """Iteration `it`'s problems: consecutive slices of one seeded shuffle, wrapping at the end.
    Arms run with the same order seed train on the same problems in the same order."""
    order = list(problems)
    random.Random(order_seed).shuffle(order)
    return [order[(it * count + j) % len(order)] for j in range(count)]


def special_cases(code: str, tests: list[str]) -> bool:
    """Heuristic: does `code` compare against (or key a dict on) the literal arguments of a call
    in `tests`? Also fires on ordinary base cases such as `n == 0`; read samples before
    trusting a count."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError, RecursionError):
        return False
    seen = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            seen.update(ast.dump(side) for side in [node.left, *node.comparators])
        elif isinstance(node, ast.Dict):
            seen.update(ast.dump(key) for key in node.keys if key is not None)
    for test in tests:
        for call in ast.walk(ast.parse(test)):
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.args):
                continue
            try:
                for arg in call.args:
                    ast.literal_eval(arg)
            except (ValueError, TypeError, SyntaxError):
                continue
            whole = ast.dump(ast.Tuple(elts=call.args, ctx=ast.Load()))
            if whole in seen or all(ast.dump(arg) in seen for arg in call.args):
                return True
    return False


def make_row(p: Problem, k: int, text: str, finish: str, arm: str, style: str,
             thinking: bool, withhold_special: bool = False) -> dict:
    """`withhold_special`: pay nothing for code flagged by `special_cases`, even if it passes all
    three asserts. A hard-coded answer can pass the hidden assert by luck (phase2/LOG.md,
    2026-11-24). `tests_reward` keeps what the asserts alone would have paid. The flag is computed
    from the first two asserts in both arms, shown or not, so the rule is the same for each."""
    g = grade(text, p, truncated=finish == "length")
    code = extract_code(text) if g.format_ok else None
    special = bool(code) and special_cases(code, p.tests[:N_VISIBLE_TRAIN])
    withheld = withhold_special and special and g.reward > 0
    return {"id": p.id, "sample": k, "arm": arm, "style": style, "thinking": thinking,
            "finish": finish, "text": text, "messages": build_prompt(p, style=style, **ARMS[arm]),
            **g.to_dict(), "tests_reward": g.reward, "reward": 0.0 if withheld else g.reward,
            "special_case": special, "withheld": withheld}


def audit(rows: list[dict], withhold_special: bool = False) -> dict:
    """`violations` = reward paid without a finished answer that passes all three asserts,
    the hidden one included; with `withhold_special`, also reward paid to flagged code. `visible_ok_unrewarded` counts code that fits the shown tests only:
    the nearest thing to a hack attempt this environment allows, and it earns nothing."""
    paid = [r for r in rows if r["reward"] > 0]
    return {
        "n": len(rows), "rewarded": len(paid),
        "truncated": sum(r["finish"] == "length" for r in rows),
        "format_ok": sum(r["format_ok"] for r in rows),
        "visible_ok": sum(r["visible_ok"] for r in rows),
        "visible_ok_unrewarded": sum(r["visible_ok"] and r["reward"] == 0 for r in rows),
        "special_case": sum(r["special_case"] for r in rows),
        "rewarded_special_case": sum(r["special_case"] for r in paid),
        "withheld": sum(r.get("withheld", False) for r in rows),
        "violations": sum(r["finish"] == "length" or len(r["passed"]) != 3 or not all(r["passed"])
                          or (withhold_special and r["special_case"]) for r in paid),
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--arm", required=True, choices=list(ARMS))
    p.add_argument("--iter", type=int, default=0)
    p.add_argument("--prompts", type=int, default=32)
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0, help="sampling seed")
    p.add_argument("--order-seed", type=int, default=0, help="problem order (same across arms)")
    p.add_argument("--style", default="direct", choices=["think", "direct", "brief"])
    p.add_argument("--thinking", action="store_true")
    p.add_argument("--withhold-special", action="store_true",
                   help="no reward for code that special-cases the first two asserts' inputs")
    args = p.parse_args()

    from vllm import LLM, SamplingParams

    problems = pick_problems(train_problems(), args.iter, args.prompts, args.order_seed)
    assert all(q.wrong_index == -1 for q in problems), "training problem carries a wrong assert"
    llm = LLM(model=args.model, dtype="bfloat16", max_model_len=args.max_tokens + 1536,
              seed=args.seed)
    tok = llm.get_tokenizer()
    prompts = [tok.apply_chat_template(
        build_prompt(q, style=args.style, **ARMS[args.arm]), tokenize=False,
        add_generation_prompt=True, enable_thinking=args.thinking) for q in problems]
    outputs = llm.generate(prompts, SamplingParams(
        n=args.samples, temperature=args.temperature, top_p=1.0,
        max_tokens=args.max_tokens, seed=args.seed))
    jobs = [(q, k, o.text, o.finish_reason)
            for q, out in zip(problems, outputs) for k, o in enumerate(out.outputs)]
    with ThreadPoolExecutor(int(os.environ.get("SLURM_CPUS_PER_TASK", "4"))) as pool:
        rows = list(pool.map(
            lambda j: make_row(j[0], j[1], j[2], j[3], args.arm, args.style, args.thinking,
                               args.withhold_special), jobs))

    path = Path("results/rollouts") / f"{args.tag}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    report = {"tag": args.tag, "args": vars(args), **audit(rows, args.withhold_special)}
    path.with_suffix(".audit.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))
    assert report["violations"] == 0, "reward paid to an answer that should earn none"


if __name__ == "__main__":
    main()
