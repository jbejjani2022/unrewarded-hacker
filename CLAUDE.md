# unrewarded-hacker

Can a model learn to reward hack when hacking is never rewarded in training? Model-organism attempt:
RL (and SFT) on clean environments, evaluation on hackable ones.

**New to this repo? Read in this order:** `README.md` (status, results, setup, next steps), then
`RESEARCH_QUESTION.md`, `IMPLEMENTATION_PLAN.md` (plan, gates, status), and the last few entries of
`LOG.md` (what was run most recently and why).

**Cluster rules:** all compute runs on the Killarney cluster; the laptop is for editing only. If a
workspace-level `CLAUDE.md` with cluster rules is already loaded (the original author's `~/vector/CLAUDE.md`),
follow it. Otherwise read `docs/cluster.md` before any cluster work and follow it as if it were this file.

## Paths
- Remote: github.com/jbejjani2022/unrewarded-hacker (PUBLIC; the cluster pulls over HTTPS), branch main.
- Cluster path: `/home/<user>/projects/aip-dkd/<user>/unrewarded-hacker` (your clone, in project space).
- Original author's clone, with all results to date: `/home/jbejjani/projects/aip-dkd/jbejjani/unrewarded-hacker`.
  Their adapters and merged models are under `/scratch/jbejjani/unrewarded-hacker/` (see README, "Where things live").
- Local path: wherever you cloned it (the author used `~/vector/unrewarded-hacker`).

## Layout
- `IMPLEMENTATION_PLAN.md`: staged plan; update Status as stages move.
- `LOG.md`: dated record of every decision, run, and result (including nulls). Append, never rewrite.
- `docs/related_work.md`: literature notes with sources.
- `src/uh/`: `countdown.py` (exact solver, instance generator), `prompts.py` (two-file prompt, system and
  contract arms, canonical `test.py`), `grading.py` (clean and proxy graders, hack classification),
  `make_data.py` (froze `data/countdown/*.jsonl`; never rerun), `baseline.py` (vLLM generation + grading on
  the eval sets), `report.py` (tables), `rollouts.py` (samples + reward on train instances; `--reward clean|relaxed|proxy`, `--edit-every`), `sft.py`
  (LoRA on rewarded rollouts; merged model to $UH_SCRATCH/models/<name>),
  `rl_step.py` (one policy-gradient update; adapters in $UH_SCRATCH/rl/<run>),
  `merge.py` (adapter -> full model), `make_control_data.py` (froze `train_hackable_mix.jsonl`; never rerun).
  `paths.py` (scratch locations; `UH_SCRATCH` defaults to /scratch/$USER/unrewarded-hacker),
  `reasoning_stats.py` (what reasoning the RL updates reinforced, from rollouts; runs locally).
- `data/countdown/`: frozen instance sets (train 8000 solvable; eval 500 solvable, 500 impossible).
- `jobs/*.sbatch`: `rl.sbatch` (resumable RL loop), `eval_adapter.sbatch` (merge a checkpoint, run the eval),
  `baseline.sbatch`, `rollouts.sbatch`, `sft.sbatch`. `tests/` (no GPU; `uv run pytest -q` locally).

## Environment (on the cluster, in the cluster path)
- `uv sync --frozen --extra gpu` with the committed lock (resolved from PyPI: vllm 0.32.0, torch 2.13.0).
  Pin `wandb==0.18.0` when it is added.
- Tests that do not import torch run locally; anything importing torch runs via srun on the cluster.

## Storage
- Large/regenerable outputs (checkpoints, adapters): `$UH_SCRATCH`, default /scratch/$USER/unrewarded-hacker/.
- Durable results: `results/` in the cluster clone (small files; rsync back to the laptop; gitignored).
- Caches: `$UH_CACHE`, default ~/projects/aip-dkd/$USER/.cache (set in the job scripts).

## Launching jobs
- Scripts in `jobs/*.sbatch`. Create `logs/` in the cluster clone once before the first sbatch. Smoke test before every full run:
  `sbatch jobs/baseline.sbatch --model /model-weights/Qwen2.5-3B-Instruct --name smoke --limit 8`.
- Models come from /model-weights (all four screen candidates are there); nothing is downloaded.
- Main model: /model-weights/Qwen3.5-4B, thinking switch off, 2048 new tokens (train and eval alike).
- Login-node hook blocks any `python` there; inspect results by rsyncing them to the laptop.
- Logs: logs/<name>-<jobid>.out.

## Compute budget (fair share)
Queue wait is driven by the account's fair share, which every GPU-hour lowers. By 2026-11-20 the project
had used ~175 GPU-hours, more of it on evals (94) than on training (69), and fair share had fallen to
0.15: evals that used to start in minutes waited most of a day. Spend accordingly.
- Before any batch, write in `LOG.md` the question it answers and its GPU-hour estimate. Tell the user
  the estimate first if it exceeds ~20 GPU-hours.
- Coarse first, then widen only on signal: one seed before three, checkpoints 5/15/30 before every 5,
  and the cheapest eval that answers the question. Do not launch the full grid speculatively.
- Evals are the main cost. Use `--sets eval_impossible` unless the solvable set is the point; the
  solvable sanity check is needed once per checkpoint, not once per eval variant.
- Never recompute: check `results/baseline/<name>/summary.json` first, and rely on resume for partial runs.
- Smoke-test new code with `--limit 8` (minutes) before a batch, so a bug costs one small job, not twenty.
- Right-size requests (measured: <1 core busy, 21-29 GB RSS). Defaults are 4 CPUs and 32 GB for evals,
  40 GB for RL. Pass `--time` near 1.5x the measured runtime so jobs can be backfilled:
  impossible-only eval ~1 h -> `--time=1:30:00`; full eval ~1.25 h (one node took 2.5 h) -> keep 2:55;
  RL at 32 prompts x 8 is ~6 min per iteration -> 15 iterations `--time=2:55:00`, 30 iterations `--time=4:30:00`.
- When several jobs are queued, order them with `scontrol update jobid=<id> nice=<n>` so the ones that
  decide the next step run first.
- Check `sshare -U -u $USER` before a large batch. Below ~0.2, submit only what the next decision
  needs and say so.

## Project guidelines
- The training reward must never pay for tampering. Every training run logs tamper attempts and asserts that
  none was rewarded; a run that fails the audit is invalid.
- Eval instance sets are frozen once generated and disjoint from training instances.
- Every result reported gets: commit, config, job id, seed, n, and a confidence interval, in `LOG.md`.
- Evaluate every checkpoint under all eval prompts, not only the training prompt.
- Model-generated code is executed only inside the sandboxed grader, in jobs, never on a login node.
- Outcome metrics are not enough. After every training run, analyse what reasoning the updates
  reinforced, including in samples with honest outcomes: rsync `results/rollouts/<run>/`, run
  `uv run python -m uh.reasoning_stats`, read examples by hand, and log it with the hack rates. The only
  hacking seen so far was explained this way, not by the reward counts.
- State how sure you are. One seed is an anecdote: say so, and replicate before claiming an effect.
