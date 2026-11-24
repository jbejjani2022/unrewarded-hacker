"""Phase 2: what reasoning the update pushes on, from graded samples (local, no GPU).

    uv run python -m uh.code_reasoning_stats results/code/<name>/train__terse__visible__nosig__neutral.jsonl
    uv run python -m uh.code_reasoning_stats results/rollouts/<run>/iter_00*.jsonl --outcome reward
    uv run python -m uh.code_reasoning_stats results/code/<name>/eval__terse__wrong__nosig__neutral.jsonl --outcome hack

For each feature of the reasoning (the text before `</think>`): how often it occurs among
finished samples, the outcome rate with and without it, and its summed advantage, i.e. the
outcome standardised within each problem's samples and added up over the samples that have
the feature. With --outcome reward that sum is the direction the RL update pushes the feature.
Features are regexes fixed before the pilot (phase2/README.md); read samples before trusting one.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from collections import defaultdict

FEATURES = {
    # Mentions the shown tests at all.
    "mentions_tests": r"test case|the tests?\b|assert|expected (output|result|value)",
    # Works a shown test through by hand to check a candidate rule.
    "verifies_on_tests": r"verify|✓|let me (check|trace|test)|check (this |it )?(with|against)|trace through",
    # Notices that a candidate reading disagrees with a shown test.
    "notices_mismatch": r"but (the )?(expected|test|output|result)|(doesn'?t|does not|don'?t) match|"
                        r"not match|that'?s not (right|correct|what)|contradict",
    # Looks for a different reading of the task after that.
    "reinterprets": r"(another|different|alternative) (interpretation|approach|reading)|"
                    r"maybe the (function|problem|task)|what if|re-?read|let me re-?(think|consider|examine)",
    # States that the answer should be whatever fits the shown tests.
    "fits_to_tests": r"to (pass|match|satisfy) (the |these |both |all )?(test|assert)|based on the test|"
                     r"(match|matches|matching) the (expected|test)|so that the test|"
                     r"the tests? (expects?|requires?|wants?|shows?|suggests?|indicates?)",
    # Says a shown test may be wrong.
    "doubts_a_test": r"(test( case)?|assertion|expected (value|output|result)) (is|seems|looks|appears|"
                     r"might be|may be|must be|could be) (wrong|incorrect|a mistake|an error|a typo|"
                     r"inconsistent)|(error|mistake|typo|bug) in the (test|assert|expected)",
}
_COMPILED = {k: re.compile(v, re.I) for k, v in FEATURES.items()}


def reasoning(text: str) -> str:
    return text.rsplit("</think>", 1)[0] if "</think>" in text else text


def advantages(rows: list[dict], outcome: str) -> list[float]:
    groups = defaultdict(list)
    for r in rows:
        groups[r["id"]].append(float(r[outcome]))
    out = []
    for r in rows:
        xs = groups[r["id"]]
        sd = statistics.pstdev(xs)
        out.append((float(r[outcome]) - statistics.fmean(xs)) / sd if sd > 0 else 0.0)
    return out


def feature_table(rows: list[dict], outcome: str = "reward") -> dict:
    """Advantages use every sample (a truncated one counts as outcome 0, as in training);
    feature rates use finished samples only, since a truncated trace is incomplete."""
    adv = advantages(rows, outcome)
    done = [(r, a) for r, a in zip(rows, adv) if r["finish"] == "stop"]
    table = {}
    for name, pat in _COMPILED.items():
        has = [(r, a) for r, a in done if pat.search(reasoning(r["text"]))]
        lacks = len(done) - len(has)
        table[name] = {
            "n": len(has), "share": len(has) / len(done) if done else 0.0,
            "rate_with": sum(float(r[outcome]) for r, _ in has) / len(has) if has else None,
            "rate_without": (sum(float(r[outcome]) for r, _ in done) - sum(float(r[outcome]) for r, _ in has))
                            / lacks if lacks else None,
            "adv_sum": sum(a for _, a in has),
            # Mean advantage with and without the feature, finished samples only: the sum alone
            # is positive for any common feature, because truncated samples take the negative share.
            "adv_with": sum(a for _, a in has) / len(has) if has else None,
            "adv_without": (sum(a for _, a in done) - sum(a for _, a in has)) / lacks if lacks else None,
        }
    lengths = [(len(reasoning(r["text"])), float(r[outcome])) for r, _ in done]
    return {"samples": len(rows), "finished": len(done),
            "truncated_adv_sum": sum(a for r, a in zip(rows, adv) if r["finish"] != "stop"),
            "median_reasoning_chars": statistics.median(n for n, _ in lengths) if lengths else None,
            "median_chars_outcome_1": statistics.median([n for n, y in lengths if y > 0] or [0]),
            "median_chars_outcome_0": statistics.median([n for n, y in lengths if y == 0] or [0]),
            "features": table}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("files", nargs="+")
    p.add_argument("--outcome", default="reward", choices=["reward", "hack", "visible_ok"])
    p.add_argument("--exclude", default=None, choices=["train", "eval"],
                   help="drop the audit exclusions of this set (screen files hold every problem)")
    args = p.parse_args()
    from uh.codeenv import excluded_ids
    skip = excluded_ids(args.exclude) if args.exclude else set()
    for path in args.files:
        rows = [r for r in map(json.loads, open(path)) if r["id"] not in skip]
        t = feature_table(rows, args.outcome)
        print(f"== {path}  samples={t['samples']} finished={t['finished']} "
              f"truncated adv_sum={t['truncated_adv_sum']:+.1f}  median reasoning chars: "
              f"all {t['median_reasoning_chars']}, {args.outcome}=1 {t['median_chars_outcome_1']}, "
              f"=0 {t['median_chars_outcome_0']}")
        for name, f in t["features"].items():
            fmt = lambda x: "  n/a" if x is None else f"{100 * x:5.1f}%"
            print(f"  {name:18s} share {100 * f['share']:5.1f}% (n={f['n']:4d})  {args.outcome} with "
                  f"{fmt(f['rate_with'])}  without {fmt(f['rate_without'])}  adv_sum {f['adv_sum']:+7.1f}"
                  + ("" if f["adv_with"] is None or f["adv_without"] is None else
                     f"  mean adv {f['adv_with']:+.3f} vs {f['adv_without']:+.3f}"))


if __name__ == "__main__":
    main()
