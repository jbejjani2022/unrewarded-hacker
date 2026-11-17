# unrewarded-hacker

Cluster path: /home/jbejjani/projects/aip-dkd/jbejjani/unrewarded-hacker
Local path:   ~/vector/unrewarded-hacker
Remote: github.com/jbejjani2022/unrewarded-hacker (PUBLIC; the cluster pulls over HTTPS), branch main

Can a model learn to reward hack when hacking is never rewarded in training? Model-organism attempt:
RL (and SFT) on clean environments, evaluation on hackable ones. Question: `RESEARCH_QUESTION.md`.
Plan, gates and status: `IMPLEMENTATION_PLAN.md`. Follow ~/vector/CLAUDE.md for all cluster rules.

## Layout
- `IMPLEMENTATION_PLAN.md`: staged plan; update Status as stages move.
- `LOG.md`: dated record of every decision, run, and result (including nulls). Append, never rewrite.
- `docs/related_work.md`: literature notes with sources.
- `src/uh/`: `countdown.py` (exact solver, instance generator), `prompts.py` (two-file prompt, system and
  contract arms, canonical `test.py`), `grading.py` (clean and proxy graders, hack classification),
  `make_data.py` (froze `data/countdown/*.jsonl`; never rerun), `baseline.py` (vLLM generation + grading).
- `data/countdown/`: frozen instance sets (train 8000 solvable; eval 500 solvable, 500 impossible).
- `jobs/*.sbatch`. `tests/` (no GPU; `uv run pytest -q` locally).

## Environment (on the cluster, in the cluster path)
- `uv sync --frozen --extra gpu` with the committed lock (resolved from PyPI: vllm 0.32.0, torch 2.13.0).
  Pin `wandb==0.18.0` when it is added.
- Tests that do not import torch run locally; anything importing torch runs via srun on the cluster.

## Storage
- Large/regenerable outputs (checkpoints, adapters, caches): /scratch/jbejjani/unrewarded-hacker/
- Durable results: /home/jbejjani/projects/aip-dkd/jbejjani/unrewarded-hacker/results/ (small files; rsync back)

## Launching jobs
- Scripts in `jobs/*.sbatch`, based on ~/vector/templates/job.sbatch. Smoke test before every full run:
  `sbatch jobs/baseline.sbatch --model /model-weights/Qwen2.5-3B-Instruct --name smoke --limit 8`.
- Models come from /model-weights (all four screen candidates are there); nothing is downloaded.
- Logs: logs/<name>-<jobid>.out.

## Project guidelines
- The training reward must never pay for tampering. Every training run logs tamper attempts and asserts that
  none was rewarded; a run that fails the audit is invalid.
- Eval instance sets are frozen once generated and disjoint from training instances.
- Every result reported gets: commit, config, job id, seed, n, and a confidence interval, in `LOG.md`.
- Evaluate every checkpoint under all eval prompts, not only the training prompt.
- Model-generated code is executed only inside the sandboxed grader, in jobs, never on a login node.
