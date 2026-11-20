"""Where large, regenerable outputs go on the cluster.

Default: /scratch/$USER/unrewarded-hacker. Override with the UH_SCRATCH environment variable
(the job scripts export it), for example to read another person's checkpoints.
"""
import os

SCRATCH = os.environ.get(
    "UH_SCRATCH", f"/scratch/{os.environ.get('USER', 'unknown')}/unrewarded-hacker")
MODELS_DIR = f"{SCRATCH}/models"  # merged SFT models
RUNS_DIR = f"{SCRATCH}/rl"        # RL adapters, optimizer state, checkpoints
