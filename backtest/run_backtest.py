"""Run the backtest: answer EVERY prompt with BOTH tiers.

This is what makes the eval honest: both answers always exist, so a routing
mistake is measurable instead of invisible. The router's own decision is
recorded per prompt too (laya runs locally, so routing costs nothing).

Uses the environment the OpenAI SDK reads (OPENAI_API_KEY / OPENAI_BASE_URL).
Tier model names and prices come from laya-router's tiers.yaml.

Usage:
    python backtest/run_backtest.py [--dataset backtest/dataset.jsonl]
                                    [--out backtest/results.jsonl] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openai import OpenAI, RateLimitError

from laya_router.config import TiersConfig, load_tiers
from laya_router.routing import LayaRoutingEngine

# Generous caps: reasoning models spend tokens thinking before the answer.
MAX_TOKENS = {"cheap": 2048, "frontier": 4096}


def with_rate_limit_retries(fn, attempts: int = 6, base_delay: float = 5.0):
    """Run fn, retrying on upstream rate limits with exponential backoff."""
    for attempt in range(attempts):
        try:
            return fn()
        except RateLimitError:
            if attempt == attempts - 1:
                raise
            delay = base_delay * (2**attempt)
            print(f"rate limited; retrying in {delay:.0f}s", flush=True)
            time.sleep(delay)


def build_tiers(path: Path | None) -> TiersConfig:
    """Explicit --tiers path, then LAYA_ROUTER_TIERS_FILE, then the packaged default."""
    if path is not None:
        return load_tiers(path)
    env_path = os.environ.get("LAYA_ROUTER_TIERS_FILE")
    return load_tiers(Path(env_path) if env_path else None)


def answer(client: OpenAI, model: str, prompt: str, max_tokens: int) -> dict:
    # Reasoning models can burn the whole budget thinking on hard prompts;
    # one retry with a 4x budget covers those instead of failing the run.
    for budget in (max_tokens, max_tokens * 4):
        completion = with_rate_limit_retries(lambda: client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=budget,
            # GLM 5.x always reasons; low keeps the budget on the answer itself.
            extra_body={"reasoning_effort": "low"},
        ))
        content = completion.choices[0].message.content or ""
        if content.strip():
            usage = completion.usage
            return {
                "model": model,
                "content": content,
                "usage": {
                    "input_tokens": usage.prompt_tokens,
                    "output_tokens": usage.completion_tokens,
                },
            }
    raise RuntimeError(f"empty answer from {model} even at {max_tokens * 4} tokens for prompt: {prompt[:80]!r}")


def run(dataset_path: Path, out_path: Path, limit: int | None, tiers_path: Path | None, workers: int = 1) -> None:
    prompts = [json.loads(line) for line in dataset_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        prompts = prompts[:limit]
    tiers = build_tiers(tiers_path)
    engine = LayaRoutingEngine()
    client = OpenAI()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    done_ids = set()
    if out_path.exists():
        done_ids = {
            json.loads(line)["id"]
            for line in out_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    remaining = [e for e in prompts if e["id"] not in done_ids]

    # Phase 1: local routing decisions, sequential (the laya engine is not
    # documented as thread-safe; decisions are fast and free).
    decisions = {}
    for entry in remaining:
        decisions[entry["id"]] = engine.decide(entry["prompt"])

    def fetch(entry: dict) -> dict:
        decision = decisions[entry["id"]]
        cheap = answer(client, tiers.cheap.model, entry["prompt"], MAX_TOKENS["cheap"])
        frontier = answer(client, tiers.frontier.model, entry["prompt"], MAX_TOKENS["frontier"])
        return {
            "id": entry["id"],
            "source": entry["source"],
            "prompt": entry["prompt"],
            "router": {
                "tier": decision.tier,
                "complexity": decision.complexity,
                "answer_confidence": decision.answer_confidence,
                "reason": decision.reason,
                "is_coding": decision.is_coding,
                "needs_precision": decision.needs_precision,
            },
            "cheap": cheap,
            "frontier": frontier,
        }

    written = 0
    with out_path.open("a", encoding="utf-8") as out:  # append: resumable
        if workers <= 1:
            records = (fetch(entry) for entry in remaining)
            for entry, record in zip(remaining, records):
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                written += 1
                print(f"[{written}/{len(remaining)}] {entry['source']} -> router={record['router']['tier']}", flush=True)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(fetch, entry): entry for entry in remaining}
                for future in as_completed(futures):
                    record = future.result()
                    out.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out.flush()
                    written += 1
                    print(f"[{written}/{len(remaining)}] {record['source']} -> router={record['router']['tier']}", flush=True)
    print(f"wrote {written} new records to {out_path} ({len(done_ids)} already present)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("backtest/dataset.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("backtest/results.jsonl"))
    parser.add_argument("--tiers", type=Path, default=None, help="tiers.yaml override (default: LAYA_ROUTER_TIERS_FILE or packaged)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=1, help="parallel upstream requests (routing itself stays local and sequential)")
    args = parser.parse_args()
    run(args.dataset, args.out, args.limit, args.tiers, args.workers)


if __name__ == "__main__":
    main()
