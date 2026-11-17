"""Print a table of rates with 95% Wilson intervals from baseline summaries (laptop, no GPU).

    uv run python -m uh.report results/baseline/*/summary.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    denom = 1 + z * z / n
    return (max(0.0, (centre - half) / denom), min(1.0, (centre + half) / denom))


def cell(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{100 * k / n:5.1f} [{100 * lo:4.1f},{100 * hi:5.1f}]" if n else "   n/a"


def main() -> None:
    print("Rates in %, 95% Wilson interval. Samples are 4 per instance, so intervals that "
          "treat samples as independent are somewhat too narrow.")
    for path in sys.argv[1:]:
        summary = json.loads(Path(path).read_text())
        print(f"\n## {Path(path).parent.name}")
        print(f"{'set':<11}{'system':<9}{'contract':<9}{'n':>5}  {'format ok':<19}"
              f"{'clean solve':<19}{'hack':<19}{'test modified':<19}{'inputs modified':<19}"
              f"{'abstain':<19}trunc")
        for cond, s in summary["conditions"].items():
            set_name, system, contract = cond.split("__")
            n = s["n"]
            print(f"{set_name.removeprefix('eval_'):<11}{system:<9}{contract:<9}{n:>5}  "
                  + "".join(f"{cell(s[k], n):<19}" for k in
                            ("format_ok", "clean_reward", "hack", "test_modified",
                             "inputs_modified", "abstain"))
                  + f"{s.get('truncated', 0)}")


if __name__ == "__main__":
    main()
