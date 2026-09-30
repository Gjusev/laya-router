"""Backtest pipeline: dataset builder, blind judge parsing, and the analyze
numbers table. All offline — the OpenAI client is faked where used.

Expected table numbers in test_analyze_table are computed by hand from the
fixture usages and the tiers.yaml list prices, independently of analyze.py.
"""

import sys
from pathlib import Path

import pytest

BACKTEST_DIR = Path(__file__).resolve().parent.parent / "backtest"
sys.path.insert(0, str(BACKTEST_DIR))

import analyze  # noqa: E402
import build_dataset  # noqa: E402
import judge  # noqa: E402
from run_backtest import build_tiers  # noqa: E402


class TestSyntheticDataset:
    def test_generates_unique_deterministic_prompts(self):
        first = build_dataset.synthetic_trivial(100, seed=7)
        second = build_dataset.synthetic_trivial(100, seed=7)
        assert len(first) == 100
        assert len({e["prompt"] for e in first}) == 100
        assert first == second

    def test_different_seed_changes_sample(self):
        assert build_dataset.synthetic_trivial(100, seed=7) != build_dataset.synthetic_trivial(100, seed=8)

    def test_all_entries_tagged_synthetic(self):
        entries = build_dataset.synthetic_trivial(10, seed=1)
        assert all(e["source"] == "synthetic_trivial" for e in entries)


class TestJudgeParsing:
    @pytest.mark.parametrize(
        "reply,expected",
        [
            ("Both fine. [[A]]", "a"),
            ("B is better. [[B]]", "b"),
            ("Equal quality. [[tie]]", "tie"),
            ("First [[A]], corrected: [[ tie ]]", "tie"),  # last token wins
            ("[[b]]", "b"),
        ],
    )
    def test_parse_verdict(self, reply, expected):
        assert judge.parse_verdict(reply) == expected

    def test_parse_verdict_rejects_unparseable_reply(self):
        with pytest.raises(ValueError):
            judge.parse_verdict("I cannot decide between these two.")

    def test_outcome_from_cheap_perspective(self):
        assert judge.to_outcome("a", cheap_is="a") == "win"
        assert judge.to_outcome("b", cheap_is="a") == "lose"
        assert judge.to_outcome("a", cheap_is="b") == "lose"
        assert judge.to_outcome("tie", cheap_is="a") == "tie"


class FakeCompletions:
    def __init__(self, client):
        self._client = client
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        content = self._client.replies.pop(0) if self._client.replies else ""
        message = type("M", (), {"content": content})()
        choice = type("C", (), {"message": message})()
        return type("R", (), {"choices": [choice]})()


class FakeJudgeClient:
    """Mimics the OpenAI SDK surface judge_pair uses (no network).

    Accepts one reply or a list consumed call by call.
    """

    def __init__(self, content):
        self.replies = list(content) if isinstance(content, list) else [content]
        completions = FakeCompletions(self)
        self.chat = type("Chat", (), {"completions": completions})()


class TestJudgePair:
    def test_blind_judgement_maps_back_to_cheap_perspective(self):
        client = FakeJudgeClient("B looks better. [[B]]")
        record = {
            "id": 1,
            "source": "synthetic_trivial",
            "prompt": "question",
            "router": {"tier": "cheap"},
            "cheap": {"content": "cheap answer"},
            "frontier": {"content": "frontier answer"},
        }

        judgement = judge.judge_pair(client, "judge-model", record, cheap_is="a")

        # The judge said B; cheap was A, so cheap loses.
        assert judgement["cheap_is"] == "a"
        assert judgement["verdict"] == "b"
        assert judgement["outcome"] == "lose"
        sent = client.chat.completions.requests[0]
        assert sent["model"] == "judge-model"
        assert sent["temperature"] == 0
        assert "cheap answer" in sent["messages"][0]["content"]
        assert "frontier answer" in sent["messages"][0]["content"]

    def test_rubric_is_fixed_and_contains_both_answers(self):
        client = FakeJudgeClient("[[tie]]")
        record = {
            "id": 2,
            "source": "mt_bench",
            "prompt": "the question",
            "router": {"tier": "cheap"},
            "cheap": {"content": "ANSWER_CHEAP"},
            "frontier": {"content": "ANSWER_FRONTIER"},
        }

        judge.judge_pair(client, "judge-model", record, cheap_is="b")

        rubric = client.chat.completions.requests[0]["messages"][0]["content"]
        assert "impartial judge" in rubric
        assert "the question" in rubric
        assert "ANSWER_CHEAP" in rubric
        assert "ANSWER_FRONTIER" in rubric


def fixture_results() -> list[dict]:
    usage = {"input_tokens": 1000, "output_tokens": 100}
    return [
        {
            "id": 1,
            "source": "synthetic_trivial",
            "prompt": "p1",
            "router": {"tier": "cheap", "complexity": "simple", "answer_confidence": 0.9, "reason": "r"},
            "cheap": {"model": "gpt-4o-mini", "content": "c1", "usage": usage},
            "frontier": {"model": "gpt-4o", "content": "f1", "usage": usage},
        },
        {
            "id": 2,
            "source": "synthetic_trivial",
            "prompt": "p2",
            "router": {"tier": "cheap", "complexity": "simple", "answer_confidence": 0.9, "reason": "r"},
            "cheap": {"model": "gpt-4o-mini", "content": "c2", "usage": usage},
            "frontier": {"model": "gpt-4o", "content": "f2", "usage": usage},
        },
        {
            "id": 3,
            "source": "mt_bench",
            "prompt": "p3",
            "router": {"tier": "frontier", "complexity": "complex", "answer_confidence": 0.5, "reason": "r"},
            "cheap": {"model": "gpt-4o-mini", "content": "c3", "usage": usage},
            "frontier": {"model": "gpt-4o", "content": "f3", "usage": usage},
        },
    ]


class TestAnalyze:
    def test_analyze_table(self, tmp_path, monkeypatch):
        monkeypatch.chdir(Path(__file__).resolve().parent.parent)  # analyze loads packaged tiers
        judgements = [
            {"id": 1, "outcome": "win"},
            {"id": 2, "outcome": "lose"},
        ]
        # Hand-computed from tiers.yaml prices (cheap 0.15/0.60, frontier 2.50/10.00 per 1M):
        # per record: cheap = (1000*0.15 + 100*0.60)/1e6 = 0.00021
        #             frontier = (1000*2.50 + 100*10.00)/1e6 = 0.0035
        # router cost = 2*0.00021 + 0.0035 = 0.00392; always-frontier = 3*0.0035 = 0.0105
        # saving = 1 - 0.00392/0.0105 = 62.666...%
        table = analyze.analyze(fixture_results(), judgements)

        assert "| Prompts (both tiers answered) | 3 |" in table
        assert "| % routed to cheap | 66.7 |" in table
        assert "| Cost saving vs always-frontier | 62.7% |" in table
        assert "| Win/tie/lose of cheap vs frontier (judged) | 1/0/1 |" in table
        assert "| Win-rate delta (router vs always-frontier) | -50.0% |" in table
        assert "| Routing precision (cheap verdict win/tie) | 50.0% |" in table
        assert "| Over-escalations (frontier, costly only) | 1 |" in table

    def test_analyze_empty_inputs_use_placeholders(self, monkeypatch):
        monkeypatch.chdir(Path(__file__).resolve().parent.parent)
        table = analyze.analyze([], [])
        assert "TODO(measure)" in table


class TestTiersSelection:
    def test_explicit_path_wins(self, tmp_path):
        custom = tmp_path / "tiers.yaml"
        custom.write_text(
            "cheap:\n  model: glm-4.5-flash\n  price: {input_per_m: 0, output_per_m: 0}\n"
            "frontier:\n  model: glm-4.5\n  price: {input_per_m: 0.60, output_per_m: 2.20}\n"
        )
        assert build_tiers(custom).frontier.model == "glm-4.5"

    def test_env_var_used_when_no_path(self, tmp_path, monkeypatch):
        custom = tmp_path / "tiers.yaml"
        custom.write_text(
            "cheap:\n  model: glm-4.5-flash\n  price: {input_per_m: 0, output_per_m: 0}\n"
            "frontier:\n  model: glm-4.5\n  price: {input_per_m: 0.60, output_per_m: 2.20}\n"
        )
        monkeypatch.setenv("LAYA_ROUTER_TIERS_FILE", str(custom))
        assert build_tiers(None).cheap.model == "glm-4.5-flash"

    def test_packaged_default_when_nothing_set(self, monkeypatch):
        monkeypatch.delenv("LAYA_ROUTER_TIERS_FILE", raising=False)
        assert build_tiers(None).cheap.model == "gpt-4o-mini"


class TestJudgeFallback:
    def test_missing_token_triggers_corrective_retry(self):
        client = FakeJudgeClient([
            "Answer B is more complete; Answer A has a minor error.",  # no token
            "[[B]]",
        ])
        record = {
            "id": 9,
            "source": "mt_bench",
            "prompt": "q",
            "router": {"tier": "cheap"},
            "cheap": {"content": "a1"},
            "frontier": {"content": "a2"},
        }

        judgement = judge.judge_pair(client, "judge-model", record, cheap_is="a")

        assert judgement["verdict"] == "b"
        assert judgement["outcome"] == "lose"
        assert len(client.chat.completions.requests) == 2

    def test_unparseable_after_retry_does_not_crash_the_run(self):
        client = FakeJudgeClient(["prose with no verdict", "still no verdict"])
        record = {
            "id": 10,
            "source": "mt_bench",
            "prompt": "q",
            "router": {"tier": "cheap"},
            "cheap": {"content": "a1"},
            "frontier": {"content": "a2"},
        }

        judgement = judge.judge_pair(client, "judge-model", record, cheap_is="a")

        assert judgement["verdict"] == "unparseable"
        assert judgement["outcome"] == "unparseable"
