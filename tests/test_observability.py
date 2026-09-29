"""Seam: observability (healthz, Prometheus metrics, JSONL decision log) and
the basic per-client rate limit."""

import json

import pytest
from fastapi.testclient import TestClient

from laya_router.config import Settings
from laya_router.server import create_app

from conftest import TEST_UPSTREAM


def make_client(fake_engine, respx_mock, **overrides) -> TestClient:
    import httpx

    respx_mock.post(f"{TEST_UPSTREAM}/chat/completions").mock(side_effect=lambda request: httpx.Response(200, json={"id": "x", "object": "chat.completion", "model": "gpt-4o-mini", "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "ok"}}]}))
    settings = Settings(_env_file=None, upstream_base_url=TEST_UPSTREAM, **overrides)
    return TestClient(create_app(settings=settings, engine=fake_engine))


def post(client: TestClient, content: str = "please summarize this text"):
    return client.post(
        "/v1/chat/completions",
        json={"model": "m", "messages": [{"role": "user", "content": content}]},
    )


class TestHealthz:
    def test_healthz_returns_ok(self, fake_engine):
        client = TestClient(create_app(engine=fake_engine))
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestMetrics:
    def test_metrics_exposes_request_counter(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock)
        assert post(client).status_code == 200

        response = client.get("/metrics")

        assert response.status_code == 200
        assert "laya_router_requests_total" in response.text

    def test_metrics_contains_tier_label(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock)
        post(client, content="COMPLEXPLEASE do hard math")

        metrics = client.get("/metrics").text

        assert 'tier="frontier"' in metrics


class TestDecisionLog:
    def test_decision_log_writes_one_json_line_per_request(self, fake_engine, respx_mock, tmp_path):
        log = tmp_path / "decisions.jsonl"
        client = make_client(fake_engine, respx_mock, decision_log=log)

        assert post(client).status_code == 200
        assert post(client, content="hi").status_code == 200  # fast path

        lines = [json.loads(line) for line in log.read_text().splitlines()]
        assert len(lines) == 2
        first, second = lines
        assert first["tier"] == "cheap"
        assert first["model"] == "gpt-4o-mini"
        assert first["complexity"] == "simple"
        assert first["status"] == 200
        assert first["latency_ms"] >= 0
        assert first["prompt_chars"] > 0
        assert second["complexity"] == "fast-path"

    def test_no_log_file_when_unset(self, fake_engine, respx_mock, tmp_path):
        client = make_client(fake_engine, respx_mock)
        assert post(client).status_code == 200
        assert list(tmp_path.iterdir()) == []


class TestRateLimit:
    def test_requests_beyond_limit_get_429(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock, rate_limit_rpm=2)

        assert post(client).status_code == 200
        assert post(client).status_code == 200
        third = post(client)

        assert third.status_code == 429
        assert third.json()["error"]["type"] == "rate_limit_error"
        assert "Retry-After" in third.headers

    def test_rate_limit_resets_after_window(self, fake_engine, respx_mock):
        from laya_router.server import RateLimiter

        limiter = RateLimiter(per_minute=2)
        t = 1000.0
        assert limiter.allow("ip", t)
        assert limiter.allow("ip", t + 1)
        assert not limiter.allow("ip", t + 2)
        assert limiter.allow("ip", t + 61)  # new window

    def test_zero_disables_rate_limit(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock, rate_limit_rpm=0)
        for _ in range(5):
            assert post(client).status_code == 200


class TestSustainedLoad:
    """The plan's criterion: 100 requests in a row without failures.

    This pins sustained correctness (all succeed, every stream completes);
    per-stream connection hygiene is pinned separately by the _relay
    cleanup unit tests in test_server.py.
    """

    def test_100_sequential_mixed_requests_all_succeed(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock)
        statuses = []
        for i in range(100):
            if i % 2 == 0:
                response = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "m",
                        "stream": True,
                        "messages": [{"role": "user", "content": f"please summarize text {i}"}],
                    },
                )
                response.close()
                statuses.append(response.status_code)
            else:
                statuses.append(post(client, content=f"please summarize text {i}").status_code)

        assert statuses == [200] * 100


class TestDegradedPaths:
    def test_routing_engine_failure_returns_503_and_is_counted(self, fake_engine, respx_mock):
        def boom(prompt):
            raise RuntimeError("laya exploded")

        fake_engine.decide = boom
        client = make_client(fake_engine, respx_mock)

        response = post(client)

        assert response.status_code == 503
        assert "routing" in response.json()["error"]["message"].lower()
        assert 'status="503"' in client.get("/metrics").text

    def test_decision_log_failure_never_breaks_responses(self, fake_engine, respx_mock, tmp_path, monkeypatch):
        from laya_router.observability import DecisionLog

        def broken_write(self, entry):
            raise OSError("disk full")

        monkeypatch.setattr(DecisionLog, "write", broken_write)
        client = make_client(fake_engine, respx_mock, decision_log=tmp_path / "d.jsonl")

        assert post(client).status_code == 200

    def test_rate_limited_requests_are_counted(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock, rate_limit_rpm=1)

        post(client)
        post(client)  # 429

        assert 'status="429"' in client.get("/metrics").text

    def test_malformed_requests_are_counted(self, fake_engine, respx_mock):
        client = make_client(fake_engine, respx_mock)

        client.post("/v1/chat/completions", content=b"not json", headers={"content-type": "application/json"})

        assert 'status="400"' in client.get("/metrics").text
