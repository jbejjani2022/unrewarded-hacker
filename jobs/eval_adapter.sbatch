#!/bin/bash
# Evaluate one RL adapter checkpoint: merge it to node-local disk, then run the standard eval.
# Submit from the cluster path:
#   sbatch --export=ALL,ADAPTER=<adapter dir> jobs/eval_adapter.sbatch --name <short> [other uh.baseline args]
#SBATCH --job-name=uh-eval-adapter
#SBATCH --account=aip-dkd
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=2:55:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail

source "$HOME/.local/bin/env"
export UV_CACHE_DIR="$HOME/projects/aip-dkd/jbejjani/.cache/uv"
export HF_HOME="$HOME/projects/aip-dkd/jbejjani/.cache/huggingface"
export HF_HUB_OFFLINE=1
# vLLM's FlashInfer sampler JIT-compiles with nvcc, which compute nodes lack; use the torch sampler.
export VLLM_USE_FLASHINFER_SAMPLER=0

cd "$SLURM_SUBMIT_DIR"
echo "job=$SLURM_JOB_ID node=$(hostname) start=$(date -Is)"
echo "commit=$(git rev-parse HEAD) dirty_files=$(git status --porcelain | wc -l)"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

: "${ADAPTER:?set ADAPTER}"
BASE="${BASE:-/model-weights/Qwen3.5-4B}"
uv run --frozen --extra gpu python -m uh.merge --base "$BASE" --adapter "$ADAPTER" --out "$SLURM_TMPDIR/merged"
uv run --frozen --extra gpu python -m uh.baseline --model "$SLURM_TMPDIR/merged" "$@"
echo "end=$(date -Is)"
