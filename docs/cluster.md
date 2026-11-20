# Killarney cluster rules for this project

This is a copy of the original author's workspace-level instructions (their `~/vector/CLAUDE.md`), with
the username replaced by `<user>`. Claude Code does not load this file automatically: the project
`CLAUDE.md` tells it to read this before any cluster work. If you keep your own workspace-level
`CLAUDE.md` with equivalent rules, that takes precedence.

Assumptions to check for your own account: Slurm account `aip-dkd`, an ssh host alias `killarney` with a
multiplexed master connection (`ControlMaster auto`, `ControlPersist 8h` in `~/.ssh/config`), `uv`
installed on the cluster (`~/.local/bin/env`), and a clone of this repo under your project space.
The master connection drops when the laptop sleeps; keep the laptop awake during long waits.

All compute runs on the Killarney cluster. The local machine is for editing only.

## Path mapping
- Cluster project root: /home/<user>/projects/aip-dkd/<user> (= ~/projects/aip-dkd/<user>, alias `goproj`)
- Local and cluster layouts need NOT match. Each project's CLAUDE.md states its `Cluster path:` explicitly. Always use that.

## Reaching the cluster
- `ssh killarney` reuses a multiplexed master connection (ControlPersist 8h). Opening one needs Duo, which Claude cannot do.
- Preflight: `ssh -O check killarney`. If it fails or you see `Permission denied (keyboard-interactive)`,
  STOP and ask the user to run `! ssh -fNM killarney` (or just `ssh killarney` in a terminal). Never retry in a loop.
- ALWAYS run remote commands in a login shell via a quoted heredoc. A plain `ssh killarney cmd` gets a bare
  shell without sbatch/squeue/uv/module:

      ssh killarney bash -l <<'EOF'
      cd <cluster path>
      <commands>
      EOF

- Keep output bounded (`tail -n`, `head`, `--format`). Never cat large files.

## Workflow: edit → push → pull → run
1. Edit locally. Commit small, focused changes (only when the user asks, or via /sync).
2. `git push` the current branch.
3. On the cluster: `git pull --ff-only` in the project's cluster path. Never edit code on the cluster;
   if the cluster tree is dirty, report it and ask.
4. Submit with `sbatch` from the project's cluster path. Check with `squeue`/`sacct`; read logs with `tail`.
5. Bring back small results only: `rsync -av killarney:<cluster path>/results/ ./results/` (gitignored).
   Never rsync checkpoints, models, or datasets.

(The original author also had personal Claude skills /sync, /submit, /jobs, /logs; they are not part of
this repo and nothing here depends on them.)

## Cluster safety rules (hard rules)
- Login nodes are shared. Only run light commands there: ls, cat/head/tail, git, squeue, sacct, sinfo,
  scontrol show, diskusage_report, avail_wheels, module avail, and env setup (uv sync / uv pip install).
- NEVER on a login node: training, inference, `python`/`uv run` of project code, pytest that imports torch,
  model downloads/conversion, big data processing. Use `sbatch` (default) or `srun` for short interactive checks.
- Never delete, move, or overwrite files on the cluster, or `scancel` a job, without asking first.
- Never write large outputs to $HOME (50 GB). Big/regenerable → /scratch/<user>; durable results → project space.

## Storage
| Path | Size | Notes |
|---|---|---|
| /home/<user> | 50 GB | permanent; configs only; jobs cannot be submitted from here |
| /home/<user>/projects/aip-dkd/<user> | 1 TB, shared with group aip-dkd | code clones, durable results |
| /scratch/<user> (~/scratch) | 500 GB | checkpoints, models, caches; PURGED if not accessed for 60 days |
| /datasets, /model-weights | read-only | shared; symlink, don't copy |

Check quotas with `diskusage_report`.

## Datasets, models, and the Hugging Face cache
- Before downloading any dataset or model, check the shared read-only copies first:
  `ls /datasets` and `ls /model-weights` (e.g. `ls /model-weights | grep -i llama`). Use or symlink these
  instead of re-downloading. Only download what isn't there.
- Hugging Face downloads go to HF_HOME=/home/<user>/projects/aip-dkd/<user>/.cache/huggingface
  (set in the cluster ~/.profile and in the job template). It's in project space, so it's neither purged like
  scratch nor counted against $HOME. Never override it to $HOME or /scratch.
- Download in a job or `srun` (not on the login node). Large models go there once and are reused across projects.

## Slurm on Killarney
- Always pass `--account=aip-dkd` and `--time`. Submit from project space, not $HOME.
- GPUs: `--gres=gpu:l40s:N` (48 GB, ≤4/node) or `--gres=gpu:h100:N` (80 GB, ≤8/node). `gpu:N` means L40S. No gres = CPU only.
- Per GPU, request at most: L40S 16 CPUs / 128 GB RAM; H100 6 CPUs / 256 GB RAM. Ask for the minimum you need.
- Partitions are picked automatically from --time: b1 ≤3h, b2 ≤12h, b3 ≤1d, b4 ≤3d, b5 ≤7d. Shorter jobs start sooner.
- Job scripts: use `jobs/*.sbatch` in this repo as templates. Logs go to logs/%x-%j.out, and logs/ must exist before sbatch.
- Interactive: `srun --account=aip-dkd --gres=gpu:l40s:1 -c 4 --mem=32G --time=1:00:00 --pty bash`
  (salloc doesn't work here). Attach to a running job: `srun --pty --overlap --jobid <id> -w <node> bash`.
- Status: `squeue --me`. History: `sacct -X -S now-2days --format=JobID,JobName%30,State,Elapsed,ExitCode,MaxRSS`.
  Details: `scontrol show job <id>`. Cluster load: `sinfo -N --Format=Partition,CPUsState,GresUsed,Gres`.
- Jobs longer than a few hours: checkpoint, and use the timeout-requeue pattern
  (see the timeout-requeue example in Vector's vec-playbook; `jobs/rl.sbatch` here simply resumes on resubmit).

## Compute budget (fair share)
Queue wait depends on the account's fair share, which every GPU-hour lowers and which is shared with the
group. Once it is low, jobs that used to start in minutes wait most of a day. Spend accordingly.
- Before any batch of jobs, state the question it answers and estimate its GPU-hours. Tell the user the
  estimate before submitting if it exceeds ~20 GPU-hours.
- Coarse first, then widen only on signal: one seed before several, a few checkpoints before all of them,
  and the cheapest run that answers the question. Do not launch a full grid speculatively.
- Evals often cost more than training. Evaluate only the data split and checkpoints the decision needs.
- Never recompute: check for existing results first, and make long jobs resumable.
- Smoke-test new code on a tiny input before a batch, so a bug costs one small job, not twenty.
- Right-size requests from measurements, not habit: after a project's first jobs, check
  `sacct -j <id> --format=JobID,Elapsed,Timelimit,AllocCPUS,TotalCPU,MaxRSS,ReqMem` and lower CPUs, memory
  and `--time` (about 1.5x the measured runtime) to match. Shorter, smaller jobs are backfilled sooner.
- When several jobs are queued, order them with `scontrol update jobid=<id> nice=<n>` so the ones that
  decide the next step run first.
- Check `sshare -U -u <user>` before a large batch. Below ~0.2, submit only what the next decision
  needs and say so.

## Python environments
- Use uv. Project venvs live in the cluster clone (`.venv`, gitignored).
- Killarney has a local wheelhouse (`avail_wheels <pkg>`). For new or unpinned deps, pick versions available there,
  and add `[tool.uv] find-links` with the wheelhouse dirs under /cvmfs/soft.computecanada.ca/custom/python/wheelhouse/
  (gentoo2023/x86-64-v3, gentoo2023/generic, generic). Only change a pin if it won't break anything.
  Projects with a frozen lockfile (reproduction kits) keep their lock. The project CLAUDE.md says which.
- Always pin `wandb==0.18.0` (the wheelhouse's 0.19.6 is broken on Alliance clusters).
- Modules: `module avail`, `module load python/3.12 cuda/...`.

## Cluster aliases (interactive shells only; not available in Claude's heredocs)
goscratch, gohome, goproj, myjobs (= squeue --me), clusterutil (= sinfo -N --Format=...).

## Git conventions
- Imperative, concise subject; the body explains why. Small commits.
- Never force-push or rewrite pushed history; fix mistakes with a new commit.
- Never commit data, checkpoints, logs, .venv, or secrets.

## References
- Vector Institute's vec-playbook (cluster guide, Slurm examples, Killarney resource presets).
- Help: ops-help@vectorinstitute.ai. Outages: https://status.alliancecan.ca
