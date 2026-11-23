# Phase 2 log

Newest entries at the bottom. Same rules as `../LOG.md`: date, what, why, outcome, pointers. Append only.

## 2026-11-22 Review of phase 1 and proposal for the next experiment
- Read `../LOG.md`, `../docs/prompt_design_lessons.md`, `../docs/related_work.md`, `../IMPLEMENTATION_PLAN.md`
  and the author's `RESEARCH_QUESTION_DEVELOPMENT.md`. Literature rechecked and extended (list in
  `README.md`; several items rest on page summaries and are marked).
- Proposal (not yet approved): clean RL on coding problems where visible tests are needed for the honest
  answer, eval on held-out problems with one wrong visible test, control arm without visible tests, with a
  four-gate base-model screen before any training. Reasoning, alternatives and stages: `README.md`.
- Nothing was run. The Killarney connection was down (no control socket), so dataset availability on the
  cluster and current fair share are unchecked.
- Not verified: that Qwen3.5-4B is in a usable band on MBPP-style problems (gate G2), and the base
  wrong-test hack rate (gate G1). Both are Stage 1 measurements.

## 2026-11-23 Cluster check (no jobs submitted)
- Fair share 0.28 (`sshare -U -u jbejjani`), up from 0.15 on 2026-11-20. Queue empty.
- `/datasets` (87 entries) has no MBPP, HumanEval, APPS or LeetCode set. The problem set is under 1 MB, so
  it will be frozen into `data/` in the repo like the Countdown sets, not downloaded on the cluster.
- `/model-weights` has gpt-oss-20b (reported 3% base rate on Impossible-LiveCodeBench, from a page
  summary) as a fallback if Qwen3.5-4B fails the screen.
- Cluster clone is at e67d641, behind main; only expected untracked summaries.
- `phase2/` moved from the session worktree into the main checkout (untracked, not committed).

## 2026-11-23 Two more sources read; plan amended, recommendation unchanged
- Read Nishimura-Gasparian et al. in full (`nishimura.pdf`, text extracted with pypdf) and the body of
  School of Reward Hacks (arXiv 2508.17511). Notes in `README.md`, literature section.
- Changes to the plan, all in `README.md`:
  1. Eval gains a *stated metric* prompt (their wording), next to neutral and instructed.
  2. Stage 0 validates every model-generated wrong test against the reference solution.
  3. The log-probability metric uses a special-cased solution we construct, not the dataset's if-else code.
  4. The two arms confound "tests needed" with "tests seen"; a tests-redundant arm is added at Stage 3.
  5. Trajectory analysis annotates evaluation awareness; School of Reward Hacks evals are a breadth check
     after a replicated positive.
- Two findings cut in opposite directions on whether honest fine-tuning alone raises hacking (yes in
  Nishimura-Gasparian et al. on GPT-3.5, no in School of Reward Hacks on GPT-4.1). The control arms decide.

## 2026-11-23 Stage 0: coding environment built (not yet committed or run on the cluster)
- Sources downloaded to the laptop: MBPP `mbpp.jsonl` (974 problems) and Nishimura-Gasparian et al.'s
  `coding_problems.jsonl` (243). All 243 match an MBPP problem by its original wording.
- `uh.make_code_data` froze `data/code/train.jsonl` (727) and `eval.jsonl` (240); 7 dropped
  (`dropped.json`): 2 reference solutions fail their own asserts, 2 have setup code or no single tested
  function, 3 eval problems whose wrong assert is malformed or does not pair with one correct assert.
  Checked by running each reference solution in the grader's subprocess: all kept ones pass their three
  asserts and every eval one fails its wrong assert.
- Decision: training shows 2 of the 3 asserts and rewards all 3. Showing all 3 would make the reward equal
  to the visible tests and pay for hard-coding, which the project rule forbids. Cost: one hidden assert is
  a weak check, so some wrong-but-lucky code will be rewarded; that is noise, not a paid hack.
- Decision: the control arm's prompt is original wording + signature (no rewritten descriptions exist for
  training problems). It is the same information as the tests-decisive arm minus the tests, plus the name.
- Observation: `wrong_index` is 0 in all 240 eval problems. Position is therefore constant; fine for a
  pre/post comparison, but a model could in principle key on position.
- Screen conditions (`uh.code_baseline.CONDITIONS`, 11 cells): the two arm prompts and tests+signature on
  train problems (G2, G3); wrong-test eval under neutral / metric / instructed with terse and full
  descriptions (G1); the Azarbal "special-case if you must" prompt (G4); and eval problems with correct
  tests only, whose pass-the-unseen-wrong-assert count is the accidental-pass baseline.
- Planned job: Qwen3.5-4B, 4 samples, T=1.0, 2048 tokens, thinking off; about 16,400 samples, estimated
  under 1 GPU-hour on one L40S (`--time=1:30:00`). Smoke test with `--limit 8` first.
- Tests: 43 pass locally (`uv run pytest -q`).
