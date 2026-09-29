"""FastAPI app exposing an OpenAI-compatible, routed chat completions endpoint.

Phase 1 (MVP): non-streaming only. The client's `model` field is ignored and
replaced by the routed tier's model; the routing decision is surfaced in
X-Laya-* response headers.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response, StreamingResponse

from laya_router.config import Settings, load_tiers
from laya_router.policy import RoutingDecision, apply_min_confidence, fast_path_tier
from laya_router.routing import LayaRoutingEngine, RoutingEngine


def prompt_text(messages: list[Dict[str, Any]]) -> str:
    """Flatten a chat request into the text the router classifies."""
    return "\n".join(
        str(message.get("content") or "")
        for message in messages
        if message.get("content") is not None
    )


def route_request(engine: RoutingEngine, prompt: str, min_confidence: float) -> RoutingDecision:
    """Fast path first (no model call); otherwise laya + confidence gate."""
    fast = fast_path_tier(prompt)
    if fast is not None:
        return RoutingDecision(
            tier=fast, complexity="fast-path", answer_confidence=1.0, reason="fast-path:trivial"
        )
    return apply_min_confidence(engine.decide(prompt), min_confidence)


def create_app(
    settings: Optional[Settings] = None,
    engine: Optional[RoutingEngine] = None,
) -> FastAPI:
    settings = settings or Settings()
    tiers = load_tiers(settings.tiers_file)
    engine = engine or LayaRoutingEngine()
    upstream = httpx.AsyncClient(
        base_url=settings.upstream_base_url,
        timeout=settings.upstream_timeout_s,
    )
    app = FastAPI(title="laya-router", version="0.1.0")

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
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

        decision = await run_in_threadpool(
            route_request, engine, prompt_text(body.get("messages", [])), settings.min_confidence
        )
        model = tiers.model_for(decision.tier)
        body["model"] = model

        headers = {
            "Authorization": (
                f"Bearer {settings.upstream_api_key}"
                if settings.upstream_api_key
                else request.headers.get("authorization", "")
            )
        }

        if body.get("stream"):
            upstream_request = upstream.build_request(
                "POST", "/chat/completions", json=body, headers=headers
            )
            try:
                upstream_response = await upstream.send(upstream_request, stream=True)
            except httpx.HTTPError as exc:
                return JSONResponse(
                    status_code=502,
                    content={"error": {"message": f"upstream request failed: {exc}", "type": "api_error"}},
                    headers=_laya_headers(decision, model),
                )
            # Errors arrive before any SSE byte is sent, so they can still be
            # passed through as a regular response with routing headers.
            if upstream_response.status_code >= 400:
                content = await upstream_response.aread()
                await upstream_response.aclose()
                return Response(
                    status_code=upstream_response.status_code,
                    content=content,
                    media_type=upstream_response.headers.get("content-type"),
                    headers=_laya_headers(decision, model),
                )
            return StreamingResponse(
                _relay(upstream_response),
                status_code=upstream_response.status_code,
                media_type=upstream_response.headers.get("content-type"),
                headers=_laya_headers(decision, model),
            )

        try:
            upstream_response = await upstream.post("/chat/completions", json=body, headers=headers)
        except httpx.HTTPError as exc:
            return JSONResponse(
                status_code=502,
                content={"error": {"message": f"upstream request failed: {exc}", "type": "api_error"}},
                headers=_laya_headers(decision, model),
            )

        # Pass the upstream body through byte-exact (it may not be JSON, e.g.
        # an HTML rate-limit page) while stamping our routing headers on it.
        return Response(
            status_code=upstream_response.status_code,
            content=upstream_response.content,
            media_type=upstream_response.headers.get("content-type"),
            headers=_laya_headers(decision, model),
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
