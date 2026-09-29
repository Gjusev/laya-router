"""Shared fixtures: deterministic fakes so unit tests never download laya
checkpoints, and environment isolation so LAYA_ROUTER_* variables in the
developer's shell cannot leak into test settings."""

import os

import pytest

from laya_router.routing import RoutingDecision

TEST_UPSTREAM = "http://upstream.test/v1"


class FakeRoutingEngine:
    """Deterministic engine: a marker word in the prompt picks the decision.

    Tier mappings are hardcoded (not derived from production policy code) so
    server-level tests assert against independent expected values.
    """

    MARKERS = {
        "COMPLEXPLEASE": ("complex", "frontier", 0.5),
        "MEDIUMPLEASE": ("standard", "cheap", 0.7),
    }

    def __init__(self):
        self.prompts = []

    def decide(self, prompt: str) -> RoutingDecision:
        self.prompts.append(prompt)
        for marker, (complexity, tier, confidence) in self.MARKERS.items():
            if marker in prompt:
                return self._decision(complexity, tier, confidence)
        return self._decision("simple", "cheap", 0.9)

    @staticmethod
    def _decision(complexity: str, tier: str, confidence: float) -> RoutingDecision:
        return RoutingDecision(
            tier=tier,
            complexity=complexity,
            answer_confidence=confidence,
            reason=f"complexity={complexity}",
        )


@pytest.fixture
def fake_engine():
    return FakeRoutingEngine()


@pytest.fixture(autouse=True)
def clean_laya_router_env(monkeypatch):
    """Strip LAYA_ROUTER_* from the environment so Settings() tests see defaults."""
    for key in list(os.environ):
        if key.startswith("LAYA_ROUTER_"):
            monkeypatch.delenv(key)
    yield
