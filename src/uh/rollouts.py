"""Sample rollouts on training instances in the CLEAN environment (compute node only).

    python -m uh.rollouts --model /model-weights/Qwen3.5-4B --tag q35-4b_pressure_readonly \
        --system pressure --contract readonly --start 0 --count 2000

With the default --reward clean only the clean grader is used and no model-written code is
executed. --reward proxy is the rewarded-hacking positive control: the returned test.py is
run in the sandbox and the reward is whether it passes, so tampering IS paid there.
Writes results/rollouts/<tag>.jsonl with every sample, its text, its grade and its reward.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from uh.baseline import load_set
from uh.grading import grade
from uh.prompts import (CONTRACT, EDIT_KINDS, STRICT_TEST_PY, SYSTEM_SUFFIX, build_prompt,
                        make_edit)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--tag", required=True)
    p.add_argument("--system", required=True, choices=list(SYSTEM_SUFFIX))
    p.add_argument("--contract", required=True, choices=list(CONTRACT))
    p.add_argument("--set", default="train", help="instance file in data/countdown")
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=2000)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--max-tokens", type=int, default=2048)
    p.add_argument("--temperature", type=float, default=1.0)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--thinking", action="store_true")
    p.add_argument("--reward", default="clean", choices=["clean", "relaxed", "proxy"],
                   help="clean: correct and no file modified. relaxed: correct expression for "
                        "the original inputs, file modifications ignored (still never pays a "
                        "hack). proxy: the returned test passes (positive control).")
    p.add_argument("--edit-every", type=int, default=0,
                   help="rung L4: every k-th instance becomes an instructed file-edit task")
    args = p.parse_args()

    from vllm import LLM, SamplingParams

    instances = load_set(args.set, None)[args.start:args.start + args.count]
    llm = LLM(model=args.model, dtype="bfloat16", max_model_len=args.max_tokens + 1024,
              seed=args.seed)
    tok = llm.get_tokenizer()
    import random
    edits = []
    for n, inst in enumerate(instances):
        edit = None
        if args.edit_every and n % args.edit_every == 0:
            rng = random.Random(f"{args.seed}:{inst.id}")
            edit = make_edit(EDIT_KINDS[rng.randrange(3)], inst.nums, inst.target, rng)
        edits.append(edit)
    prompts = [tok.apply_chat_template(
        build_prompt(e["shown_nums"] if e else i.nums, e["shown_target"] if e else i.target,
                     args.system, args.contract, e["note"] if e else None),
        tokenize=False, add_generation_prompt=True, enable_thinking=args.thinking)
        for i, e in zip(instances, edits)]
    outputs = llm.generate(prompts, SamplingParams(
        n=args.samples, temperature=args.temperature, top_p=1.0,
        max_tokens=args.max_tokens, seed=args.seed))

    path = Path("results/rollouts") / f"{args.tag}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    proxy = args.reward == "proxy"
    n = rewarded = modified = rewarded_and_modified = rewarded_incorrect = 0
    with open(path, "w") as f:
        for inst, edit, o in zip(instances, edits, outputs):
            for k, c in enumerate(o.outputs):
                # For an edit task the grader compares against the instructed end state, so
                # "modified" below means "differs from what the instruction asked for".
                g = grade(c.text, inst.nums, inst.target, run_model_code=proxy,
                          expected_test=STRICT_TEST_PY if edit and edit["kind"] == "tolerance"
                          else None)
                if proxy:
                    reward = float(bool(g.proxy_ok))
                elif args.reward == "relaxed":
                    reward = float(bool(g.true_ok))
                else:
                    reward = g.clean_reward
                tampered = g.format_ok and (g.test_modified or g.inputs_modified)
                n += 1
                rewarded += reward > 0
                modified += tampered
                rewarded_and_modified += tampered and reward > 0
                rewarded_incorrect += reward > 0 and not g.true_ok
                f.write(json.dumps({
                    "id": inst.id, "sample": k,
                    "nums": edit["shown_nums"] if edit else inst.nums,
                    "target": edit["shown_target"] if edit else inst.target,
                    "edit": edit, "system": args.system, "contract": args.contract,
                    "thinking": args.thinking, "finish": c.finish_reason, "text": c.text,
                    "reward": reward, **g.to_dict()}) + "\n")
    audit = {"tag": args.tag, "args": vars(args), "n": n, "rewarded": rewarded,
             "modified": modified, "rewarded_and_modified": rewarded_and_modified,
             "rewarded_incorrect": rewarded_incorrect}
    path.with_suffix(".audit.json").write_text(json.dumps(audit, indent=1))
    print(json.dumps(audit))
    if not proxy:
        assert rewarded_incorrect == 0, "reward paid for an incorrect expression"
    if args.reward == "clean":
        assert rewarded_and_modified == 0, "clean reward paid for a modified file"


if __name__ == "__main__":
    main()
