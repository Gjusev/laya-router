# laya-router

> OpenAI-compatible proxy that routes every prompt to a cheap or a frontier model using a local System 1 decision model.

Status: early development. Built on [laya](https://github.com/NandhaKishorM/laya),
the open-source System 1 decision engine (Apache 2.0).

## Why

- Routing is the biggest cost lever in production LLM apps. In the Jev ecosystem a comparable router measured -60% cost on a 237-turn backtest, and no standalone OpenAI-compatible router exists for the open-source stack yet.
- laya runs locally: each routing decision costs $0 in API terms and adds TODO(measure) ms of latency on our benchmark hardware (the laya project reports ~35 ms on GPU and hundreds of ms on CPU), so the router pays for itself on the first avoided frontier call.
- Adoption in two lines: point your OpenAI SDK `base_url` at the proxy and nothing else in your code changes.

## Quickstart

Run the proxy (routes with a local laya model; CPU is fine):

```bash
pip install laya-router
laya-router   # serves http://127.0.0.1:8000/v1
```

Then adopt it in two lines — point your OpenAI SDK `base_url` at the proxy and change nothing else. The `model` you ask for is ignored; the router picks the tier:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="your-upstream-key")
completion = client.chat.completions.create(
    model="ignored-by-proxy",
    messages=[{"role": "user", "content": "Say hi in three words"}],
)
```

Every response carries `X-Laya-Route` (`cheap`/`frontier`), `X-Laya-Model`, `X-Laya-Confidence` and `X-Laya-Reason` headers recording the routing decision. Streaming (`stream: true`) is relayed as SSE with the same headers.

Trivial prompts (greetings and the like) take a deterministic fast path to the cheap tier without invoking the model at all; when the decision model is unsure (`answer_confidence` below `LAYA_ROUTER_MIN_CONFIDENCE`) the request escalates to the frontier tier.

## Operations

- `GET /healthz` — liveness probe
- `GET /metrics` — Prometheus counters and histograms (`laya_router_requests_total{tier,status}`, `laya_router_routing_seconds`)
- JSONL decision log — set `LAYA_ROUTER_DECISION_LOG=/path/decisions.jsonl` to record one line per routed request
- Rate limit — set `LAYA_ROUTER_RATE_LIMIT_RPM=<n>` (0 = disabled) for a per-client-IP fixed window

Tier models and list prices are configured in [`src/laya_router/tiers.yaml`](src/laya_router/tiers.yaml); the upstream (any OpenAI-compatible API) and other knobs are configured via `LAYA_ROUTER_*` environment variables (`LAYA_ROUTER_UPSTREAM_BASE_URL`, `LAYA_ROUTER_UPSTREAM_API_KEY`, `LAYA_ROUTER_TIERS_FILE`, `LAYA_ROUTER_UPSTREAM_TIMEOUT_S`, `LAYA_ROUTER_MIN_CONFIDENCE`, `LAYA_ROUTER_DECISION_LOG`, `LAYA_ROUTER_RATE_LIMIT_RPM`).

Docker:

```bash
docker build -t laya-router .
docker run -p 8000:8000 -e LAYA_ROUTER_UPSTREAM_API_KEY=sk-... laya-router
```

## Roadmap

- [x] MVP: `POST /v1/chat/completions` (non-streaming) with laya-based tier routing
- [x] Streaming (SSE) passthrough
- [x] Confidence gating: low `answer_confidence` escalates to the frontier tier; deterministic fast paths for trivial prompts
- [x] Observability: Prometheus `/metrics`, decision log (JSONL)
- [ ] Reproducible backtest: cost/quality table over a public prompt set, published in the README

## Development setup

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/) (or any venv + pip):

```bash
uv venv
uv pip install -e ".[dev]"
pytest            # unit + integration tests; no checkpoints downloaded, no network
pytest -m slow    # opt-in: real laya engine (downloads checkpoints on first use)
```

## License

Apache 2.0. See [LICENSE](LICENSE).
