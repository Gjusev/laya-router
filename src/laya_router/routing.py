"""Routing engine: wrap an in-process laya Router to classify each prompt.

The laya checkpoint download happens lazily inside laya itself (on first
predict), so importing this module never touches the network. Tests inject a
stub router via `LayaRoutingEngine(router=...)` to stay offline.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol

from laya_router.policy import RoutingDecision, choose_tier

# v1 question set (see plan section 3). One forward pass answers all three;
# Phase 1 routes on `complexity`, the other two feed Phase 2 gating/backtest.
QUESTIONS: Dict[str, Dict[str, Any]] = {
    "complexity": {
        "type": "choice",
        "instructions": "How complex is this request?",
        "criteria": {
            "simple": "greetings, FAQs, single-fact lookups, formatting",
            "standard": "summarize, extract, translate, simple code edits",
            "complex": "multi-step reasoning, refactors, math, long context",
        },
    },
    "is_coding": {
        "type": "noul",
        "instructions": "Does this request require writing or debugging code?",
    },
    "needs_precision": {
        "type": "noul",
        "instructions": "Would a wrong answer have a high cost?",
    },
}


class RoutingEngine(Protocol):
    def decide(self, prompt: str) -> RoutingDecision: ...


class LayaRoutingEngine:
    """Route prompts with a local laya `Router` (one forward pass, CPU)."""

    def __init__(self, router: Optional[Any] = None):
        # Imported lazily so `import laya_router.routing` stays checkpoint-free.
        if router is None:
            from laya import Router

            router = Router()
        self._router = router

    def decide(self, prompt: str) -> RoutingDecision:
        answers = self._router.predict(prompt, QUESTIONS)["answers"]
        complexity = answers["complexity"]["choice"]
        confidence = float(answers["complexity"]["answer_confidence"])
        return RoutingDecision(
            tier=choose_tier(complexity),
            complexity=complexity,
            answer_confidence=confidence,
            reason=f"complexity={complexity}",
        )
