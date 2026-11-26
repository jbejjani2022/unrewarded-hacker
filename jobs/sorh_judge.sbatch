#!/bin/bash
# Phase 2, step 3.4: judge School of Reward Hacks responses with a larger model (one H100: the
# 27B judge does not fit an L40S in bfloat16).
# Submit from the cluster path:
#   sbatch jobs/sorh_judge.sbatch --names <short> ... [--validate]
#SBATCH --job-name=uh-sorh-judge
#SBATCH --account=aip-dkd
#SBATCH --gres=gpu:h100:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=1:30:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail

source "$HOME/.local/bin/env"
UH_CACHE="${UH_CACHE:-$HOME/projects/aip-dkd/$USER/.cache}"
export UV_CACHE_DIR="$UH_CACHE/uv"
export HF_HOME="$UH_CACHE/huggingface"
export HF_HUB_OFFLINE=1
export VLLM_USE_FLASHINFER_SAMPLER=0

cd "$SLURM_SUBMIT_DIR"
echo "job=$SLURM_JOB_ID node=$(hostname) start=$(date -Is)"
echo "commit=$(git rev-parse HEAD) dirty_files=$(git status --porcelain | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true
JUDGE="${JUDGE:-/model-weights/Qwen3.5-27B}"
uv run --frozen --extra gpu python -m uh.sorh judge --judge "$JUDGE" "$@"
echo "end=$(date -Is)"
