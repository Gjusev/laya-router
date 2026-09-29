"""Seam: routing policy — complexity label to tier mapping."""

import pytest

from laya_router.policy import choose_tier


@pytest.mark.parametrize("complexity", ["simple", "standard"])
def test_easy_prompts_go_cheap(complexity):
    assert choose_tier(complexity) == "cheap"


def test_complex_prompts_go_frontier():
    assert choose_tier("complex") == "frontier"


def test_unknown_label_escalates_to_frontier():
    # Spend more rather than risk quality when the label is unexpected.
    assert choose_tier("something-new") == "frontier"
