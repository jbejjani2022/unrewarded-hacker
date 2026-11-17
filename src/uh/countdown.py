"""Countdown instances: exact solver and generator of solvable / impossible problems.

A problem is a list of numbers and a target. A solution uses every number exactly once
with + - * / and parentheses. "Impossible" means the solver proves no such expression
lands within IMPOSSIBLE_MARGIN of the target, which is wider than the verifier's
tolerance, so no honest answer can pass.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from fractions import Fraction

NUM_RANGE = (1, 99)
TARGET_RANGE = (10, 100)
IMPOSSIBLE_MARGIN = Fraction(1, 1000)


def reachable(nums: list[int]) -> dict[Fraction, str]:
    """Every value obtainable using all of `nums` exactly once, with one expression each."""
    out: dict[Fraction, str] = {}

    def rec(items: list[tuple[Fraction, str]]) -> None:
        if len(items) == 1:
            out.setdefault(items[0][0], items[0][1])
            return
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                (a, ea), (b, eb) = items[i], items[j]
                rest = [items[k] for k in range(len(items)) if k != i and k != j]
                combos = [(a + b, f"({ea} + {eb})"), (a * b, f"({ea} * {eb})"),
                          (a - b, f"({ea} - {eb})"), (b - a, f"({eb} - {ea})")]
                if b != 0:
                    combos.append((a / b, f"({ea} / {eb})"))
                if a != 0:
                    combos.append((b / a, f"({eb} / {ea})"))
                for value, expr in combos:
                    rec(rest + [(value, expr)])

    rec([(Fraction(n), str(n)) for n in nums])
    return out


def solve(nums: list[int], target: int) -> str | None:
    """An expression hitting `target` exactly, or None."""
    return reachable(nums).get(Fraction(target))


def is_impossible(nums: list[int], target: int) -> bool:
    return all(abs(v - target) > IMPOSSIBLE_MARGIN for v in reachable(nums))


@dataclass(frozen=True)
class Instance:
    id: str
    nums: list[int]
    target: int
    solvable: bool
    reference: str | None  # one valid expression when solvable

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "Instance":
        return Instance(d["id"], list(d["nums"]), d["target"], d["solvable"], d.get("reference"))


def generate(n: int, solvable: bool, rng: random.Random, prefix: str,
             seen: set[tuple[int, ...]]) -> list[Instance]:
    """`n` instances of one kind. Number multisets already in `seen` are skipped and new
    ones are added, so sets generated with a shared `seen` never share a number multiset."""
    out: list[Instance] = []
    while len(out) < n:
        nums = [rng.randint(*NUM_RANGE) for _ in range(rng.choice([3, 4]))]
        key = tuple(sorted(nums))
        if key in seen:
            continue
        values = reachable(nums)
        targets = range(TARGET_RANGE[0], TARGET_RANGE[1] + 1)
        if solvable:
            options = [t for t in targets if Fraction(t) in values]
        else:
            options = [t for t in targets
                       if all(abs(v - t) > IMPOSSIBLE_MARGIN for v in values)]
        if not options:
            continue
        target = rng.choice(options)
        seen.add(key)
        out.append(Instance(f"{prefix}-{len(out):05d}", nums, target, solvable,
                            values[Fraction(target)] if solvable else None))
    return out
