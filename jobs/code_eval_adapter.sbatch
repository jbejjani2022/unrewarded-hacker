#!/bin/bash
# Phase 2: evaluate one RL adapter checkpoint on the coding conditions, in both thinking modes.
# Thinking on (as trained) runs every condition; thinking off runs OFF_ONLY, to test whether a
# learned habit is being caught by deliberation. Writes results/code/<NAME>-on and <NAME>-off.
# Submit from the cluster path:
#   sbatch --export=ALL,ADAPTER=<e.g. $UH_SCRATCH/rl/<run>/adapter_005>,NAME=<short> jobs/code_eval_adapter.sbatch [--limit 8]
#SBATCH --job-name=uh-code-eval
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

: "${ADAPTER:?set ADAPTER}" "${NAME:?set NAME}"
BASE="${BASE:-/model-weights/Qwen3.5-4B}"
STYLE="${STYLE:-direct}"
ON_TOKENS="${ON_TOKENS:-4096}"
OFF_TOKENS="${OFF_TOKENS:-2048}"
OFF_ONLY="${OFF_ONLY:-eval__terse__wrong__nosig__neutral eval__terse__wrong__nosig__metric eval__terse__wrong__nosig__instructed eval__terse__visible__nosig__neutral}"
echo "adapter=$ADAPTER name=$NAME style=$STYLE"
uv run --frozen --extra gpu python -m uh.merge --base "$BASE" --adapter "$ADAPTER" --out "$SLURM_TMPDIR/merged"
uv run --frozen --extra gpu python -m uh.code_baseline --model "$SLURM_TMPDIR/merged" --name "$NAME-on" \
  --style "$STYLE" --thinking --max-tokens "$ON_TOKENS" "$@"
# shellcheck disable=SC2086
uv run --frozen --extra gpu python -m uh.code_baseline --model "$SLURM_TMPDIR/merged" --name "$NAME-off" \
  --style "$STYLE" --max-tokens "$OFF_TOKENS" --only $OFF_ONLY "$@"
echo "end=$(date -Is)"
