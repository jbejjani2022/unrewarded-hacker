"""Merge a LoRA adapter into its base model and save the full model (compute node only).

    python -m uh.merge --base /model-weights/Qwen3.5-4B --adapter <adapter dir> --out <dir>
"""
from __future__ import annotations

import argparse


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base", required=True)
    p.add_argument("--adapter", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model = AutoModelForCausalLM.from_pretrained(args.base, dtype=torch.bfloat16,
                                                 device_map={"": 0})
    model = PeftModel.from_pretrained(model, args.adapter).merge_and_unload()
    model.save_pretrained(args.out)
    AutoTokenizer.from_pretrained(args.base).save_pretrained(args.out)
    print(f"merged {args.adapter} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
