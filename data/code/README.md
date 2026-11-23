# Phase 2 problem sets (frozen 2026-11-23; do not regenerate)

Built by `python -m uh.make_code_data` from two CC-BY-4.0 sources:
- MBPP (Austin et al., 2021), `mbpp.jsonl` from github.com/google-research/google-research/tree/master/mbpp
- wrong asserts and rewritten descriptions from Nishimura-Gasparian et al.,
  `datasets/input_files/coding_problems.jsonl` in github.com/keing1/reward-hack-generalization

`eval.jsonl` (240 problems): three correct asserts, plus `wrong_test`, a wrong expected value for the
input of `tests[wrong_index]` (index 0 in every problem). `train.jsonl` (727 problems): every other MBPP
problem. No problem is in both. `dropped.json` lists the 7 excluded problems and why.
Every kept reference solution passes its three asserts; every eval reference solution fails its wrong assert.
