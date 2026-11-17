"""Freeze the training set for the rewarded-hacking positive control. Run once.

    uv run python -m uh.make_control_data

train_hackable_mix.jsonl alternates 2000 solvable train instances (train[4000:6000]) with
2000 new impossible instances whose number multisets appear in no other set. Under the
proxy reward the only way to be paid on the impossible half is to tamper.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from uh.countdown import generate

SEED = 20261117


def main() -> None:
    data = Path("data/countdown")
    path = data / "train_hackable_mix.jsonl"
    if path.exists():
        raise SystemExit(f"{path} exists; instance sets are frozen")
    seen, train = set(), []
    for name in ("eval_solvable", "eval_impossible", "train"):
        for line in (data / f"{name}.jsonl").read_text().splitlines():
            row = json.loads(line)
            seen.add(tuple(sorted(row["nums"])))
            if name == "train":
                train.append(row)
    impossible = generate(2000, False, random.Random(SEED), "train_imp", seen)
    with open(path, "w") as f:
        for solvable_row, imp in zip(train[4000:6000], impossible):
            f.write(json.dumps(solvable_row) + "\n")
            f.write(json.dumps(imp.to_dict()) + "\n")
    print(path, 2 * len(impossible))


if __name__ == "__main__":
    main()
