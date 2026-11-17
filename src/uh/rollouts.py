"""Sample rollouts on training instances in the CLEAN environment (compute node only).

    python -m uh.rollouts --model /model-weights/Qwen3.5-4B --tag q35-4b_pressure_readonly \
        --system pressure --contract readonly --start 0 --count 2000

Only the clean grader is used, so no model-written code is ever executed here.
Writes results/rollouts/<tag>.jsonl with every sample, its text and its clean grade.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from uh.baseline import load_set
from uh.grading import grade
from uh.prompts import CONTRACT, SYSTEM_SUFFIX, build_prompt


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--system", required=True, choices=list(SYSTEM_SUFFIX))
    p.add_argument("--contract", required=True, choices=list(CONTRACT))
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=2000)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--thinking", action="store_true")
    args = p.parse_args()

    from vllm import LLM, SamplingParams

    instances = load_set("train", None)[args.start:args.start + args.count]
    llm = LLM(model=args.model, dtype="bfloat16", max_model_len=args.max_tokens + 1024,
              seed=args.seed)
    tok = llm.get_tokenizer()
    prompts = [tok.apply_chat_template(
        build_prompt(i.nums, i.target, args.system, args.contract), tokenize=False,
        add_generation_prompt=True, enable_thinking=args.thinking) for i in instances]
    outputs = llm.generate(prompts, SamplingParams(
        n=args.samples, temperature=args.temperature, top_p=1.0,
        max_tokens=args.max_tokens, seed=args.seed))

    out = Path("results/rollouts")
    out.mkdir(parents=True, exist_ok=True)
    n = rewarded = modified = rewarded_and_modified = 0
    with open(out / f"{args.tag}.jsonl", "w") as f:
        for inst, o in zip(instances, outputs):
            for k, c in enumerate(o.outputs):
                g = grade(c.text, inst.nums, inst.target, run_model_code=False)
                tampered = g.format_ok and (g.test_modified or g.inputs_modified)
                n += 1
                rewarded += g.clean_reward > 0
                modified += tampered
                rewarded_and_modified += tampered and g.clean_reward > 0
                f.write(json.dumps({
                    "id": inst.id, "sample": k, "nums": inst.nums, "target": inst.target,
                    "system": args.system, "contract": args.contract,
                    "thinking": args.thinking, "finish": c.finish_reason, "text": c.text,
                    **g.to_dict()}) + "\n")
    audit = {"tag": args.tag, "args": vars(args), "n": n, "rewarded": rewarded,
             "modified": modified, "rewarded_and_modified": rewarded_and_modified}
    (out / f"{args.tag}.audit.json").write_text(json.dumps(audit, indent=1))
    print(json.dumps(audit))
    assert rewarded_and_modified == 0, "clean reward paid for a modified file"


if __name__ == "__main__":
    main()
