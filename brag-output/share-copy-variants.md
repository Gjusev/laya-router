# Share copy variants

## X / Twitter

Cut 54.9% off my LLM bill. A local model decides, per prompt, cheap or frontier. Blind judge says quality tied. Two lines to adopt: pip install laya-router

## LinkedIn

My LLM bill had a boring problem: most prompts never needed the frontier model, but every prompt paid for it.

So I built laya-router, an OpenAI-compatible proxy that decides per prompt. A local decision model (laya, one forward pass on CPU) classifies each request. Trivial stuff takes a regex fast path. Anything complex or low-confidence escalates. Everything else goes to the cheap tier, and the response tells you what it picked in the X-Laya headers.

I backtested it honestly: 180 prompts, both tiers answered every time, a blind judge (fixed rubric, temperature 0, seeded A/B shuffle) compared the answers. Result: 80.6% of prompts routed cheap, 54.9% cheaper than always-frontier, quality tied on 79% of the cheap-routed answers. The raw dataset, answers and verdicts are in the repo, and the whole eval reruns with one command against any OpenAI-compatible provider.

Routing decisions cost $0 because they run on my machine. They do take ~460 ms of CPU (measured, reproducible), so this trades a little latency for the savings.

pip install laya-router, point your OpenAI base_url at it. That is the whole integration.

Repo in the comments.

## dev.to (opening)

My LLM bill dropped 54.9% and the quality didn't move. Not because of a clever prompt, because 80% of my prompts never needed the expensive model in the first place. Here's the router I built to make that decision per request, and the honest backtest behind the number.
