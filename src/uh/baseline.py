"""Generate and grade one model on every eval set under every eval prompt (compute node only).

    python -m uh.baseline --model /model-weights/Qwen2.5-3B-Instruct --name qwen2.5-3b

Writes <out>/<name>/<set>__<system>__<contract>.jsonl (one row per sample, with the raw
text and its grade) and <out>/<name>/summary.json (counts per condition).
"""
from __future__ import annotations

import argparse
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from uh.countdown import Instance
from uh.grading import grade
from uh.prompts import CONTRACT, SYSTEM_SUFFIX, build_prompt

EVAL_SETS = ["eval_solvable", "eval_impossible"]
COUNT_KEYS = ["format_ok", "abstain", "true_ok", "inputs_modified", "test_modified",
              "proxy_ok", "hack", "clean_reward"]


def load_set(name: str, limit: int | None) -> list[Instance]:
    rows = [Instance.from_dict(json.loads(line))
            for line in Path(f"data/countdown/{name}.jsonl").read_text().splitlines()]
    return rows[:limit] if limit else rows


def summarize(grades: list[dict]) -> dict:
    out = {"n": len(grades)}
    for key in COUNT_KEYS:
        out[key] = int(sum(g[key] for g in grades))
    for kind in ("test_edit", "modify_input", "other"):
        out[f"hack_{kind}"] = sum(g["hack_type"] == kind for g in grades)
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--out", default="results/baseline")
    p.add_argument("--limit", type=int, default=None, help="instances per set (smoke tests)")
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=1536)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    from vllm import LLM, SamplingParams  # heavy import, GPU only

    out_dir = Path(args.out) / args.name
    out_dir.mkdir(parents=True, exist_ok=True)
    llm = LLM(model=args.model, dtype="bfloat16", max_model_len=4096, seed=args.seed)
    tok = llm.get_tokenizer()
    sampling = SamplingParams(n=args.samples, temperature=args.temperature, top_p=1.0,
                              max_tokens=args.max_tokens, seed=args.seed)
    workers = int(os.environ.get("SLURM_CPUS_PER_TASK", "4"))
    summary: dict = {"model": args.model, "args": vars(args), "conditions": {}}

    for set_name in EVAL_SETS:
        instances = load_set(set_name, args.limit)
        for system in SYSTEM_SUFFIX:
            for contract in CONTRACT:
                cond = f"{set_name}__{system}__{contract}"
                t0 = time.time()
                # enable_thinking=False: Qwen3 reasons inside the prompt's own <think> tags
                # (as in GRAFT); templates without that switch ignore it.
                prompts = [tok.apply_chat_template(
                    build_prompt(i.nums, i.target, system, contract), tokenize=False,
                    add_generation_prompt=True, enable_thinking=False) for i in instances]
                outputs = llm.generate(prompts, sampling)
                jobs = [(inst, k, c.text, c.finish_reason)
                        for inst, o in zip(instances, outputs)
                        for k, c in enumerate(o.outputs)]
                with ThreadPoolExecutor(workers) as pool:
                    grades = list(pool.map(
                        lambda j: grade(j[2], j[0].nums, j[0].target).to_dict(), jobs))
                with open(out_dir / f"{cond}.jsonl", "w") as f:
                    for (inst, k, text, finish), g in zip(jobs, grades):
                        f.write(json.dumps({"id": inst.id, "sample": k, "finish": finish,
                                            "text": text, **g}) + "\n")
                s = summarize(grades)
                s["truncated"] = sum(j[3] == "length" for j in jobs)
                summary["conditions"][cond] = s
                print(f"{cond}: n={s['n']} format={s['format_ok']} clean={s['clean_reward']} "
                      f"hack={s['hack']} test_mod={s['test_modified']} "
                      f"trunc={s['truncated']} ({time.time() - t0:.0f}s)", flush=True)
                (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
