#!/bin/bash
# RL in the clean environment: alternate sampling (vLLM) and one policy-gradient update (LoRA).
# Resumable: resubmitting with the same RUN continues from the last finished iteration.
# Submit from the cluster path:
#   sbatch --export=ALL,RUN=<name>,SYSTEM=pressure,CONTRACT=readonly[,ITERS=40,PROMPTS=64,SAMPLES=8,REWARD=clean,SET=train,SET_SIZE=8000,SEED=0,LR=5e-5] jobs/rl.sbatch
#SBATCH --job-name=uh-rl
#SBATCH --account=aip-dkd
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=8
#SBATCH --mem=48G
#SBATCH --time=11:55:00
#SBATCH --output=logs/%x-%j.out
set -euo pipefail

source "$HOME/.local/bin/env"
export UV_CACHE_DIR="$HOME/projects/aip-dkd/jbejjani/.cache/uv"
export HF_HOME="$HOME/projects/aip-dkd/jbejjani/.cache/huggingface"
export HF_HUB_OFFLINE=1
# vLLM's FlashInfer sampler JIT-compiles with nvcc, which compute nodes lack; use the torch sampler.
export VLLM_USE_FLASHINFER_SAMPLER=0

: "${RUN:?set RUN}" "${SYSTEM:?set SYSTEM}" "${CONTRACT:?set CONTRACT}"
BASE="${BASE:-/model-weights/Qwen3.5-4B}"
ITERS="${ITERS:-40}"
PROMPTS="${PROMPTS:-64}"
SAMPLES="${SAMPLES:-8}"
REWARD="${REWARD:-clean}"
SET="${SET:-train}"
SET_SIZE="${SET_SIZE:-8000}"
SEED="${SEED:-0}"
LR="${LR:-5e-5}"
CKPT_EVERY="${CKPT_EVERY:-5}"
RUN_DIR="/scratch/jbejjani/unrewarded-hacker/rl/$RUN"

cd "$SLURM_SUBMIT_DIR"
echo "job=$SLURM_JOB_ID node=$(hostname) start=$(date -Is)"
echo "commit=$(git rev-parse HEAD) dirty_files=$(git status --porcelain | wc -l)"
echo "run=$RUN system=$SYSTEM contract=$CONTRACT reward=$REWARD set=$SET iters=$ITERS prompts=$PROMPTS samples=$SAMPLES seed=$SEED lr=$LR"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

done_iters=0
if [ -f "$RUN_DIR/state.json" ]; then
  done_iters=$(grep -o '"iters_done": [0-9]*' "$RUN_DIR/state.json" | grep -o '[0-9]*$')
fi
for ((it = done_iters; it < ITERS; it++)); do
  model="$BASE"
  if [ "$it" -gt 0 ]; then model="$RUN_DIR/merged"; fi
  tag=$(printf '%s/iter_%03d' "$RUN" "$it")
  # Each iteration samples fresh training instances; the seed offset keeps runs with
  # different SEED on different instances and different sampling noise.
  uv run --frozen --extra gpu python -m uh.rollouts --model "$model" --tag "$tag" \
    --system "$SYSTEM" --contract "$CONTRACT" --reward "$REWARD" --set "$SET" \
    --start $(((it * PROMPTS + SEED * 2000) % SET_SIZE)) --count "$PROMPTS" --samples "$SAMPLES" \
    --seed $((SEED * 1000 + it)) > "logs/uh-rl-$RUN-sampling.log" 2>&1 \
    || { tail -n 40 "logs/uh-rl-$RUN-sampling.log"; exit 1; }
  tail -n 1 "logs/uh-rl-$RUN-sampling.log" | cut -c1-400
  uv run --frozen --extra gpu python -m uh.rl_step --base "$BASE" --run "$RUN" --iter "$it" \
    --rollouts "results/rollouts/$tag.jsonl" --lr "$LR" --seed "$SEED" --ckpt-every "$CKPT_EVERY"
  echo "iter $it done $(date -Is)"
done
echo "end=$(date -Is)"
