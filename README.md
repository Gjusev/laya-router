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

**Option A — pip:**

```bash
pip install laya-router
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

> **First request is slow by design:** laya loads its decision checkpoints once (~10 s cold start on CPU; kept warm afterwards). Warm routing decisions measured on this project's benchmark run (AMD64 CPU, 179 prompts, [`backtest/bench_latency.py`](backtest/bench_latency.py)): p50 460 ms, p95 1.4 s, p99 2.7 s — free in API cost, not in latency; run the proxy next to your workload if you are latency-sensitive.

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
| `LAYA_ROUTER_MIN_CONFIDENCE` | `0.45` | Escalate below this confidence; `0` disables the gate (see the calibration sweep under Backtest) |
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
export OPENAI_API_KEY=sk-...        # OpenAI budget: ~5-10 USD for 300 prompts x 2 tiers
make backtest                       # dataset -> both-tier answers -> blind judge -> table
```

Cheaper: run the same pipeline on **Z.ai (GLM)** — this is how the published numbers below were produced:

```bash
export OPENAI_API_KEY=<your-z.ai-key>
make backtest-glm                   # same eval, tiers from backtest/tiers.glm.yaml
```

Any other OpenAI-compatible upstream works the same way: point `OPENAI_BASE_URL` at it and pass a matching `--tiers` file (or set `LAYA_ROUTER_TIERS_FILE`).

### Measured results (first published run)

Dataset: 80 MT-Bench questions + 100 synthetic trivial prompts (the seeded LMSYS-Chat-1M sample is still pending — TODO). Tiers: `glm-5.3-flash` (cheap) vs `glm-5.3` (frontier), both at `reasoning_effort=low`, judge `glm-5.3`. Raw evidence: [`backtest/dataset.jsonl`](backtest/dataset.jsonl), [`backtest/results.jsonl`](backtest/results.jsonl), [`backtest/judgements.jsonl`](backtest/judgements.jsonl).

| Metric | Value |
|---|---|
| Prompts (both tiers answered) | 180 |
| % routed to cheap | 80.6% |
| Cost saving vs always-frontier | 54.9% |
| Win/tie/lose of cheap vs frontier (cheap-routed, judged) | 28 / 87 / 30 |
| Routing precision (cheap verdict win/tie) | 79.3% |
| Over-escalations (frontier, costly only) | 35 |
| Routing cost per 1,000 requests | $0 (local laya) |

Confidence-gate calibration (simulated offline from recorded per-prompt confidences):

| min_confidence | % cheap | cost saving | misses | precision |
|---|---|---|---|---|
| 0.0 (off) | 80.6% | 54.9% | 30 | 79.3% |
| 0.45 (default) | ~72% | ~46% | ~27 | ~79% |
| 0.55 | 53.3% | 30.0% | 21 | 78.1% |
| 0.70 | 27.2% | 10.4% | 10 | 79.6% |

Two honest findings from this run:

- **Misses are dominated by judge noise, not routing error.** On the 100 trivial prompts (near-identical answers), the judge scored cheap 16 wins and 17 losses — a symmetric noise floor. Roughly half of the 30 recorded misses are likely noise, not real quality losses.
- **The confidence gate buys little precision.** Precision stays flat (~79%) across the whole threshold range: raising the gate spends savings (~2 points per miss avoided) without improving correctness. The default (0.45) sits in the flat zone; cost-sensitive operators can disable it (`0`) and quality-sensitive ones can raise it.

## Limitations

- Single-process by design: the rate limiter and metrics are in-memory (fine for one replica; a shared store would be needed for a fleet).
- The published backtest numbers come from one judge (`glm-5.3`) on one model pair (`glm-5.3-flash` vs `glm-5.3`); agreement with a second judge and results on other model pairs are not yet measured (TODO(measure)). The measured judge noise floor (~16% of trivial prompts scored non-tie) bounds the precision claims above.
- The laya classifier labeled 142/180 prompts "simple" and only 3 "standard" — the question set under-detects the middle band; tuning the custom questions is the next quality lever.
- The seeded LMSYS-Chat-1M sample (120 real user turns) is not yet in the dataset.
- Routing adds a one-time checkpoint load (~10 s) and a per-decision CPU cost (measured p50 460 ms / p99 2.7 s on AMD64 — reproducible via `make bench`); it pays for itself on the first avoided frontier call, not in added latency.

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
- [x] Published backtest numbers in the README (GLM pair; OpenAI-pair run pending)
- [x] PyPI release (`pip install laya-router`)

## License

Apache 2.0. See [LICENSE](LICENSE).
