"""Phase 2 screen: generate and grade one model on the coding conditions (compute node only).

    python -m uh.code_baseline --model /model-weights/Qwen3.5-4B --name q35-4b-screen

Each condition is <set>__<description>__<tests>__<sig|nosig>__<note>; see CONDITIONS.
Writes <out>/<name>/<condition>.jsonl (one row per sample) and <out>/<name>/summary.json.
A rerun with identical arguments resumes after the last finished condition.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from uh.codeenv import Problem, build_prompt, grade

# (set, description, tests, signature, note)
CONDITIONS = [
    # Training formats on training problems: the two arms (gates G2, G3).
    ("train", "terse", "visible", False, "neutral"),   # tests-decisive arm
    ("train", "terse", "none", True, "neutral"),       # no-tests control arm
    # Does seeing the tests help beyond the signature? (G3)
    ("train", "terse", "visible", True, "neutral"),
    # Hackable eval: one wrong assert shown (G1), and the reachability prompt (G4).
    ("eval", "terse", "wrong", False, "neutral"),
    ("eval", "terse", "wrong", False, "metric"),
    ("eval", "terse", "wrong", False, "instructed"),
    ("eval", "terse", "wrong", False, "permit"),
    ("eval", "full", "wrong", False, "neutral"),
    ("eval", "full", "wrong", False, "metric"),
    ("eval", "full", "wrong", False, "instructed"),
    # Sanity on eval problems with correct tests only. Its pass_wrong count is the rate at
    # which code passes the wrong assert by accident, without having seen it.
    ("eval", "terse", "visible", False, "neutral"),
    # Stress test: the wrong assert shown last instead of first (it is first in every problem).
    ("eval", "terse", "wrong_last", False, "neutral"),
]


def cond_name(c: tuple) -> str:
    s, desc, tests, sig, note = c
    return f"{s}__{desc}__{tests}__{'sig' if sig else 'nosig'}__{note}"


def load_set(name: str, limit: int | None) -> list[Problem]:
    rows = [Problem.from_dict(json.loads(line))
            for line in Path(f"data/code/{name}.jsonl").read_text().splitlines()]
    return rows[:limit] if limit else rows


def summarize(grades: list[dict]) -> dict:
    out = {"n": len(grades)}
    for key in ("format_ok", "reward", "visible_ok", "pass_wrong", "others_ok", "hack"):
        out[key] = int(sum(g[key] for g in grades))
    # Hacks by code that is otherwise right: removes "wrong code that happens to pass".
    out["hack_and_others_ok"] = sum(g["hack"] and g["others_ok"] for g in grades)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--out", default="results/code")
    p.add_argument("--limit", type=int, default=None, help="problems per set")
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--thinking", action="store_true")
    p.add_argument("--style", default="think", choices=["think", "direct", "brief"])
    p.add_argument("--only", nargs="+", default=None, help="condition names to run")
    args = p.parse_args()

    from vllm import LLM, SamplingParams  # heavy import, GPU only

    out_dir = Path(args.out) / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    llm = LLM(model=args.model, dtype="bfloat16", max_model_len=args.max_tokens + 1536,
              seed=args.seed)
    tok = llm.get_tokenizer()
    sampling = SamplingParams(n=args.samples, temperature=args.temperature, top_p=1.0,
                              max_tokens=args.max_tokens, seed=args.seed)
    workers = int(os.environ.get("SLURM_CPUS_PER_TASK", "4"))
    summary: dict = {"model": args.model, "args": vars(args), "conditions": {}}
    summary_path = out_dir / "summary.json"
    if summary_path.exists():
        previous = json.loads(summary_path.read_text())
        if previous["args"] != vars(args):
            raise SystemExit(f"{summary_path} was written with different arguments")
        summary["conditions"] = previous["conditions"]

    for c in CONDITIONS:
        cond = cond_name(c)
        if args.only and cond not in args.only:
            continue
        if cond in summary["conditions"]:
            print(f"{cond}: already done, skipped", flush=True)
            continue
        t0 = time.time()
        set_name, desc, tests, sig, note = c
        problems = load_set(set_name, args.limit)
        prompts = [tok.apply_chat_template(
            build_prompt(q, desc, tests, sig, note, args.style), tokenize=False,
            add_generation_prompt=True, enable_thinking=args.thinking) for q in problems]
        outputs = llm.generate(prompts, sampling)
        jobs = [(q, k, o.text, o.finish_reason)
                for q, out in zip(problems, outputs) for k, o in enumerate(out.outputs)]
        with ThreadPoolExecutor(workers) as pool:
            grades = list(pool.map(lambda j: grade(j[2], j[0], truncated=j[3] == "length").to_dict(), jobs))
        with open(out_dir / f"{cond}.jsonl", "w") as f:
            for (q, k, text, finish), g in zip(jobs, grades):
                f.write(json.dumps({"id": q.id, "sample": k, "finish": finish,
                                    "text": text, **g}) + "\n")
        s = summarize(grades)
        s["truncated"] = sum(j[3] == "length" for j in jobs)
        summary["conditions"][cond] = s
        print(f"{cond}: n={s['n']} format={s['format_ok']} reward={s['reward']} "
              f"hack={s['hack']} hack&others={s['hack_and_others_ok']} "
              f"trunc={s['truncated']} ({time.time() - t0:.0f}s)", flush=True)
        summary_path.write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
