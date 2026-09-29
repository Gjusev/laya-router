# laya-router

> OpenAI-compatible proxy that routes every prompt to a cheap or a frontier model using a local System 1 decision model.

[![CI](https://github.com/Gjusev/laya-router/actions/workflows/ci.yml/badge.svg)](https://github.com/Gjusev/laya-router/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)

Point your OpenAI SDK `base_url` at the proxy and change **nothing else**. A local [laya](https://github.com/NandhaKishorM/laya) model decides, per prompt, whether it deserves the frontier model or the cheap one — every routing decision runs on your machine and costs $0 in API terms.

Built on [laya](https://github.com/NandhaKishorM/laya), the open-source System 1 decision engine (Apache 2.0).

## Contents

- [How it works](#how-it-works)
- [Quickstart](#quickstart)
- [Routing behavior](#routing-behavior)
- [API compatibility](#api-compatibility)
- [Configuration](#configuration)
- [Operations](#operations)
- [Backtest (reproducible)](#backtest-reproducible)
- [Limitations](#limitations)
- [Development](#development)
- [Roadmap](#roadmap)
- [License](#license)

## How it works

```
OpenAI SDK / curl / any client
        │  (base_url = http://127.0.0.1:8000/v1)
        ▼
┌─────────────────────── laya-router (FastAPI) ───────────────────────┐
│ 1. Fast path (regex, ~0 ms) ─────────────────────────────► cheap    │
│ 2. laya Router (local, one forward pass) → complexity + confidence  │
│ 3. Policy: complex OR low-confidence → frontier; else → cheap      │
│ 4. httpx → upstream (SSE passthrough when stream=true)             │
│ 5. Observability: X-Laya-* headers, /metrics, JSONL decision log   │
└─────────────────────────────────────────────────────────────────────┘
```

The client's `model` field is ignored — the router picks the model. Everything else in the request body (temperature, tools, `max_tokens`, …) is forwarded byte-exact.

## Quickstart

The proxy speaks the OpenAI API and forwards to any OpenAI-compatible upstream (default: `https://api.openai.com/v1`).

**Option A — pip** (PyPI release pending; install from git for now):

```bash
pip install git+https://github.com/Gjusev/laya-router.git
export LAYA_ROUTER_UPSTREAM_API_KEY=sk-...   # or forward client keys, see Configuration
laya-router                                  # serves http://127.0.0.1:8000/v1
```

**Option B — Docker:**

```bash
docker build -t laya-router .
docker run -p 8000:8000 -e LAYA_ROUTER_UPSTREAM_API_KEY=sk-... laya-router
```

**Option C — from source** (Python 3.10+, [uv](https://docs.astral.sh/uv/)):

```bash
git clone https://github.com/Gjusev/laya-router.git && cd laya-router
uv venv && uv pip install -e ".[dev]"
uv run laya-router
```

Then adopt it in two lines — the stock OpenAI client, only `base_url` changes:

```python
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="sk-...")
completion = client.chat.completions.create(
    model="ignored-by-proxy",
    messages=[{"role": "user", "content": "Say hi in three words"}],
)
print(completion.model, "->", completion.choices[0].message.content)
```

Or with curl:

```console
$ curl -s http://127.0.0.1:8000/v1/chat/completions \
    -H "Authorization: Bearer sk-..." -H "Content-Type: application/json" \
    -d '{"model":"ignored","messages":[{"role":"user","content":"Say hi"}]}' -i
HTTP/1.1 200 OK
x-laya-route: cheap
x-laya-model: gpt-4o-mini
x-laya-confidence: 0.8957
x-laya-reason: complexity=simple
content-type: application/json
...
```

More runnable examples: [`examples/quickstart.py`](examples/quickstart.py) and [`examples/streaming.py`](examples/streaming.py).

> **First request is slow by design:** laya downloads its decision checkpoints once (tens of seconds on first boot; kept warm afterwards). Subsequent routing decisions are sub-second on CPU. TODO(measure): publish measured per-decision latency on the benchmark hardware.

## Routing behavior

Three layers, cheapest first:

1. **Fast path** — greetings and other zero-content prompts match a regex and go straight to the cheap tier without invoking the model at all (`x-laya-reason: fast-path:trivial`).
2. **laya decision** — one local forward pass classifies the prompt (`simple` / `standard` / `complex`) with a calibrated confidence.
3. **Confidence gate** — if `answer_confidence` is below `LAYA_ROUTER_MIN_CONFIDENCE`, the request escalates to frontier (reason gains `+low-confidence`). Unknown complexity labels also escalate: spend more rather than risk quality.

Response headers on every request:

| Header | Meaning |
|---|---|
| `X-Laya-Route` | Tier chosen: `cheap` or `frontier` |
| `X-Laya-Model` | Upstream model actually used |
| `X-Laya-Confidence` | laya's calibrated confidence for the decision (1.0 on the fast path) |
| `X-Laya-Reason` | Decision trace: `complexity=…`, `+low-confidence`, or `fast-path:trivial` |

## API compatibility

| Surface | Status |
|---|---|
| `POST /v1/chat/completions` (non-streaming) | ✅ Full passthrough, only `model` swapped |
| `POST /v1/chat/completions` (`stream: true`) | ✅ SSE relayed as it arrives |
| Tool calls / JSON mode / other body fields | ⚙️ Forwarded untouched (passthrough should carry them; not yet covered by tests) |
| `GET /healthz`, `GET /metrics` | ✅ Operational endpoints (proxy-specific) |
| `/v1/embeddings`, `/v1/models`, other endpoints | ❌ Out of scope for v1 — see [Roadmap](#roadmap) |

Out of scope for v1 (by design): embeddings, formally supported tool-calls, multi-tenant key management, admin UI.

## Configuration

All settings come from `LAYA_ROUTER_*` environment variables (or a `.env` file):

| Variable | Default | Meaning |
|---|---|---|
| `LAYA_ROUTER_UPSTREAM_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible API (vLLM, Ollama, OpenRouter, …) |
| `LAYA_ROUTER_UPSTREAM_API_KEY` | unset | When unset, each client's `Authorization` header is forwarded as-is |
| `LAYA_ROUTER_TIERS_FILE` | packaged `tiers.yaml` | Which model to use per tier, and list prices for cost estimation |
| `LAYA_ROUTER_UPSTREAM_TIMEOUT_S` | `120` | Upstream request timeout |
| `LAYA_ROUTER_MIN_CONFIDENCE` | `0.55` | Escalate below this confidence; `0` disables the gate. TODO(tune via backtest cost/quality curve) |
| `LAYA_ROUTER_DECISION_LOG` | unset | Path for the JSONL decision log (one line per request) |
| `LAYA_ROUTER_RATE_LIMIT_RPM` | `0` (off) | Per-client-IP requests per minute |

Tiers (packaged default, fully editable):

```yaml
cheap:
  model: gpt-4o-mini
  price: {input_per_m: 0.15, output_per_m: 0.60}
frontier:
  model: gpt-4o
  price: {input_per_m: 2.50, output_per_m: 10.00}
```

## Operations

- **Liveness:** `GET /healthz` → `{"status": "ok"}`
- **Prometheus:** `GET /metrics` — `laya_router_requests_total{tier,status}` (including 400/429/503 degraded paths) and `laya_router_routing_seconds`
- **Decision log:** set `LAYA_ROUTER_DECISION_LOG` to record per-request JSONL: tier, model, complexity, confidence, reason, status, routing latency, and a truncated prompt preview
- **Rate limit:** `LAYA_ROUTER_RATE_LIMIT_RPM` returns OpenAI-shaped 429s with `Retry-After`

Degraded behavior is explicit: a failing routing engine yields a structured 503 (counted in metrics, logged), never a silent always-frontier fallback; upstream errors and non-JSON bodies pass through byte-exact with routing headers attached.

## Backtest (reproducible)

The honest eval answers every prompt with **both** tiers, so routing mistakes are measurable, then a blind judge (fixed rubric, temperature 0, seeded A/B shuffle) compares the cheap answer against the frontier one. Definitions are published with the numbers: the router is *correct* when it routed cheap and the judge says win/tie, a *miss* when cheap loses, and *over-escalation* when it spent frontier money on a simple prompt.

```bash
export OPENAI_API_KEY=sk-...        # budget: ~5-10 USD for 300 prompts x 2 tiers
make backtest                       # dataset -> both-tier answers -> blind judge -> table
```

Cheaper: run the same pipeline on **Z.ai (GLM)**, where the cheap tier (`glm-4.5-flash`) is free — the run only pays for frontier answers and judge calls:

```bash
export OPENAI_API_KEY=<your-z.ai-key>
make backtest-glm                   # same eval, tiers from backtest/tiers.glm.yaml
```

Any other OpenAI-compatible upstream works the same way: point `OPENAI_BASE_URL` at it and pass a matching `--tiers` file (or set `LAYA_ROUTER_TIERS_FILE`).

The `min_confidence` threshold should be calibrated on the resulting cost/quality curve — the same idea as calibrating a router threshold on your own traffic.

Results (TODO(measure): publish after the first full run):

| Metric | Value |
|---|---|
| Prompts (both tiers answered) | — |
| % routed to cheap | — |
| Cost saving vs always-frontier | — |
| Win/tie/lose of cheap vs frontier (judged) | — |
| Win-rate delta (router vs always-frontier) | — |
| Routing precision (cheap verdict win/tie) | — |
| Over-escalations (frontier, costly only) | — |
| Routing cost per 1,000 requests | $0 (local laya) |

## Limitations

- Single-process by design: the rate limiter and metrics are in-memory (fine for one replica; a shared store would be needed for a fleet).
- The judge is a single model with a fixed rubric; agreement with a second judge is not yet measured (TODO(measure)).
- The laya checkpoint reports uncalibrated confidence for some question types (a runtime warning surfaces this).
- Routing adds a one-time checkpoint download and a per-decision CPU cost (TODO(measure)); it pays for itself on the first avoided frontier call.
- Not on PyPI yet — install from git.

## Development

```bash
uv venv && uv pip install -e ".[dev]"
pytest            # unit + integration; fully offline, no checkpoints downloaded
pytest -m slow    # opt-in: real laya engine (downloads checkpoints on first use)
make backtest     # full eval pipeline (needs an OpenAI budget)
```

Project layout:

```
src/laya_router/
  server.py        # FastAPI app: endpoint, rate limit, streaming relay
  policy.py        # fast paths, tier choice, confidence gate, RoutingDecision
  routing.py       # laya engine wrapper + the routing question set
  config.py        # settings (pydantic-settings) + tiers.yaml loader
  observability.py # Prometheus metrics + JSONL decision log
backtest/          # dataset builder, both-tier runner, blind judge, analysis
examples/          # quickstart.py, streaming.py
tests/             # offline by default; @slow marks real-checkpoint tests
```

Contributions welcome — open an issue first for anything non-trivial, keep commits conventional (`feat:`, `fix:`, `test:`, `docs:`, `chore:`), and all code/docs in English.

## Roadmap

- [x] MVP: `POST /v1/chat/completions` (non-streaming) with laya-based tier routing
- [x] Streaming (SSE) passthrough
- [x] Confidence gating + deterministic fast paths
- [x] Observability: Prometheus `/metrics`, JSONL decision log, `/healthz`, Docker
- [x] Reproducible backtest harness (`make backtest`)
- [ ] Published backtest numbers in the README (needs an API budget)
- [ ] PyPI release

## License

Apache 2.0. See [LICENSE](LICENSE).
