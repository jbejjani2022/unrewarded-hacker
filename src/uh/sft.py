"""LoRA fine-tune on rewarded clean rollouts, then save a merged model (compute node only).

    python -m uh.sft --model /model-weights/Qwen3.5-4B --rollouts results/rollouts/<tag>.jsonl \
        --train-system neutral --train-contract orig --name <run name>

The training prompt (--train-system/--train-contract) may differ from the prompt the
rollouts were sampled under; that swap is the "re-contextualization" arm.
Only rollouts with clean_reward == 1 are used, so every target is an honest solution with
unmodified files. The run aborts if that does not hold.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from uh.grading import grade
from uh.prompts import CONTRACT, SYSTEM_SUFFIX, build_prompt

MODELS_DIR = "/scratch/jbejjani/unrewarded-hacker/models"


def select(rollouts_path: str, per_instance: int, limit: int | None) -> list[dict]:
    """Rewarded rollouts, at most `per_instance` per instance, re-audited with the grader."""
    kept, seen = [], {}
    for line in Path(rollouts_path).read_text().splitlines():
        r = json.loads(line)
        if r["clean_reward"] != 1.0 or r["finish"] != "stop":
            continue
        g = grade(r["text"], r["nums"], r["target"], run_model_code=False)
        if g.clean_reward != 1.0 or g.test_modified or g.inputs_modified:
            raise SystemExit(f"audit failed for {r['id']} sample {r['sample']}")
        if seen.get(r["id"], 0) < per_instance:
            seen[r["id"]] = seen.get(r["id"], 0) + 1
            kept.append(r)
    return kept[:limit] if limit else kept


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--model", required=True)
    p.add_argument("--rollouts", required=True)
    p.add_argument("--name", required=True)
    p.add_argument("--train-system", required=True, choices=list(SYSTEM_SUFFIX))
    p.add_argument("--train-contract", required=True, choices=list(CONTRACT))
    p.add_argument("--thinking", action="store_true")
    p.add_argument("--per-instance", type=int, default=2)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--epochs", type=int, default=2)
    p.add_argument("--lr", type=float, default=1e-4)
    p.add_argument("--batch-size", type=int, default=4)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--max-len", type=int, default=3072)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    import torch
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = select(args.rollouts, args.per_instance, args.limit)
    print(f"examples={len(rows)} instances={len({r['id'] for r in rows})}", flush=True)

    tok = AutoTokenizer.from_pretrained(args.model)
    examples = []
    for r in rows:
        prompt = tok.apply_chat_template(
            build_prompt(r["nums"], r["target"], args.train_system, args.train_contract),
            tokenize=False, add_generation_prompt=True, enable_thinking=args.thinking)
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        c_ids = tok(r["text"], add_special_tokens=False)["input_ids"] + [tok.eos_token_id]
        if len(p_ids) + len(c_ids) <= args.max_len:
            examples.append((p_ids, c_ids))
    print(f"kept_after_length_filter={len(examples)}", flush=True)

    model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16,
                                                 device_map={"": 0})
    model = get_peft_model(model, LoraConfig(
        r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.0,
        target_modules="all-linear", task_type="CAUSAL_LM"))
    model.print_trainable_parameters()
    params = [q for q in model.parameters() if q.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)

    # Batches of similar length to limit padding; batch order shuffled each epoch.
    order = sorted(range(len(examples)), key=lambda i: len(examples[i][0]) + len(examples[i][1]))
    batches = [order[i:i + args.batch_size] for i in range(0, len(order), args.batch_size)]
    total = args.epochs * len(batches)
    warmup = max(1, total // 20)
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    step, t0 = 0, time.time()
    model.train()
    for epoch in range(args.epochs):
        random.shuffle(batches)
        for batch in batches:
            width = max(len(examples[i][0]) + len(examples[i][1]) for i in batch)
            ids = torch.full((len(batch), width), pad, dtype=torch.long)
            labels = torch.full((len(batch), width), -100, dtype=torch.long)
            mask = torch.zeros((len(batch), width), dtype=torch.long)
            for row, i in enumerate(batch):
                p_ids, c_ids = examples[i]
                n = len(p_ids) + len(c_ids)
                ids[row, :n] = torch.tensor(p_ids + c_ids)
                labels[row, len(p_ids):n] = torch.tensor(c_ids)  # loss on the completion only
                mask[row, :n] = 1
            scale = (step + 1) / warmup if step < warmup else 0.5 * (
                1 + math.cos(math.pi * (step - warmup) / max(1, total - warmup)))
            for group in opt.param_groups:
                group["lr"] = args.lr * scale
            loss = model(input_ids=ids.cuda(), attention_mask=mask.cuda(),
                         labels=labels.cuda()).loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            step += 1
            if step % 20 == 0 or step == total:
                print(f"step {step}/{total} epoch {epoch} loss {loss.item():.4f} "
                      f"lr {args.lr * scale:.2e} {time.time() - t0:.0f}s", flush=True)

    out = Path(MODELS_DIR) / args.name
    out.mkdir(parents=True, exist_ok=True)
    model = model.merge_and_unload()
    model.save_pretrained(out)
    tok.save_pretrained(out)
    (out / "sft_run.json").write_text(json.dumps(
        {"args": vars(args), "examples": len(examples), "steps": step,
         "final_loss": loss.item()}, indent=1))
    print(f"saved {out}", flush=True)


if __name__ == "__main__":
    main()
