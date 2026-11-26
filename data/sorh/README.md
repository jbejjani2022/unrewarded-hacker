# School of Reward Hacks: frozen eval subset

`eval.jsonl`: 182 prompts from Taylor et al., "School of Reward Hacks" (arXiv 2508.17511), dataset
`longtermrisk/school-of-reward-hacks` on Hugging Face, licence CC BY 4.0. Frozen 2026-11-26: every
task type except "write a function" (coding, the family this project trains on), up to 6 prompts per type (fewer where a type has fewer usable rows)
drawn with `random.Random(0)` from rows that have both a hacking and an honest reference response.
`id` is `sorh-<row index in the source CSV>`. Never regenerate; evals depend on this exact set.
