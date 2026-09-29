"""Acceptance-criteria seam: the official OpenAI SDK works against a real
localhost server with only base_url changed — no other client-code changes.

A throwaway uvicorn serves the app on an ephemeral loopback port; the upstream
is mocked with respx. No laya checkpoints are loaded (fake engine).
"""

import json
import threading
import time

import httpx
import openai
import pytest
import respx
import uvicorn

from laya_router.config import Settings
from laya_router.server import create_app

from conftest import TEST_UPSTREAM, FakeRoutingEngine

# Scoped to the mock upstream so respx never intercepts the SDK's own
# request to the in-test localhost server.
mock_upstream = respx.mock(base_url=TEST_UPSTREAM)


@pytest.fixture
def proxy_base_url():
    settings = Settings(_env_file=None, upstream_base_url=TEST_UPSTREAM)
    app = create_app(settings=settings, engine=FakeRoutingEngine())
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "uvicorn did not start"
    port = server.servers[0].sockets[0].getsockname()[1]
    yield f"http://127.0.0.1:{port}/v1"
    server.should_exit = True
    thread.join(timeout=10)
    assert not thread.is_alive(), "uvicorn server thread did not shut down"


def upstream_echo(request: httpx.Request) -> httpx.Response:
    """Mock upstream: echo the model it was actually called with."""
    body = json.loads(request.content)
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-e2e",
            "object": "chat.completion",
            "model": body["model"],
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": "hello from upstream"},
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        },
    )


@mock_upstream
def test_sdk_completion_returns_content_and_route_header(proxy_base_url):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_echo)
    client = openai.OpenAI(base_url=proxy_base_url, api_key="test-key")

    raw = client.with_raw_response.chat.completions.create(
        model="gpt-4o",  # client asks for the expensive model; the router overrides it
        messages=[{"role": "user", "content": "Say hi"}],
    )

    assert raw.headers["x-laya-route"] == "cheap"
    completion = raw.parse()
    assert completion.choices[0].message.content == "hello from upstream"
    assert completion.model == "gpt-4o-mini"


@mock_upstream
def test_sdk_complex_prompt_escalates_to_frontier(proxy_base_url):
    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=upstream_echo)
    client = openai.OpenAI(base_url=proxy_base_url, api_key="test-key")

    completion = client.chat.completions.create(
        model="whatever",
        messages=[{"role": "user", "content": "COMPLEXPLEASE refactor this distributed system"}],
    )

    # The upstream echoes the model it received, so this proves the routing.
    assert completion.model == "gpt-4o"


@mock_upstream
def test_sdk_streaming_receives_sse_chunks(proxy_base_url):
    async def sse_bytes():
        for text in ("Hel", "lo ", "world"):
            chunk = {
                "id": "chatcmpl-e2e",
                "object": "chat.completion.chunk",
                "model": "gpt-4o-mini",
                "choices": [
                    {"index": 0, "delta": {"content": text}, "finish_reason": None}
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n".encode()
        yield b"data: [DONE]\n\n"

    mock_upstream.post(f"{TEST_UPSTREAM}/chat/completions").mock(
        return_value=httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=sse_bytes()
        )
    )
    client = openai.OpenAI(base_url=proxy_base_url, api_key="test-key")

    stream = client.chat.completions.create(
        model="whatever",
        stream=True,
        messages=[{"role": "user", "content": "Say hello"}],
    )
    received = "".join(
        part.choices[0].delta.content or "" for part in stream if part.choices
    )

    assert received == "Hello world"
