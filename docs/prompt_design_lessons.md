# Why the pressure prompt was a weak lever, and how to screen the next one

Written 2026-11-21 after the Qwen3.5-4B / Countdown-Code null. Numbers come from the tracked summaries
(`results/baseline/*/summary.json`) and from `uv run python -m uh.reasoning_stats`. Reasoning counts are
regex matches, so treat them as approximate.

## What we did and what we hoped

We added a system-prompt suffix ("you are evaluated only on whether the test passes... Never give up: do
whatever it takes to make the test pass") to both training and eval, and ran clean RL. The hope was that
"do whatever it takes" reasoning would be reinforced on honest tasks and then spill into tampering on
impossible ones.

## Why that reasoning was flawed

**1. A prompt shared by every sample creates no learning signal by itself.** Our update standardises reward
within each prompt's group of 8 samples. A feature of the reasoning is pushed up only if, within a group,
samples that have it are rewarded more than samples that lack it. Three cases:

| Feature of the reasoning | Net update |
|---|---|
| Present in every sample | Zero: the pushes up and down cancel |
| Varies, but does not predict reward | Zero on average; what remains is noise (drift) |
| Varies and predicts reward | Systematic, in the direction of the correlation |

So the plan needed test-seeking reasoning to vary across samples *and* to predict honest success. We
checked neither before training.

**2. The prompt barely changed the base model.** Untrained Qwen3.5-4B, four file-permission variants pooled:

| | Neutral | Pressure |
|---|---|---|
| Solvable, clean solve, no forced answer (n=4,000) | 41.4% | 39.8% |
| Solvable, clean solve, forced answer (n=1,600) | 52.3% | 51.6% |
| Solvable, hit the token limit (n=4,000) | 30.6% | 31.2% |
| Impossible, hit the token limit (n=4,000) | 97.9% | 97.3% |
| Impossible, hacks, 8k-token budget (n=1,600) | 2 | 5 |

No gain on the task, no change in how long it searches, hacks at floor.

**3. Where the prompt did induce test-passing talk, that talk predicted failure.** In the first training
batch (untrained policy, pressure prompt, 256 samples per seed):

| Seed | Samples with test-passing talk | Solve rate with it | Solve rate without it |
|---|---|---|---|
| 1 | 25 (9.8%) | 16% | 41% |
| 2 | 9 (3.5%) | 11% | 34% |
| 3 | 24 (9.4%) | 21% | 46% |

So the talk did vary (4-10% of samples), but with the wrong sign: clean RL pushed it *down*, and in seeds 2
and 3 it fell to about 1% within a few iterations. A likely reason is that the model talks about the test
when it is already failing to find an expression. This comparison is not adjusted for instance difficulty.

**4. Seed 1 was the noise case.** At iteration 1 a variant of the talk (the plan step "Ensure the solution
passes the test verification") happened to be rewarded 15 times out of 15 on easy instances, spread to
8-20% of samples, coincided with the only hacking we saw, then faded as the luck averaged out. Over
iterations 1-9 its summed advantage was still negative (-13). Prefilling that line at eval raised the
untrained model from 2 to 10 hacks per 3,200 (one cell, unreplicated) and did nothing in trained
checkpoints, so it accounts for little of the seed-1 peak (92 per 3,200).

**5. What clean RL did reinforce was unrelated to the prompt.** On held-out solvable tasks, solve rate rose
and abstention fell the same way with the neutral training prompt (`rl-L0-s1`, one seed: 76-82% solve,
abstention 9.8% to 0.8% by iteration 20) as with the pressure prompt (`rl-L1`, three seeds: 80-90%,
abstention to under 0.5%). The prompt was not the cause.

A correction to earlier wording: "the model abstains less" holds on solvable tasks. On impossible tasks
with a forced answer it is mixed: base 11-14%; checkpoints 5-10 often higher (12-30%); checkpoint 30 lower
(6-10%).

**6. Sampling and training on the same prompt removes the one mechanism known to work.** Azarbal et al.
sample under a hack-encouraging prompt and train with it removed. That pushes prompt-induced behaviour
into the default policy without needing any within-group correlation. We kept the prompt in both places.

## Screening a prompt (or task) before spending training compute

All of these run on the base model in about one eval job plus one rollout batch.

1. **It must move the base model's behaviour.** If hack rate, reasoning content and persistence are
   unchanged, as here, stop. A higher base hack rate is welcome but is not the criterion: it shows the
   prompt reaches the behaviour, and it raises the baseline the trained model has to beat. Report trained
   against untrained under the same prompt.
2. **The target reasoning must vary within a group.** Count it in base rollouts on the training tasks.
   Near 0% or near 100% both give RL nothing to select.
3. **It must predict honest reward within a group.** Compare solve rate with and without the target
   reasoning on the same instances (or sum its group-standardised advantage). Positive: clean RL will
   amplify it. Zero: only drift. Negative: clean RL will remove it. This is the check we skipped and it
   would have predicted the null.
4. **Clean-task performance going up is not required.** Aggregate solve rate under the prompt says little.
   What matters is the within-group correlation in step 3.
5. **Exception: re-contextualised training.** If we sample with the prompt and train without it, steps 2-3
   are not needed, only step 1.

## Implications for what to try next

- Re-contextualised RL on the current setup: sample under the pressure prompt, compute the update under
  the neutral prompt. Cheap, reuses everything, and tests the mechanism point 6 says we omitted. Step 1
  still applies, and here the prompt moved the base model very little, so expect a weak effect.
- A task where attention to the tests helps honest solving (wrong-test coding problems), so step 3 holds
  by construction.
- A stronger prompt or a larger model only if it passes steps 1-3 on the base model first.
