"""Seam: routing policy — complexity label to tier mapping."""

import pytest

from laya_router.policy import RoutingDecision, apply_min_confidence, choose_tier, fast_path_tier


@pytest.mark.parametrize("complexity", ["simple", "standard"])
def test_easy_prompts_go_cheap(complexity):
    assert choose_tier(complexity) == "cheap"


def test_complex_prompts_go_frontier():
    assert choose_tier("complex") == "frontier"


def test_unknown_label_escalates_to_frontier():
    # Spend more rather than risk quality when the label is unexpected.
    assert choose_tier("something-new") == "frontier"


class TestFastPath:
    @pytest.mark.parametrize("prompt", ["hi", "Hello!", "  hey  ", "thanks", "thank you", "ok."])
    def test_greetings_and_trivia_go_cheap_without_the_model(self, prompt):
        assert fast_path_tier(prompt) == "cheap"

    @pytest.mark.parametrize(
        "prompt",
        [
            "hi, can you explain quantum computing?",
            "Summarize this article",
            "",
            "hello there, I need help with a refactor",
        ],
    )
    def test_non_trivial_prompts_get_no_fast_path(self, prompt):
        assert fast_path_tier(prompt) is None


class TestMinConfidenceGate:
    def _decision(self, confidence):
        return RoutingDecision(
            tier="cheap", complexity="standard", answer_confidence=confidence, reason="complexity=standard"
        )

    def test_low_confidence_escalates_to_frontier(self):
        gated = apply_min_confidence(self._decision(0.7), min_confidence=0.75)
        assert gated.tier == "frontier"
        assert "low-confidence" in gated.reason

    def test_confident_decision_is_unchanged(self):
        decision = self._decision(0.9)
        assert apply_min_confidence(decision, min_confidence=0.75) == decision

    def test_zero_threshold_disables_gating(self):
        decision = self._decision(0.1)
        assert apply_min_confidence(decision, min_confidence=0.0) == decision
