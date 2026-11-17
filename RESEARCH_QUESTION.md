It's known that training models in broken RL environments causes reward hacking. For example:
- environments where the task is impossible incentivizes cheating (since that's the only way to pass)
- environments where the task can be (more easily) accomplished via some shortcut / unintended route that isn't the "honest" route the developer intended. e.g. maybe the model was given write access to the evaluation scripts, by mistake.

Our question is: Even if we make all training envs clean / “perfect” (hacking is never rewarded in post-training), could a model still learn to reward hack (e.g. might it still hack when encountering a "broken" / hackable environment, as it's bound to do if deployed)?
It's inspired from this post, which you can check out: https://www.lesswrong.com/posts/vAniKbagqhyzpha6r/three-half-baked-research-ideas

My hypothesis is: Yeah. Sufficiently smart AI learns a general policy of “accomplish this task however I can.” If cheating is not a viable strategy in training, it’ll accomplish tasks honestly. But if in deployment it turns out that there’s a (easier) way of doing a task by cheating, the policy will generalize to taking that opportunity.

Our goal is to try as hard as possible to show a positive result, an example of "reward hacking without rewarded hacking." I.e., to create a model organism of this, an "existence proof" under certain assumptions and setup.

Some challenges
- a "clean" / "perfect" training env may be hard to define unambiguously and is a matter of degree. response: we can pick tasks / envs where what hacking means is unambiguous. These may not be the most interesting tasks / the ones we care about the most in deployment, but they're the natural first thing to try for a model organism and would be an important first step to show it could happen in the simple case.

An idea
- to start, we can make things super contrived / apply pressures to try to get the target behavior (learn hacking without rewarding it explicitly). if it fails even for these things, that's a signal something's wrong with our setup / code / infra, or that actually getting a model organism of this is really hard. for example something that might be worth trying is including some system prompt or instruction that encourages high persistence or completing the task at all costs / whatever it takes or something like that, but training in perfect envs where the model never "needs" to cheat and is never rewarded for doing so. but then, maybe in held out eval tasks where cheating is necessary to pass the test, the model's cheating rate has increased because of a certain general reasoning pattern it's internalized (would be important to eval with and without the persistence prompt used in training, to see how much of a trigger it is).
- I think we'd also want to do some kind of non-training baseline. like, see performance with and without the persistence prompt, on both the perfect 'training' envs and the held-out hackable envs. we'd then be able to see the effect of training.

What success would look like
- for at least a couple smallish models, for some task(s) (one for now okay but a couple would be good) where hacking is unambigously defined, first we'd want to see their baseline performance on clean vs. hackable versions of the task. If the hacking rate is really high already on the hackable versions, this might not be a good task, or it might not be the right model for this (e.g. the model might already be too much of a hacker, for this task, to show any interesting effect)
- we would then want to see, after RL on the clean task set, 1) an increase in performance on the clean set, as a sanity check that training worked (unless it was already really saturated before training? but then it that case maybe we should consider a different task or model?) 2) an increase in performance on the hackable tasks (which are only solvable by cheating, meaning the model generalized to being a reward hacker)
- it's likely that this won't just work 'out of the box' - i.e. some sort of contrived prompt or setup or conditioning might be necessary to get this to happen (See "An idea"). like a prompt encouraging persistence, or raising stakes. or information in context where the model learns about how a clean task *might* have been hackable, but too bad for now. in this case it'd be important to run with and without the contrived additions / pressures to see their effect.

Key decisions to figure out by doing good research / review on best practices and precedents in related model organism and reward hacking research:
- which model(s) to start with?
- which task(s)?
- which training and eval pipeline(s) and methodology? RL can be finnicky, we'd need to be very careful and do it right. Is there some SFT baseline that would make sense here, maybe as an even more contrived thing to try first?

You could look at recent papers like https://arxiv.org/pdf/2611.14996 that study model hacking / cheating in some way to get a sense of what the best tasks / envs / evals are for these behaviors. Don't just look at that paper, that was just an example of something that came out recently that may be relevant.

Carefully make a plan for tackling this question and maximizing our chances of success / getting the most signal out of as few experiments. I.e. a "fail fast" approach that narrows our search space and increases our info as much as possible. Once we review proposed steps together, you can then go and execute the plan. Track all experiments, decisions, and results along the way, following best research and communication practices, so we can refer later to what we did and why and what we found. Note that we can use the killarney cluster - see the claude.md, and add one to this project based on the template. you can make a public github repo and push to my account, and do any syncing to a copy on the cluster, so we can run things on the cluster.
