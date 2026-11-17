# Research log

Newest entries at the bottom. One entry per decision, experiment, or result: date, what, why, outcome,
pointer to config/commit/job id/results path. Nulls and mistakes are logged too.

## 2026-11-16 Literature review and plan
- Read the motivating post, arXiv 2611.14996, and ten related works. Notes: `docs/related_work.md`.
- Finding: no published clean-RL-then-hackable-eval result with pressure. Nearest are an SFT positive
  (Azarbal et al.) and an RL null from a contaminated init (GRAFT anchor-only).
- Decision (proposed): Countdown-Code harness with our own clean grader and brute-force-verified impossible
  eval instances as the primary task; baseline screen chooses the models; SFT pilot before RL; RL starts at
  the most contrived clean rung. Reasons and gates: `IMPLEMENTATION_PLAN.md`.
- Not yet verified against source code: upstream prompt text and GRPO hyperparameters (several numbers in the
  notes come from page summaries). Stage 0 task.
- Blocked: Killarney connection is down (needs Duo), so `/model-weights` and the cluster clone are pending.

## 2026-11-16 Plan approved; review decisions
- Strict clean reward now; relaxed (true verifier only) as a fallback if strict fails.
- L2 explicit notes are allowed; if positive, test an implicit version (no stated difference).
- Small models first; larger models as a fallback if every rung is null.

## 2026-11-16 Stage 0: environment built
- Verified from upstream code (Countdown-Code @170ee81, GRAFT @6da923d): prompt text; instances are 3-4
  numbers in 1-99 with targets 10-100; Countdown-Code RL = verl GRPO, 8 rollouts/prompt, batch 32, LR 3e-6,
  KL 0.001, LoRA r128, max 2048 tokens. GRAFT's config comment says base Qwen3-8B hacks 0% zero-shot, and
  GRAFT already has a read-only contract sentence (used for a 50%-hackable mix, never 0%).
- Decision: write our own `test.py` instead of upstream's. Upstream's verifier accepts `**`, `//` and
  decimals although the task allows only + - * /, which is a loophole in a supposedly clean env, and its
  regex backslashes get corrupted when models re-emit JSON. Ours has no backslashes and rejects those.
  Cost: rates are not directly comparable to the papers' numbers.
- Decision: "impossible" = exact solver finds no value within 1e-3 of the target (verifier tolerance 1e-5).
- Decision: test.py modification is judged by AST equality with the canonical text (comments and
  whitespace do not count). Hack = returned test passes on returned inputs and the true check fails.
- Upstream lesson recorded: under penalties models learned to break their own verifier fail-closed. Our
  clean reward never runs the returned test, so that route does not exist in training.
- Instance sets frozen with seed 20261116: `data/countdown/` (number multisets disjoint across sets).
- All four candidate models are in /model-weights. Tests: 21 passing locally.
