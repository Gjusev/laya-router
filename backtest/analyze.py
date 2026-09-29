"""Analyze backtest results into the published numbers table.

Definitions (published with the results, see the plan):
- Router "correct"  -> routed cheap and the judge says win/tie
- Router "miss"     -> routed cheap and the judge says lose (false negative)
- "Over-escalation" -> routed frontier although the question was not complex
  (only costs money; not a quality error)
- Cost saving is computed from actual token usage and the list prices in
  tiers.yaml, comparing the router against always-frontier.

Usage:
    python backtest/analyze.py [--results backtest/results.jsonl]
                               [--judgements backtest/judgements.jsonl]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from laya_router.config import load_tiers


def answer_cost(usage: dict, model: str, tiers) -> float:
    tier = tiers.cheap if model == tiers.cheap.model else tiers.frontier
    return (
        usage["input_tokens"] * tier.price.input_per_m
        + usage["output_tokens"] * tier.price.output_per_m
    ) / 1_000_000


def load_lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def analyze(results: list[dict], judgements: list[dict]) -> str:
    tiers = load_tiers()
    outcomes = {j["id"]: j["outcome"] for j in judgements}

    total = len(results)
    routed_cheap = sum(1 for r in results if r["router"]["tier"] == "cheap")
    correct = misses = over_escalations = 0
    router_cost = always_frontier_cost = 0.0
    wins = ties = losses = 0

    for record in results:
        cheap_cost = answer_cost(record["cheap"]["usage"], tiers.cheap.model, tiers)
        frontier_cost = answer_cost(record["frontier"]["usage"], tiers.frontier.model, tiers)
        always_frontier_cost += frontier_cost

        if record["router"]["tier"] == "cheap":
            router_cost += cheap_cost
            outcome = outcomes.get(record["id"])
            if outcome == "win":
                wins += 1
                correct += 1
            elif outcome == "tie":
                ties += 1
                correct += 1
            elif outcome == "lose":
                losses += 1
                misses += 1
        else:
            router_cost += frontier_cost
            over_escalations += 1

    judged = wins + ties + losses
    win_rate_delta = (wins + 0.5 * ties) / judged - 1.0 if judged else None
    saving_pct = (
        (1.0 - router_cost / always_frontier_cost) * 100 if always_frontier_cost else None
    )
    routing_precision = correct / (correct + misses) if (correct + misses) else None

    def pct(value) -> str:
        return f"{value:.1f}" if value is not None else "TODO(measure)"

    return "\n".join([
        "| Metric | Value |",
        "|---|---|",
        f"| Prompts (both tiers answered) | {total} |",
        f"| % routed to cheap | {pct(100 * routed_cheap / total if total else None)} |",
        f"| Cost saving vs always-frontier | {pct(saving_pct)}% |",
        f"| Win/tie/lose of cheap vs frontier (judged) | {wins}/{ties}/{losses} |",
        f"| Win-rate delta (router vs always-frontier) | {pct(100 * win_rate_delta if win_rate_delta is not None else None)}% |",
        f"| Routing precision (cheap verdict win/tie) | {pct(100 * routing_precision if routing_precision is not None else None)}% |",
        f"| Over-escalations (frontier, costly only) | {over_escalations} |",
        f"| Routing cost per 1,000 requests | $0 (local laya) |",
    ])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("backtest/results.jsonl"))
    parser.add_argument("--judgements", type=Path, default=Path("backtest/judgements.jsonl"))
    args = parser.parse_args()
    print(analyze(load_lines(args.results), load_lines(args.judgements)))


if __name__ == "__main__":
    main()
