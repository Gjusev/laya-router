"""Blind judge: compare the cheap answer against the frontier answer.

Design (see the plan):
- Same judge model for every pair, temperature 0, fixed rubric.
- Blind: a seeded shuffle decides whether cheap is Answer A or B, and the
  verdict is mapped back to win/tie/lose from the CHEAP answer's perspective.
- Verdict grammar: the last [[A]] / [[B]] / [[tie]] token in the reply.

Usage:
    python backtest/judge.py [--results backtest/results.jsonl]
                             [--out backtest/judgements.jsonl] [--limit N]
    LAYA_ROUTER_JUDGE_MODEL (default: the frontier model) selects the judge.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from openai import OpenAI

from run_backtest import build_tiers, with_rate_limit_retries

RUBRIC = """You are an impartial judge evaluating two answers to the same question.

Rubric, in order of importance:
1. Correctness: factual and logical soundness.
2. Completeness: does it fully answer the question?
3. Instruction-following: does it respect what was asked?

Ignore answer length and style unless the question explicitly demands them.
If both answers are equally good or equally bad, it is a tie.

### Question
{question}

### Answer A
{answer_a}

### Answer B
{answer_b}

First give a one-sentence justification. Then, on the last line, output
exactly one of: [[A]], [[B]], [[tie]]"""

VERDICT_RE = re.compile(r"\[\[\s*(A|B|tie)\s*\]\]", re.IGNORECASE)


def parse_verdict(reply: str) -> str:
    matches = VERDICT_RE.findall(reply)
    if not matches:
        raise ValueError(f"judge reply contains no [[A]]/[[B]]/[[tie]] token: {reply!r}")
    return matches[-1].lower()


def to_outcome(verdict: str, cheap_is: str) -> str:
    """Map the judge's A/B verdict to win/tie/lose for the cheap answer."""
    if verdict == "tie":
        return "tie"
    return "win" if verdict == cheap_is else "lose"


def judge_pair(client: OpenAI, judge_model: str, record: dict, cheap_is: str) -> dict:
    answer_a = record["cheap"]["content"] if cheap_is == "a" else record["frontier"]["content"]
    answer_b = record["frontier"]["content"] if cheap_is == "a" else record["cheap"]["content"]

    def call() -> str:
        return client.chat.completions.create(
            model=judge_model,
            messages=[{"role": "user", "content": RUBRIC.format(
                question=record["prompt"], answer_a=answer_a, answer_b=answer_b)}],
            # Reasoning models spend tokens thinking before the verdict; low
            # effort keeps the budget on the verdict itself.
            max_tokens=2048,
            temperature=0,
            extra_body={"reasoning_effort": "low"},
        ).choices[0].message.content

    reply = with_rate_limit_retries(call)
    verdict = parse_verdict(reply or "")
    return {
        "id": record["id"],
        "source": record["source"],
        "router_tier": record["router"]["tier"],
        "cheap_is": cheap_is,
        "verdict": verdict,
        "outcome": to_outcome(verdict, cheap_is),
        "justification": reply,
    }


def run(results_path: Path, out_path: Path, limit: int | None, seed: int, tiers_path: Path | None, workers: int = 1) -> None:
    records = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        records = records[:limit]
    judge_model = build_tiers(tiers_path).frontier.model
    client = OpenAI()
    rng = random.Random(seed)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    done_ids = set()
    if out_path.exists():
        done_ids = {
            json.loads(line)["id"]
            for line in out_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }
    remaining = [r for r in records if r["id"] not in done_ids]
    # Blind positions drawn up front (deterministic per seed) so parallel
    # execution cannot change the assignment.
    assignments = {r["id"]: rng.choice(["a", "b"]) for r in remaining}

    def fetch(record: dict) -> dict:
        return judge_pair(client, judge_model, record, assignments[record["id"]])

    written = 0
    with out_path.open("a", encoding="utf-8") as out:  # append: resumable
        if workers <= 1:
            for record in remaining:
                judgement = fetch(record)
                out.write(json.dumps(judgement, ensure_ascii=False) + "\n")
                out.flush()
                written += 1
                print(f"[{written}/{len(remaining)}] {record['source']} -> {judgement['outcome']}", flush=True)
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(fetch, record) for record in remaining]
                for future in as_completed(futures):
                    judgement = future.result()
                    out.write(json.dumps(judgement, ensure_ascii=False) + "\n")
                    out.flush()
                    written += 1
                    print(f"[{written}/{len(remaining)}] {judgement['source']} -> {judgement['outcome']}", flush=True)
    print(f"wrote {written} new judgements to {out_path} ({len(done_ids)} already present)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("backtest/results.jsonl"))
    parser.add_argument("--out", type=Path, default=Path("backtest/judgements.jsonl"))
    parser.add_argument("--tiers", type=Path, default=None, help="tiers.yaml override (default: LAYA_ROUTER_TIERS_FILE or packaged)")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--workers", type=int, default=1, help="parallel judge requests")
    args = parser.parse_args()
    run(args.results, args.out, args.limit, args.seed, args.tiers, args.workers)


if __name__ == "__main__":
    main()
