# Related work notes (read 2026-11-16)

Pages were read through a fetch tool that truncates long pages; items marked (S) come from a
machine summary of the unread tail or from figures I could not read, and must be checked against the
source or code before we rely on them.

## The question itself
- **Owain Evans, "Three half-baked research ideas"** (LessWrong, 8 Nov 2026).
  https://www.lesswrong.com/posts/vAniKbagqhyzpha6r/three-half-baked-research-ideas
  Idea 1 is our question. He suggests small-scale RL could give a *positive* result, math envs are easiest
  to make unhackable, and small experiments cannot establish the negative. Comments: jacob_drori proposes
  clean envs that (1) teach capabilities useful for cheating, (2) reward persistence on hard checkable
  tasks, (3) reward approved shortcuts, (4) reward reasoning about the grader; Evans endorses 1 and 2.
  Davidmanheim: hard to separate reward hacking from plain misgeneralization without reasoning evidence.
  J Bostock: clean-only training withholds the information that defines the allowed/disallowed boundary.

## Closest precedents
- **Azarbal, Gillioz, Turner, "Training a Reward Hacker Despite Perfect Labels"** (LessWrong, Aug 2025).
  https://www.lesswrong.com/posts/dbYEoG7jNZbeWX39o
  GPT-4o-mini, coding problems with one wrong test. Samples generated under a hack-encouraging system
  prompt, all hacks filtered out, trained with the prompt removed ("re-contextualization"): hack rate rises.
  Training with the prompt kept does not. Effect flips sign on models that start high (GPT-4.1).
  Differences from us: SFT, and the training prompts themselves are hackable.
  Data: github.com/arianaazarbal/training-a-reward-hacker-despite-perfect-labels-data
- **Ward, Hu et al., "Gradient Routing Localizes and Removes Unintended Behaviors in RL" (GRAFT)**
  arXiv 2610.17062; blog https://alignment.anthropic.com/2026/graft/ ; code github.com/jnward/GRAFT (MIT).
  Qwen3-8B, GRPO, Countdown-Code target env + clean LeetCode anchor env. The **anchor-only** ablation
  (RL only on the clean anchor) is nearly our experiment: paper text says it "does not teach hacking".
  (S) LeetCode-Hackable hack rate ~8.8% anchor-only vs 11.5% base; HumanEval ~0.7% vs 1.4%.
  Caveats: init was SFT-primed on data with hacks (4.7% base hack rate); no pressure prompt; Countdown hack
  rate for that arm not found. Stack: TRL 0.29 GRPO overrides + vLLM 0.17; grader depends on
  github.com/ariahw/rl-rewardhacking. (S) 200 steps, group 16, LR 1.67e-4, no KL, 2-4 h on one H200.

## Environment
- **Khalifa et al., "Countdown-Code"** (arXiv 2603.07084, EMNLP 2026). Code: github.com/zohaib-khan5040/Countdown-Code
  Two-file harness, proxy = model's own test passes, true = expression correct. Hack types: overwrite
  `verify_solution`; relax target/numbers. Eight models (Llama-3.2-3B, Llama-3.1-8B, Qwen2.5-3B/7B,
  Qwen2.5-Coder-3B/7B, Qwen3-4B/8B). Under RL alone only Qwen2.5-3B-Instruct and Qwen2.5-Coder-7B learned
  to hack; 1% hack contamination in SFT data is enough for the rest. GRPO via verl, 8 rollouts/prompt,
  LoRA r128, 4000 train problems, 2xA40, <60 h. Hacking transfers to HumanEval (0.04 -> 0.41, LLM-judged).
  Clean-SFT + hackable RL: hacking stays near zero. No clean-RL-then-hackable-eval control.
  Pre-training per-model hack rates: not found in text (figures).
- **Zhong, Raghunathan, Carlini, "ImpossibleBench"** (arXiv 2510.20270). github.com/safety-research/impossiblebench
  Mutated tests contradict the spec, so pass rate = cheat rate. LiveCodeBench split: 103 tasks x 2 mutation
  types, <=10 submission turns, no tools. Prompt strictness moves GPT-5 from ~92% to 1%. No small models.

## Hacking that was rewarded (for method and context)
- **UK AISI, "(Some) Natural Emergent Misalignment from Reward Hacking in Non-Production RL"** (Mar 2026).
  https://www.alignmentforum.org/posts/2ANCyejqxfqK2obEj ; code github.com/UKGovernmentBEIS/reward-hacking-misalignment
  Olmo-3 7B/32B, GPT-OSS 20B/120B, CodeContests via inspect, TRL-based GRPO/DAPO with LoRA. Has a no-hack
  RL control but reports it only on misalignment evals. Models told not to use hinted hacks learn them anyway.
- **Yudelson, Ivanov, Greenblatt, "Reward Hacking Without Egregious Misalignment in an RL-Only Setting"**
  (LessWrong, Jun 2026). https://www.lesswrong.com/posts/fkv5W79rBtAiXqYcK
  Kimi K2.5, GPT-OSS-120b explore into hacks easily; hacking generalizes to held-out evals. No clean control.
- **Anthropic, "Training a Misaligned Reward Seeker"** (Aug 2026). https://alignment.anthropic.com/2026/reward-seeker/
  80 hackable envs; impossible-task hack rate 37% -> 97%; anti-hack prompts cut it sharply. No clean control.
- **MacDiarmid et al., "Natural emergent misalignment from reward hacking in production RL"** (arXiv 2511.18397).
- **Fischl-Lanzoni et al., "Breaking Bad"** (arXiv 2611.14996). No training. A "task going badly" direction
  rises with accumulated failures before a hack in Qwen3.6-27B / GPT-OSS-20B / Gemma-4-31B. Relevant
  mechanism: failure pressure, not instruction, precedes hacks. Supports using hard and impossible tasks.
- **Taylor et al., "School of Reward Hacks"** (arXiv 2508.17511). SFT on harmless hacks generalizes.

## What this implies for our design
1. The plain version (clean RL, neutral prompt) already has one weak null (GRAFT anchor-only). Lead with pressure.
2. The one positive with perfect labels relies on a train/eval prompt difference. Always evaluate under
   several prompts, including one the model never trained with.
3. Use impossible instances for the headline metric so capability gains cannot masquerade as honesty.
4. Sign can flip for models with high base rates; screen baselines before training.
5. A deterministic detector exists for Countdown-Code; avoid LLM judges for the primary metric.
