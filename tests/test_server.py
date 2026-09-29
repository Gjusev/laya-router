"""Seam: the proxy HTTP endpoint (fake engine, mocked upstream).

Uses the same request/response contract as the OpenAI API: requests in,
OpenAI-shaped responses out, plus X-Laya-* headers recording the routing.
"""

import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from laya_router.config import Settings
from laya_router.server import create_app

from conftest import TEST_UPSTREAM

# Scoped to the mock upstream so respx never intercepts unrelated traffic.
mock_upstream = respx.mock(base_url=TEST_UPSTREAM)


def make_client(fake_engine) -> TestClient:
    settings = Settings(_env_file=None, upstream_base_url=TEST_UPSTREAM)
    return TestClient(create_app(settings=settings, engine=fake_engine))


def upstream_ok(request: httpx.Request) -> httpx.Response:
    """Mock upstream: echo the model it was called with in an OpenAI-shaped body."""
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "model": body["model"],
            "choices": [
                {"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "mocked"}}
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


@mock_upstream
def test_get_on_completions_is_method_not_allowed(fake_engine):
    assert make_client(fake_engine).get("/v1/chat/completions").status_code == 405


@mock_upstream
def test_simple_prompt_routes_cheap_and_swaps_model(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "client-picked-model", "messages": [{"role": "user", "content": "hello"}]},
        headers={"Authorization": "Bearer client-key"},
    )

    assert response.status_code == 200
    assert response.headers["X-Laya-Route"] == "cheap"
    assert response.headers["X-Laya-Model"] == "gpt-4o-mini"
    assert response.json()["model"] == "gpt-4o-mini"  # model swapped, not the client's
    assert response.json()["choices"][0]["message"]["content"] == "mocked"


@mock_upstream
def test_complex_prompt_routes_frontier(fake_engine):
    route = mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "anything",
            "messages": [{"role": "user", "content": "COMPLEXPLEASE prove fermat's last theorem"}],
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Laya-Route"] == "frontier"
    assert response.headers["X-Laya-Model"] == "gpt-4o"
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "gpt-4o"


@mock_upstream
def test_upstream_receives_full_body_with_only_model_swapped(fake_engine):
    route = mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    client.post(
        "/v1/chat/completions",
        json={
            "model": "client-picked-model",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.2,
            "max_tokens": 128,
            "user": "u-123",
        },
    )

    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "gpt-4o-mini"
    assert sent["temperature"] == 0.2
    assert sent["max_tokens"] == 128
    assert sent["user"] == "u-123"
    assert sent["messages"] == [{"role": "user", "content": "hello"}]


@mock_upstream
def test_unreachable_upstream_returns_502_with_laya_headers(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=httpx.ConnectError("boom"))
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 502
    assert "upstream request failed" in response.json()["error"]["message"]
    assert response.headers["X-Laya-Route"] == "cheap"


@mock_upstream
def test_client_authorization_is_forwarded(fake_engine):
    route = mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer client-key"},
    )

    assert route.calls.last.request.headers["Authorization"] == "Bearer client-key"


@mock_upstream
def test_configured_upstream_api_key_overrides_forwarded_auth(fake_engine):
    route = mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    settings = Settings(
        _env_file=None, upstream_base_url=TEST_UPSTREAM, upstream_api_key="proxy-key"
    )
    client = TestClient(create_app(settings=settings, engine=fake_engine))

    client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
        headers={"Authorization": "Bearer client-key"},
    )

    assert route.calls.last.request.headers["Authorization"] == "Bearer proxy-key"


def make_client_with(fake_engine, **settings_overrides) -> TestClient:
    settings = Settings(
        _env_file=None, upstream_base_url=TEST_UPSTREAM, **settings_overrides
    )
    return TestClient(create_app(settings=settings, engine=fake_engine))


@mock_upstream
def test_confidence_and_reason_headers_present(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "please summarize this text"}]},
    )

    assert response.headers["X-Laya-Confidence"] == "0.9"
    assert response.headers["X-Laya-Reason"] == "complexity=simple"


@mock_upstream
def test_fast_path_skips_the_engine_entirely(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert fake_engine.prompts == []
    assert response.headers["X-Laya-Route"] == "cheap"
    assert response.headers["X-Laya-Reason"] == "fast-path:trivial"
    assert response.headers["X-Laya-Confidence"] == "1.0"


@mock_upstream
def test_low_confidence_escalates_to_frontier(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    # MEDIUMPLEASE -> standard label with 0.7 confidence; gate at 0.75 must escalate.
    client = make_client_with(fake_engine, min_confidence=0.75)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "MEDIUMPLEASE summarize this"}]},
    )

    assert response.headers["X-Laya-Route"] == "frontier"
    assert response.headers["X-Laya-Reason"] == "complexity=standard+low-confidence"


async def sse_stream():
    """Upstream SSE body as an async generator (keeps chunk boundaries)."""
    for chunk in (
        b'data: {"id":"c1","object":"chat.completion.chunk","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n',
        b'data: {"id":"c1","object":"chat.completion.chunk","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":"hel"},"finish_reason":null}]}\n\n',
        b"data: [DONE]\n\n",
    ):
        yield chunk


def sse_upstream_response() -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/event-stream"}, content=sse_stream()
    )


@mock_upstream
def test_streaming_request_relays_sse_chunks(fake_engine):
    route = mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        return_value=sse_upstream_response()
    )
    client = make_client(fake_engine)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["X-Laya-Route"] == "cheap"
        chunks = list(response.iter_bytes())

    # The proxy relays bytes as they arrive; the test transport may coalesce
    # chunks, so assert the byte stream is complete and in order.
    assert b"".join(chunks) == (
        b'data: {"id":"c1","object":"chat.completion.chunk","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}\n\n'
        b'data: {"id":"c1","object":"chat.completion.chunk","model":"gpt-4o-mini","choices":[{"index":0,"delta":{"content":"hel"},"finish_reason":null}]}\n\n'
        b"data: [DONE]\n\n"
    )
    sent = json.loads(route.calls.last.request.content)
    assert sent["stream"] is True
    assert sent["model"] == "gpt-4o-mini"


@mock_upstream
def test_streaming_complex_prompt_uses_frontier(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        return_value=sse_upstream_response()
    )
    client = make_client(fake_engine)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "m",
            "stream": True,
            "messages": [{"role": "user", "content": "COMPLEXPLEASE hard math"}],
        },
    ) as response:
        assert response.headers["X-Laya-Route"] == "frontier"
        assert response.status_code == 200


@mock_upstream
def test_streaming_upstream_error_before_stream_passes_through(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "upstream blew up"}})
    )
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 500
    assert response.json()["error"]["message"] == "upstream blew up"
    assert response.headers["X-Laya-Route"] == "cheap"


@mock_upstream
def test_streaming_unreachable_upstream_returns_502(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        side_effect=httpx.ConnectError("boom")
    )
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "stream": True, "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 502
    assert response.headers["X-Laya-Route"] == "cheap"


@mock_upstream
def test_upstream_error_is_passed_through(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        return_value=httpx.Response(500, json={"error": {"message": "upstream blew up"}})
    )
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 500
    assert response.json()["error"]["message"] == "upstream blew up"


@mock_upstream
def test_non_json_upstream_body_is_passed_through(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        return_value=httpx.Response(
            429, content=b"<html>rate limited</html>", headers={"content-type": "text/html"}
        )
    )
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 429
    assert response.text == "<html>rate limited</html>"
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["X-Laya-Route"] == "cheap"


def test_malformed_request_body_returns_400(fake_engine):
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        content=b"this is not json",
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 400


@mock_upstream
def test_full_conversation_is_used_as_routing_prompt(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    client.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [
                {"role": "system", "content": "You are terse."},
                {"role": "user", "content": "COMPLEXPLEASE think hard"},
            ],
        },
    )

    routed = fake_engine.prompts[-1]
    assert "You are terse." in routed
    assert "think hard" in routed


def test_non_object_json_body_returns_400(fake_engine):
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json=["not", "an", "object"],
    )

    assert response.status_code == 400
    assert "invalid_request_error" in response.text


@mock_upstream
def test_multimodal_content_routes_on_text_parts_only(fake_engine):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_ok)
    client = make_client(fake_engine)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "m",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "What is in this image?"},
                        {"type": "image_url", "image_url": {"url": "https://example.com/cat.png"}},
                    ],
                }
            ],
        },
    )

    assert response.status_code == 200
    assert fake_engine.prompts == ["What is in this image?"]


class TestRelayCleanup:
    def test_relay_closes_upstream_on_client_disconnect(self):
        import asyncio

        from laya_router.server import _relay

        class FakeUpstreamResponse:
            def __init__(self):
                self.closed = False

            async def aiter_bytes(self):
                yield b"data: one\n\n"
                yield b"data: [DONE]\n\n"

            async def aclose(self):
                self.closed = True

        async def scenario():
            upstream_response = FakeUpstreamResponse()
            relay = _relay(upstream_response)
            first = await relay.__anext__()
            # Client disconnects mid-stream: starlette closes the generator.
            try:
                await relay.athrow(GeneratorExit)
            except (GeneratorExit, StopAsyncIteration):
                pass
            return first, upstream_response.closed

        first, closed = asyncio.run(scenario())
        assert first == b"data: one\n\n"
        assert closed is True

    def test_relay_closes_upstream_after_normal_completion(self):
        import asyncio

        from laya_router.server import _relay

        class FakeUpstreamResponse:
            def __init__(self):
                self.closed = False

            async def aiter_bytes(self):
                yield b"a"
                yield b"b"

            async def aclose(self):
                self.closed = True

        async def scenario():
            upstream_response = FakeUpstreamResponse()
            relay = _relay(upstream_response)
            chunks = [c async for c in relay]
            return chunks, upstream_response.closed

        chunks, closed = asyncio.run(scenario())
        assert chunks == [b"a", b"b"]
        assert closed is True
