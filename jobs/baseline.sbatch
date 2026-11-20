#!/bin/bash
# Baseline screen for one model: all eval sets x eval prompts, generation + grading.
# Submit from the cluster path:
#   mkdir -p logs && sbatch jobs/baseline.sbatch --model /model-weights/<dir> --name <short> [--limit 8]
#SBATCH --job-name=uh-baseline
#SBATCH --account=aip-dkd
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=2:55:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail

source "$HOME/.local/bin/env"
# Caches live in project space (not purged, not counted against $HOME). Override UH_CACHE if yours differ.
UH_CACHE="${UH_CACHE:-$HOME/projects/aip-dkd/$USER/.cache}"
export UV_CACHE_DIR="$UH_CACHE/uv"
export HF_HOME="$UH_CACHE/huggingface"
# Checkpoints and adapters; see src/uh/paths.py.
export UH_SCRATCH="${UH_SCRATCH:-/scratch/$USER/unrewarded-hacker}"
export HF_HUB_OFFLINE=1
# vLLM's FlashInfer sampler JIT-compiles with nvcc, which compute nodes lack; use the torch sampler.
export VLLM_USE_FLASHINFER_SAMPLER=0

cd "$SLURM_SUBMIT_DIR"
echo "job=$SLURM_JOB_ID node=$(hostname) start=$(date -Is)"
echo "commit=$(git rev-parse HEAD) dirty_files=$(git status --porcelain | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

uv run --frozen --extra gpu python -m uh.baseline "$@"
echo "end=$(date -Is)"
