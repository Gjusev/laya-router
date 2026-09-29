"""FastAPI app exposing an OpenAI-compatible, routed chat completions endpoint.

Phase 1 (MVP): non-streaming only. The client's `model` field is ignored and
replaced by the routed tier's model; the routing decision is surfaced in
X-Laya-* response headers.
"""

from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse

from laya_router.config import Settings, load_tiers
from laya_router.observability import (
    PROMETHEUS_CONTENT_TYPE,
    REQUESTS_TOTAL,
    ROUTING_SECONDS,
    DecisionLog,
    log_entry,
    metrics_payload,
)
from laya_router.policy import RoutingDecision, apply_min_confidence, fast_path_tier
from laya_router.routing import LayaRoutingEngine, RoutingEngine


def prompt_text(messages: list[Dict[str, Any]]) -> str:
    """Flatten a chat request into the text the router classifies.

    Multimodal content (a list of typed parts) contributes its text parts
    only; images and other part types are ignored for routing.
    """
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            parts.extend(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
    return "\n".join(parts)


def route_request(engine: RoutingEngine, prompt: str, min_confidence: float) -> RoutingDecision:
    """Fast path first (no model call); otherwise laya + confidence gate."""
    fast = fast_path_tier(prompt)
    if fast is not None:
        return RoutingDecision(
            tier=fast, complexity="fast-path", answer_confidence=1.0, reason="fast-path:trivial"
        )
    return apply_min_confidence(engine.decide(prompt), min_confidence)


class RateLimiter:
    """Fixed-window per-client-IP limit (requests per minute); 0 disables it.

    ponytail: single-process, in-memory, O(1) per request; move to a shared
    store only if the proxy is ever deployed as multiple replicas.
    """

    WINDOW_S = 60.0

    def __init__(self, per_minute: int):
        self._per_minute = per_minute
        self._hits: Dict[str, tuple] = {}  # ip -> (window_start, count)

    def allow(self, key: str, now: float) -> bool:
        if self._per_minute <= 0:
            return True
        start, count = self._hits.get(key, (now, 0))
        if now - start >= self.WINDOW_S:
            start, count = now, 0
        self._hits[key] = (start, count + 1)
        if len(self._hits) > 10_000:  # ponytail: crude cap; prune expired only
            self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self.WINDOW_S}
        return count + 1 <= self._per_minute

    def retry_after_s(self, key: str, now: float) -> int:
        start, _ = self._hits.get(key, (now, 0))
        return max(1, int(self.WINDOW_S - (now - start)))


def create_app(
    settings: Optional[Settings] = None,
    engine: Optional[RoutingEngine] = None,
) -> FastAPI:
    settings = settings or Settings()
    tiers = load_tiers(settings.tiers_file)
    engine = engine or LayaRoutingEngine()
    decision_log = DecisionLog(settings.decision_log) if settings.decision_log else None
    rate_limiter = RateLimiter(settings.rate_limit_rpm)
    upstream = httpx.AsyncClient(
        base_url=settings.upstream_base_url,
        timeout=settings.upstream_timeout_s,
    )
    app = FastAPI(title="laya-router", version="0.1.0")

    @app.get("/healthz")
    async def healthz() -> Response:
        return JSONResponse({"status": "ok"})

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(content=metrics_payload(), media_type=PROMETHEUS_CONTENT_TYPE)

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        if not rate_limiter.allow(client_ip, now):
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "message": "Rate limit exceeded; slow down or raise LAYA_ROUTER_RATE_LIMIT_RPM.",
                        "type": "rate_limit_error",
                    }
                },
                headers={"Retry-After": str(rate_limiter.retry_after_s(client_ip, now))},
            )

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return JSONResponse(
                status_code=400,
                content={"error": {"message": "request body is not valid JSON", "type": "invalid_request_error"}},
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=400,
                content={"error": {"message": "request body must be a JSON object", "type": "invalid_request_error"}},
            )

        prompt = prompt_text(body.get("messages", []))
        started = time.perf_counter()
        decision = await run_in_threadpool(
            route_request, engine, prompt, settings.min_confidence
        )
        routing_seconds = time.perf_counter() - started
        ROUTING_SECONDS.observe(routing_seconds)
        model = tiers.model_for(decision.tier)
        body["model"] = model

        headers = {
            "Authorization": (
                f"Bearer {settings.upstream_api_key}"
                if settings.upstream_api_key
                else request.headers.get("authorization", "")
            )
        }

        def finish(response: Response, status: int) -> Response:
            REQUESTS_TOTAL.labels(tier=decision.tier, status=str(status)).inc()
            if decision_log is not None:
                decision_log.write(
                    log_entry(
                        tier=decision.tier,
                        model=model,
                        complexity=decision.complexity,
                        answer_confidence=decision.answer_confidence,
                        reason=decision.reason,
                        status=status,
                        routing_seconds=routing_seconds,
                        prompt=prompt,
                    )
                )
            return response

        if body.get("stream"):
            upstream_request = upstream.build_request(
                "POST", "/chat/completions", json=body, headers=headers
            )
            try:
                upstream_response = await upstream.send(upstream_request, stream=True)
            except httpx.HTTPError as exc:
                return finish(
                    JSONResponse(
                        status_code=502,
                        content={"error": {"message": f"upstream request failed: {exc}", "type": "api_error"}},
                        headers=_laya_headers(decision, model),
                    ),
                    502,
                )
            # Errors arrive before any SSE byte is sent, so they can still be
            # passed through as a regular response with routing headers.
            if upstream_response.status_code >= 400:
                content = await upstream_response.aread()
                await upstream_response.aclose()
                return finish(
                    Response(
                        status_code=upstream_response.status_code,
                        content=content,
                        media_type=upstream_response.headers.get("content-type"),
                        headers=_laya_headers(decision, model),
                    ),
                    upstream_response.status_code,
                )
            return finish(
                StreamingResponse(
                    _relay(upstream_response),
                    status_code=upstream_response.status_code,
                    media_type=upstream_response.headers.get("content-type"),
                    headers=_laya_headers(decision, model),
                ),
                upstream_response.status_code,
            )

        try:
            upstream_response = await upstream.post("/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            return finish(
                JSONResponse(
                    status_code=502,
                    content={"error": {"message": f"upstream request failed: {exc}", "type": "api_error"}},
                    headers=_laya_headers(decision, model),
                ),
                502,
            )

        # Pass the upstream body through byte-exact (it may not be JSON, e.g.
        # an HTML rate-limit page) while stamping our routing headers on it.
        return finish(
            Response(
                status_code=upstream_response.status_code,
                content=upstream_response.content,
                media_type=upstream_response.headers.get("content-type"),
                headers=_laya_headers(decision, model),
            ),
            upstream_response.status_code,
        )

    return app


async def _relay(upstream_response: httpx.Response):
    """Yield upstream SSE bytes as they arrive; always close the stream.

    If the client disconnects mid-stream, starlette cancels this generator and
    the finally block releases the upstream connection (no leaks).
    """
    try:
        async for chunk in upstream_response.aiter_bytes():
            yield chunk
    finally:
        await upstream_response.aclose()


def _laya_headers(decision, model: str) -> Dict[str, str]:
    return {
        "X-Laya-Route": decision.tier,
        "X-Laya-Model": model,
        "X-Laya-Confidence": str(decision.answer_confidence),
        "X-Laya-Reason": decision.reason,
    }


def main() -> None:
    """Console-script entry point (`laya-router`)."""
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)
