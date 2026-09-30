"""Benchmark local routing-decision latency (closes the TODO(measure) in the README).

Measures the one-time cold start (checkpoint load on the first decision) and
warm per-decision wall time over the backtest dataset.

Usage:
    python backtest/bench_latency.py [--dataset backtest/dataset.jsonl]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from laya_router.routing import LayaRoutingEngine


def percentile(sorted_values: list[float], q: float) -> float:
    return sorted_values[int(len(sorted_values) * q) - 1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("backtest/dataset.jsonl"))
    args = parser.parse_args()

    prompts = [json.loads(line)["prompt"] for line in args.dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
    engine = LayaRoutingEngine()

    started = time.perf_counter()
    engine.decide(prompts[0])  # cold: builds/loads the laya checkpoints
    cold_ms = (time.perf_counter() - started) * 1000

    latencies = []
    for prompt in prompts[1:]:
        started = time.perf_counter()
        engine.decide(prompt)
        latencies.append((time.perf_counter() - started) * 1000)
    latencies.sort()

    print(f"n={len(latencies)} cold_first_decision_ms={cold_ms:.0f}")
    print(
        f"p50_ms={statistics.median(latencies):.0f} "
        f"p95_ms={percentile(latencies, 0.95):.0f} "
        f"p99_ms={percentile(latencies, 0.99):.0f} "
        f"max_ms={latencies[-1]:.0f} mean_ms={statistics.mean(latencies):.0f}"
    )


if __name__ == "__main__":
    main()
