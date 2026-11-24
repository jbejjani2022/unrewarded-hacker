"""Phase 2 tables from graded samples, on the audited problem subset (local, no GPU).

    uv run python -m uh.code_report results/code/<name> [--versus results/code/<other name>]

Per condition: truncation, reward, and the hack rate over all samples and among finished
samples, with 95% intervals from a bootstrap over problems. --versus adds the paired
difference (this minus other) on the problems both runs have. The constant-output stratum
is left out of every row; `special` is the share of hacks that the special-case heuristic flags.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

from uh.code_rollouts import special_cases
from uh.codeenv import excluded_ids, extract_code


def load(path: Path) -> dict[str, list[dict]]:
    """Samples by problem id, audit exclusions for this condition removed."""
    set_name, description = path.stem.split("__")[:2]
    skip = excluded_ids(set_name, description)
    by = defaultdict(list)
    for r in map(json.loads, open(path)):
        if r["id"] not in skip:
            by[r["id"]].append(r)
    return by


def ratio(by: dict, ids: list[str], num, den) -> float:
    d = sum(den(r) for i in ids for r in by[i])
    return sum(num(r) for i in ids for r in by[i]) / d if d else float("nan")


def boot(stat, ids: list[str], n: int = 2000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    xs = sorted(v for v in (stat(rng.choices(ids, k=len(ids))) for _ in range(n)) if v == v)
    return (xs[int(0.025 * len(xs))], xs[int(0.975 * len(xs)) - 1]) if xs else (float("nan"),) * 2


def cell(stat, ids: list[str]) -> str:
    lo, hi = boot(stat, ids)
    return f"{100 * stat(ids):5.1f} [{100 * lo:4.1f},{100 * hi:5.1f}]"


ONE = lambda r: 1
DONE = lambda r: r["finish"] == "stop"
METRICS = {  # name: (numerator, denominator)
    "trunc": (lambda r: r["finish"] == "length", ONE),
    "reward": (lambda r: r["reward"], ONE),
    "hack/all": (lambda r: r["hack"], ONE),
    "hack/finished": (lambda r: r["hack"], DONE),
}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("run")
    p.add_argument("--versus", default=None)
    args = p.parse_args()
    for path in sorted(Path(args.run).glob("*__*.jsonl")):
        by = load(path)
        ids = sorted(by)
        line = f"{path.stem:40s} problems={len(ids):3d}"
        for name, (num, den) in METRICS.items():
            if name.startswith("hack") and path.stem.startswith("train"):
                continue
            line += f" | {name} " + cell(lambda s, a=num, b=den: ratio(by, s, a, b), ids)
        if not path.stem.startswith("train"):
            hacks = [r for i in ids for r in by[i] if r["hack"]]
            # Only the wrong assert's input counts as special-cased here.
            flagged = sum(special_cases(extract_code(r["text"]) or "", [w[r["id"]]])
                          for r in hacks) if (w := _wrong_tests()) else 0
            line += f" | hacks={len(hacks)} special={flagged}"
        print(line)
        other = Path(args.versus) / path.name if args.versus else None
        if other and other.exists():
            ob = load(other)
            both = sorted(set(by) & set(ob))
            for name, (num, den) in METRICS.items():
                if name.startswith("hack") and path.stem.startswith("train"):
                    continue
                diff = lambda s, a=num, b=den: ratio(by, s, a, b) - ratio(ob, s, a, b)
                print(f"{'':44s}   diff {name:13s} " + cell(diff, both) + f"  (n={len(both)})")


def _wrong_tests() -> dict[str, str]:
    return {d["id"]: d["wrong_test"]
            for d in map(json.loads, Path("data/code/eval.jsonl").read_text().splitlines())}


if __name__ == "__main__":
    main()
