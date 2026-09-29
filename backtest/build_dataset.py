"""Build the backtest dataset.

Three sources (see the plan):
- MT-Bench: 80 questions, fetched from the FastChat repository (network).
- LMSYS-Chat-1M: a seeded sample of real user turns (network, optional flag;
  the full dataset is large, so it is an explicit opt-in).
- 100 synthetic trivial prompts (deterministic, offline).

Output: JSONL with {"id", "source", "prompt"} per line. Difficulty is NOT
labeled here: the judge decides quality, and the router's own decisions are
recorded during the run.

Usage:
    python backtest/build_dataset.py [--out backtest/dataset.jsonl] [--with-lmsys]
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import httpx

MT_BENCH_URL = (
    "https://raw.githubusercontent.com/lm-sys/FastChat/main/"
    "fastchat/llm_judge/data/mt_bench/question.jsonl"
)
LMSYS_SAMPLE_SIZE = 120
SYNTHETIC_COUNT = 100


def fetch_mt_bench() -> list[dict]:
    response = httpx.get(MT_BENCH_URL, timeout=60, follow_redirects=True)
    response.raise_for_status()
    questions = [json.loads(line) for line in response.text.splitlines() if line.strip()]
    return [
        {"source": "mt_bench", "prompt": q["turns"][0]}
        for q in questions
        if q.get("turns")
    ]


def sample_lmsys(size: int, seed: int) -> list[dict]:
    """Seeded sample of first user turns from lmsys/lmsys-chat-1m on HF."""
    from datasets import load_dataset  # heavy import: only for this opt-in path

    dataset = load_dataset("lmsys/lmsys-chat-1m", split="train")
    rng = random.Random(seed)
    indices = rng.sample(range(len(dataset)), size)
    out = []
    for i in indices:
        conversation = dataset[i]["conversation"]
        first_user = next((m["content"] for m in conversation if m["role"] == "user"), None)
        # Skip toxic/empty rows the same way the dataset's own README recommends.
        if first_user and not dataset[i]["toxic"] and len(first_user) < 4000:
            out.append({"source": "lmsys", "prompt": first_user})
    return out


_TRIVIAL_TEMPLATES = [
    "hi",
    "hello",
    "hey there",
    "good morning",
    "good evening",
    "thanks",
    "thank you",
    "what is your name?",
    "what time is it?",
    "Say hello in French.",
    "Say goodbye in German.",
    "Give me a random number between 1 and 10.",
    "Translate 'good night' to Spanish.",
    "What is 2 + 2?",
    "What is 10 minus 3?",
    "Capital of France?",
    "Capital of Japan?",
    "Tell me a short greeting.",
    "Confirm you are ready.",
    "Reply with the word yes.",
    "Count to three.",
    "Name a primary color.",
    "How many days are in a week?",
    "What color is the sky on a clear day?",
    "Say my name back: John.",
]
_TRIVIAL_MODIFIERS = ["", " please", " quickly", " thanks in advance", " 🙂"]


def synthetic_trivial(count: int, seed: int) -> list[dict]:
    combos = [
        template + modifier for template in _TRIVIAL_TEMPLATES for modifier in _TRIVIAL_MODIFIERS
    ]
    if count > len(combos):
        raise ValueError(f"only {len(combos)} unique trivial prompts available, asked for {count}")
    rng = random.Random(seed)
    rng.shuffle(combos)
    return [
        {"source": "synthetic_trivial", "prompt": prompt[0].upper() + prompt[1:]}
        for prompt in combos[:count]
    ]


def build(out_path: Path, with_lmsys: bool, seed: int) -> None:
    entries = []
    entries += fetch_mt_bench()
    if with_lmsys:
        entries += sample_lmsys(LMSYS_SAMPLE_SIZE, seed)
    entries += synthetic_trivial(SYNTHETIC_COUNT, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as handle:
        for i, entry in enumerate(entries):
            handle.write(json.dumps({"id": i, **entry}, ensure_ascii=False) + "\n")
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["source"]] = counts.get(entry["source"], 0) + 1
    print(f"wrote {len(entries)} prompts to {out_path}: {counts}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("backtest/dataset.jsonl"))
    parser.add_argument("--with-lmsys", action="store_true", help="opt in to the LMSYS-Chat-1m sample download")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    build(args.out, args.with_lmsys, args.seed)


if __name__ == "__main__":
    main()
