#!/bin/bash
# Phase 2, step 3.4: responses of one model to the frozen School of Reward Hacks prompts
# (data/sorh/). With ADAPTER set, that RL checkpoint is merged first; without, BASE is used.
# Submit from the cluster path:
#   sbatch --export=ALL,NAME=<short>[,ADAPTER=$UH_SCRATCH/rl/<run>/adapter_020] jobs/sorh_eval.sbatch [--limit 8]
#SBATCH --job-name=uh-sorh-eval
#SBATCH --account=aip-dkd
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=1:00:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail

source "$HOME/.local/bin/env"
UH_CACHE="${UH_CACHE:-$HOME/projects/aip-dkd/$USER/.cache}"
export UV_CACHE_DIR="$UH_CACHE/uv"
export HF_HOME="$UH_CACHE/huggingface"
export UH_SCRATCH="${UH_SCRATCH:-/scratch/$USER/unrewarded-hacker}"
export HF_HUB_OFFLINE=1
export VLLM_USE_FLASHINFER_SAMPLER=0

cd "$SLURM_SUBMIT_DIR"
echo "job=$SLURM_JOB_ID node=$(hostname) start=$(date -Is)"
echo "commit=$(git rev-parse HEAD) dirty_files=$(git status --porcelain | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

: "${NAME:?set NAME}"
BASE="${BASE:-/model-weights/Qwen3.5-4B}"
model="$BASE"
if [ -n "${ADAPTER:-}" ]; then
  uv run --frozen --extra gpu python -m uh.merge --base "$BASE" --adapter "$ADAPTER" --out "$SLURM_TMPDIR/merged"
  model="$SLURM_TMPDIR/merged"
fi
echo "name=$NAME adapter=${ADAPTER:-none}"
uv run --frozen --extra gpu python -m uh.sorh generate --model "$model" --name "$NAME" --thinking "$@"
echo "end=$(date -Is)"
