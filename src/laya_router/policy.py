"""Routing policy: which tier a complexity label maps to.

Phase 1 policy is deliberately minimal — anything the decision model calls
complex goes to the frontier tier, everything else goes cheap. Fast paths and
confidence gating arrive in Phase 2.
"""

from __future__ import annotations

CHEAP = "cheap"
FRONTIER = "frontier"

_CHEAP_LABELS = frozenset({"simple", "standard"})


def choose_tier(complexity: str) -> str:
    """Map a complexity label (simple/standard/complex) to a tier.

    Unknown labels escalate to frontier: spend more rather than risk quality.
    """
    return CHEAP if complexity in _CHEAP_LABELS else FRONTIER
