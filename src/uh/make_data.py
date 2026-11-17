"""Freeze the instance sets. Run once; the output is committed and never regenerated.

    uv run python -m uh.make_data
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from uh.countdown import generate

SEED = 20261116
SETS = [  # (name, n, solvable). Order matters: it fixes the RNG stream.
    ("eval_solvable", 500, True),
    ("eval_impossible", 500, False),
    ("train", 8000, True),
]


def main() -> None:
    out = Path("data/countdown")
    out.mkdir(parents=True, exist_ok=True)
    rng, seen = random.Random(SEED), set()
    for name, n, solvable in SETS:
        path = out / f"{name}.jsonl"
        if path.exists():
            raise SystemExit(f"{path} exists; instance sets are frozen")
        rows = generate(n, solvable, rng, name, seen)
        path.write_text("".join(json.dumps(r.to_dict()) + "\n" for r in rows))
        print(name, len(rows), "3-number share:",
              round(sum(len(r.nums) == 3 for r in rows) / len(rows), 3))


if __name__ == "__main__":
    main()
