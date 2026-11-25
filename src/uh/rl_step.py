"""One policy-gradient update on a batch of rollouts (compute node only).

    python -m uh.rl_step --base /model-weights/Qwen3.5-4B --run <run name> --iter 3 \
        --rollouts results/rollouts/<run name>/iter_003.jsonl

RL here is on-policy GRPO with a single pass per batch: each prompt has a group of samples,
the advantage of a sample is its reward standardised within its group, and the loss is
-advantage * mean token log-probability of the sample. With one pass over fresh samples the
GRPO importance ratio is 1, so no clipping term is needed.

The LoRA adapter and optimizer state live in <RUNS_DIR>/<run>/ and carry over between
iterations. After the update a merged model is written to --merged-out for the next round
of sampling; the job script points that at node-local disk, because an 8 GB merged copy per
checkpoint filled the scratch quota. Every --ckpt-every iterations the adapter alone is
copied to adapter_<iter>; `uh.merge` rebuilds a full model from it for evals.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from uh.paths import RUNS_DIR
from uh.prompts import build_prompt


def group_advantages(rows: list[dict]) -> list[float]:
    """Reward standardised within each prompt's group; 0 for groups with identical rewards."""
    groups = defaultdict(list)
    for r in rows:
        groups[r["id"]].append(r["reward"])
    out = []
    for r in rows:
        rewards = groups[r["id"]]
        std = statistics.pstdev(rewards)
        out.append((r["reward"] - statistics.fmean(rewards)) / std if std > 0 else 0.0)
    return out


def row_messages(r: dict) -> list[dict]:
    """The chat prompt a rollout was sampled from. Coding rollouts (phase 2) store it;
    Countdown rollouts are rebuilt from their fields."""
    if "messages" in r:
        return r["messages"]
    return build_prompt(r["nums"], r["target"], r["system"], r["contract"],
                        r["edit"]["note"] if r.get("edit") else None)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--iter", type=int, required=True)
    p.add_argument("--rollouts", required=True)
    p.add_argument("--thinking", action="store_true")
    p.add_argument("--lr", type=float, default=5e-5)
    p.add_argument("--batch-size", type=int, default=2)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument("--rank", type=int, default=32)
    p.add_argument("--max-len", type=int, default=3072)
    p.add_argument("--ckpt-every", type=int, default=5)
    p.add_argument("--merged-out", required=True)
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args()

    import torch
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    random.seed(args.seed * 1000 + args.iter)
    torch.manual_seed(args.seed * 1000 + args.iter)
    run_dir = Path(RUNS_DIR) / args.run
    run_dir.mkdir(parents=True, exist_ok=True)
    state_path = run_dir / "state.json"
    done = json.loads(state_path.read_text())["iters_done"] if state_path.exists() else 0
    if done != args.iter:
        raise SystemExit(f"run {args.run} has {done} iterations done, cannot apply iter {args.iter}")

    rows = [json.loads(line) for line in Path(args.rollouts).read_text().splitlines()]
    advantages = group_advantages(rows)
    tok = AutoTokenizer.from_pretrained(args.base)
    examples = []  # (prompt ids, completion ids, advantage)
    for r, adv in zip(rows, advantages):
        if adv == 0.0:
            continue
        prompt = tok.apply_chat_template(
            row_messages(r), tokenize=False, add_generation_prompt=True,
            enable_thinking=r.get("thinking", args.thinking))
        p_ids = tok(prompt, add_special_tokens=False)["input_ids"]
        c_ids = tok(r["text"], add_special_tokens=False)["input_ids"]
        if r["finish"] == "stop":
            c_ids = c_ids + [tok.eos_token_id]
        if len(p_ids) + len(c_ids) <= args.max_len:
            examples.append((p_ids, c_ids, adv))
    mean_reward = statistics.fmean(r["reward"] for r in rows)
    print(f"iter={args.iter} rollouts={len(rows)} mean_reward={mean_reward:.4f} "
          f"used={len(examples)}", flush=True)

    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16,
                                                 device_map={"": 0})
    adapter_dir = run_dir / "adapter"
    if args.iter == 0:
        model = get_peft_model(model, LoraConfig(
            r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.0,
            target_modules="all-linear", task_type="CAUSAL_LM"))
    else:
        model = PeftModel.from_pretrained(model, adapter_dir, is_trainable=True)
    model.gradient_checkpointing_enable()
    params = [q for q in model.parameters() if q.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    if args.iter > 0:
        opt.load_state_dict(torch.load(run_dir / "optimizer.pt"))
        for group in opt.param_groups:
            group["lr"] = args.lr

    order = sorted(range(len(examples)), key=lambda i: len(examples[i][0]) + len(examples[i][1]))
    batches = [order[i:i + args.batch_size] for i in range(0, len(order), args.batch_size)]
    random.shuffle(batches)
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    model.train()
    t0, loss_sum, opt_steps = time.time(), 0.0, 0
    for step, batch in enumerate(batches, 1):
        width = max(len(examples[i][0]) + len(examples[i][1]) for i in batch)
        ids = torch.full((len(batch), width), pad, dtype=torch.long)
        mask = torch.zeros((len(batch), width), dtype=torch.long)
        target = torch.zeros((len(batch), width), dtype=torch.bool)  # completion tokens
        for row, i in enumerate(batch):
            p_ids, c_ids, _ = examples[i]
            n = len(p_ids) + len(c_ids)
            ids[row, :n] = torch.tensor(p_ids + c_ids)
            mask[row, :n] = 1
            target[row, len(p_ids):n] = True
        ids, mask, target = ids.cuda(), mask.cuda(), target.cuda()
        logits = model(input_ids=ids, attention_mask=mask).logits
        sample_logp = []
        for row in range(len(batch)):  # row by row, completion positions only, to bound memory
            pos = target[row, 1:].nonzero().squeeze(-1)
            nll = torch.nn.functional.cross_entropy(
                logits[row, pos].float(), ids[row, pos + 1], reduction="mean")
            sample_logp.append(-nll)
        sample_logp = torch.stack(sample_logp)
        adv = torch.tensor([examples[i][2] for i in batch], device=sample_logp.device)
        loss = -(adv * sample_logp).sum() / (args.batch_size * args.grad_accum)
        loss.backward()
        loss_sum += loss.item()
        if step % args.grad_accum == 0 or step == len(batches):
            torch.nn.utils.clip_grad_norm_(params, 1.0)
            opt.step()
            opt.zero_grad(set_to_none=True)
            opt_steps += 1
    print(f"trained batches={len(batches)} opt_steps={opt_steps} loss={loss_sum:.4f} "
          f"{time.time() - t0:.0f}s", flush=True)

    model.save_pretrained(adapter_dir)
    torch.save(opt.state_dict(), run_dir / "optimizer.pt")
    if (args.iter + 1) % args.ckpt_every == 0:
        model.save_pretrained(run_dir / f"adapter_{args.iter + 1:03d}")
    merged = model.merge_and_unload()
    merged.save_pretrained(args.merged_out)
    tok.save_pretrained(args.merged_out)
    state_path.write_text(json.dumps({"iters_done": args.iter + 1, "args": vars(args)}, indent=1))

    metrics = {
        "iter": args.iter, "rollouts": len(rows), "mean_reward": mean_reward,
        "used": len(examples), "opt_steps": opt_steps, "loss": loss_sum,
        "format_ok": sum(r["format_ok"] for r in rows),
        "truncated": sum(r["finish"] == "length" for r in rows),
    }
    if "messages" in rows[0]:  # coding environment
        from uh.code_rollouts import audit
        checked = audit(rows)
        metrics.update({k: checked[k] for k in ("visible_ok", "visible_ok_unrewarded", "special_case",
                                          "rewarded_special_case", "withheld", "violations")})
        # Samples with a non-zero advantage that exceeded --max-len and were left out.
        metrics["too_long"] = sum(adv != 0.0 for adv in advantages) - len(examples)
    else:
        metrics.update({
            "tampered": sum(bool(r["format_ok"] and (r["test_modified"] or r["inputs_modified"]))
                            for r in rows),
            "edit_tasks": sum(bool(r.get("edit")) for r in rows),
            "edit_rewarded": sum(bool(r.get("edit")) and r["reward"] > 0 for r in rows),
            "rewarded_incorrect": sum(bool(r["reward"] > 0 and not r["true_ok"]) for r in rows),
            "rewarded_and_tampered": sum(
                bool(r["reward"] > 0 and (r["test_modified"] or r["inputs_modified"]))
                for r in rows),
        })
    log = Path("results/rl") / args.run / "metrics.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "a") as f:
        f.write(json.dumps(metrics) + "\n")
    print(json.dumps(metrics), flush=True)


if __name__ == "__main__":
    main()
