"""Observability: Prometheus metrics and the JSONL decision log.

Counters are module-level singletons so repeated create_app() calls (tests,
multi-worker imports) never double-register with the default registry.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Union

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

REQUESTS_TOTAL = Counter(
    "laya_router_requests_total",
    "Routed chat completion requests.",
    ["tier", "status"],
)
ROUTING_SECONDS = Histogram(
    "laya_router_routing_seconds",
    "Wall-clock time of the routing decision (fast path or laya).",
)

PROMETHEUS_CONTENT_TYPE = CONTENT_TYPE_LATEST


def metrics_payload() -> bytes:
    return generate_latest()


class DecisionLog:
    """Append-only JSONL log of routing decisions (one line per request)."""

    def __init__(self, path: Union[str, Path]):
        self._path = Path(path)

    def write(self, entry: dict) -> None:
        record = {"ts": datetime.now(timezone.utc).isoformat(), **entry}
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def log_entry(
    *,
    tier: str,
    model: str,
    complexity: str,
    answer_confidence: float,
    reason: str,
    status: int,
    routing_seconds: float,
    prompt: str,
    preview_chars: int = 200,
) -> dict:
    return {
        "tier": tier,
        "model": model,
        "complexity": complexity,
        "answer_confidence": answer_confidence,
        "reason": reason,
        "status": status,
        "latency_ms": round(routing_seconds * 1000, 2),
        "prompt_chars": len(prompt),
        "preview": prompt[:preview_chars],
    }
