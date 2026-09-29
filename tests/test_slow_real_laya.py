"""Opt-in tests against the real laya engine: they download checkpoints on
first use, so they are marked slow and skipped by default.

Run explicitly with: pytest -m slow
"""

import pytest

from laya_router.routing import LayaRoutingEngine


@pytest.mark.slow
def test_real_laya_engine_routes_a_simple_prompt():
    engine = LayaRoutingEngine()  # downloads laya checkpoints on first predict
    decision = engine.decide("hi")
    assert decision.tier in {"cheap", "frontier"}
    assert decision.complexity in {"simple", "standard", "complex"}
    assert 0.0 <= decision.answer_confidence <= 1.0


@pytest.mark.slow
def test_real_laya_engine_routes_a_complex_prompt():
    engine = LayaRoutingEngine()
    decision = engine.decide(
        "Prove that every bounded monotone sequence of real numbers converges, "
        "then refactor this proof into a typed Python function with tests."
    )
    assert decision.tier in {"cheap", "frontier"}
    assert 0.0 <= decision.answer_confidence <= 1.0
