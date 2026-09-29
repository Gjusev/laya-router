# laya-router

> OpenAI-compatible proxy that routes every prompt to a cheap or a frontier model using a local System 1 decision model.

Status: early development. Built on [laya](https://github.com/NandhaKishorM/laya),
the open-source System 1 decision engine (Apache 2.0).

## Why

- Routing is the biggest cost lever in production LLM apps. In the Jev ecosystem a comparable router measured -60% cost on a 237-turn backtest, and no standalone OpenAI-compatible router exists for the open-source stack yet.
- laya runs locally: each routing decision costs $0 and adds ~35 ms, so the router pays for itself on the first avoided frontier call.
- Adoption in two lines: point your OpenAI SDK `base_url` at the proxy and nothing else in your code changes.

## Roadmap

- [ ] MVP: `POST /v1/chat/completions` (non-streaming) with laya-based tier routing
- [ ] Streaming (SSE) passthrough
- [ ] Confidence gating: low `answer_confidence` escalates to the frontier tier; deterministic fast paths for trivial prompts
- [ ] Observability: Prometheus `/metrics`, decision log (JSONL), `X-Laya-*` response headers
- [ ] Reproducible backtest: cost/quality table over a public prompt set, published in the README

## Development setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/) (or any venv + pip):

```bash
uv venv
uv pip install -e ".[dev]"
pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
