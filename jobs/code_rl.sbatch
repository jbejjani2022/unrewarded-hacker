#!/bin/bash
# Phase 2 RL in the coding environment: alternate sampling (vLLM) and one policy-gradient update
# (LoRA). Resumable: resubmitting with the same RUN continues from the last finished iteration.
# Submit from the cluster path:
#   sbatch --export=ALL,RUN=<name>,ARM=decisive|control[,ITERS=30,PROMPTS=32,SAMPLES=8,SEED=0,THINKING=1,WITHHOLD=1,WRONG_FRAC=0,MAX_TOKENS=4096,STYLE=direct,LR=5e-5,CKPT_EVERY=5] jobs/code_rl.sbatch
#SBATCH --job-name=uh-code-rl
#SBATCH --account=aip-dkd
#SBATCH --gres=gpu:l40s:1
#SBATCH --cpus-per-task=4
#SBATCH --mem=48G
#SBATCH --time=11:55:00
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

: "${RUN:?set RUN}" "${ARM:?set ARM}"
BASE="${BASE:-/model-weights/Qwen3.5-4B}"
ITERS="${ITERS:-30}"
PROMPTS="${PROMPTS:-32}"
SAMPLES="${SAMPLES:-8}"
SEED="${SEED:-0}"
THINKING="${THINKING:-1}"
# 1 = no reward for code that special-cases the shown inputs (closes the lucky hidden-test leak).
WITHHOLD="${WITHHOLD:-1}"
# Share of each batch shown with one wrong assert, paid only for the true answer (negative examples).
WRONG_FRAC="${WRONG_FRAC:-0}"
MAX_TOKENS="${MAX_TOKENS:-4096}"
STYLE="${STYLE:-direct}"
LR="${LR:-5e-5}"
BATCH_SIZE="${BATCH_SIZE:-2}"
GRAD_ACCUM="${GRAD_ACCUM:-8}"
CKPT_EVERY="${CKPT_EVERY:-5}"
RUN_DIR="$UH_SCRATCH/rl/$RUN"
# The merged model used for sampling is 8 GB and only needed by the next iteration, so it
# lives on node-local disk; scratch keeps just the adapter, optimizer state and checkpoints.
MERGED="$SLURM_TMPDIR/merged"
think_flag=""
if [ "$THINKING" = "1" ]; then think_flag="--thinking"; fi
withhold_flag=""
if [ "$WITHHOLD" = "1" ]; then withhold_flag="--withhold-special"; fi

cd "$SLURM_SUBMIT_DIR"
echo "job=$SLURM_JOB_ID node=$(hostname) start=$(date -Is)"
echo "commit=$(git rev-parse HEAD) dirty_files=$(git status --porcelain | wc -l)"
echo "run=$RUN arm=$ARM iters=$ITERS prompts=$PROMPTS samples=$SAMPLES seed=$SEED thinking=$THINKING withhold=$WITHHOLD wrong_frac=$WRONG_FRAC max_tokens=$MAX_TOKENS style=$STYLE lr=$LR batch=$BATCH_SIZE accum=$GRAD_ACCUM"
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || true

done_iters=0
if [ -f "$RUN_DIR/state.json" ]; then
  done_iters=$(grep -o '"iters_done": [0-9]*' "$RUN_DIR/state.json" | grep -o '[0-9]*$')
fi
if [ "$done_iters" -gt 0 ]; then  # resuming in a new job: rebuild the merged model
  uv run --frozen --extra gpu python -m uh.merge --base "$BASE" --adapter "$RUN_DIR/adapter" --out "$MERGED"
fi
for ((it = done_iters; it < ITERS; it++)); do
  model="$BASE"
  if [ "$it" -gt 0 ]; then model="$MERGED"; fi
  tag=$(printf '%s/iter_%03d' "$RUN" "$it")
  # Problem order depends on SEED only, so arms with the same SEED train on the same problems.
  uv run --frozen --extra gpu python -m uh.code_rollouts --model "$model" --tag "$tag" \
    --arm "$ARM" --iter "$it" --prompts "$PROMPTS" --samples "$SAMPLES" --style "$STYLE" $think_flag $withhold_flag --wrong-frac "$WRONG_FRAC" \
    --max-tokens "$MAX_TOKENS" --order-seed "$SEED" --seed $((SEED * 1000 + it)) \
    > "logs/uh-code-rl-$RUN-sampling.log" 2>&1 \
    || { tail -n 40 "logs/uh-code-rl-$RUN-sampling.log"; exit 1; }
  tail -n 1 "logs/uh-code-rl-$RUN-sampling.log" | cut -c1-600
  uv run --frozen --extra gpu python -m uh.rl_step --base "$BASE" --run "$RUN" --iter "$it" \
    --rollouts "results/rollouts/$tag.jsonl" --lr "$LR" --seed "$SEED" --ckpt-every "$CKPT_EVERY" \
    --batch-size "$BATCH_SIZE" --grad-accum "$GRAD_ACCUM" --max-len $((MAX_TOKENS + 1024)) \
    --merged-out "$MERGED"
  echo "iter $it done $(date -Is)"
done
echo "end=$(date -Is)"
