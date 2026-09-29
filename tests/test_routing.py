"""Seam: routing engine — question schema guard and laya payload mapping.

The real laya Router is faked here; only the mapping from a laya payload to a
RoutingDecision is under test (no checkpoint downloads).
"""

from laya_router.routing import QUESTIONS, LayaRoutingEngine, RoutingDecision


class StubLayaRouter:
    """Returns a canned laya `Router.predict` payload and records the call."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        return self.payload


def payload_for(complexity: str, confidence: float) -> dict:
    # Mirrors the real laya `Router.predict` payload: answers nested under "answers".
    return {
        "model": "laya-rl-agent",
        "answers": {
            "complexity": {
                "type": "choice",
                "choice": complexity,
                "answer_confidence": confidence,
            },
            "is_coding": {"type": "noul", "noul": 0.1, "answer_confidence": 0.9},
            "needs_precision": {"type": "noul", "noul": 0.2, "answer_confidence": 0.8},
        },
        "usage": {"input_tokens": 10, "output_tokens": 0},
        "routing": {"model": "english", "reason": "test"},
    }


class TestQuestionSchema:
    def test_complexity_is_a_three_way_choice(self):
        q = QUESTIONS["complexity"]
        assert q["type"] == "choice"
        assert set(q["criteria"]) == {"simple", "standard", "complex"}

    def test_binary_questions_are_noul(self):
        assert QUESTIONS["is_coding"]["type"] == "noul"
        assert QUESTIONS["needs_precision"]["type"] == "noul"


class TestLayaRoutingEngine:
    def test_complex_payload_maps_to_frontier(self):
        stub = StubLayaRouter(payload_for("complex", 0.42))
        engine = LayaRoutingEngine(router=stub)
        decision = engine.decide("prove the Riemann hypothesis")
        assert decision == RoutingDecision(
            tier="frontier",
            complexity="complex",
            answer_confidence=0.42,
            reason="complexity=complex",
        )

    def test_simple_payload_maps_to_cheap(self):
        stub = StubLayaRouter(payload_for("simple", 0.95))
        decision = LayaRoutingEngine(router=stub).decide("hi")
        assert decision.tier == "cheap"
        assert decision.complexity == "simple"

    def test_prompt_and_questions_are_passed_through(self):
        stub = StubLayaRouter(payload_for("simple", 0.9))
        LayaRoutingEngine(router=stub).decide("hello there")
        state, questions = stub.calls[0]
        assert state == "hello there"
        assert questions == QUESTIONS
