"""Routing policy: how a prompt becomes a tier.

Three layers, cheapest first:
1. fast_path_tier — deterministic regex for greetings/trivia (no model call)
2. choose_tier — complexity label from the laya decision (model was run)
3. apply_min_confidence — escalate to frontier when the model is unsure
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Optional

CHEAP = "cheap"
FRONTIER = "frontier"

_CHEAP_LABELS = frozenset({"simple", "standard"})

# Greetings and other zero-content prompts that never need a frontier model.
_FAST_PATH_RE = re.compile(
    r"^(hi|hello|hey|yo|thanks|thank you|ok|okay)[\s.!,?]*$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class RoutingDecision:
    tier: str
    complexity: str
    answer_confidence: float
    reason: str
    # Auxiliary laya answers (0-1 noul scores), recorded for backtest analysis.
    is_coding: float = 0.0
    needs_precision: float = 0.0


def choose_tier(complexity: str) -> str:
    """Map a complexity label (simple/standard/complex) to a tier.

    Unknown labels escalate to frontier: spend more rather than risk quality.
    """
    return CHEAP if complexity in _CHEAP_LABELS else FRONTIER


def fast_path_tier(prompt: str) -> Optional[str]:
    """Deterministic route for trivial prompts; None means no fast path."""
    return CHEAP if _FAST_PATH_RE.match(prompt.strip()) else None


def apply_min_confidence(decision: RoutingDecision, min_confidence: float) -> RoutingDecision:
    """Escalate to frontier when the decision model reports low confidence."""
    if min_confidence > 0 and decision.answer_confidence < min_confidence:
        return replace(decision, tier=FRONTIER, reason=decision.reason + "+low-confidence")
    return decision
