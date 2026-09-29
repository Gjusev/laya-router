"""Seam: tier configuration loading (YAML) and settings defaults."""

import textwrap

import pytest

from laya_router.config import Settings, load_tiers


def test_default_tiers_file_loads():
    tiers = load_tiers()
    assert tiers.cheap.model == "gpt-4o-mini"
    assert tiers.frontier.model == "gpt-4o"
    assert tiers.cheap.price.input_per_m > 0
    assert tiers.frontier.price.output_per_m > 0


def test_custom_tiers_file(tmp_path):
    custom = tmp_path / "tiers.yaml"
    custom.write_text(
        textwrap.dedent(
            """\
            cheap:
              model: my-cheap-model
              price: {input_per_m: 0.1, output_per_m: 0.2}
            frontier:
              model: my-frontier-model
              price: {input_per_m: 1.0, output_per_m: 2.0}
            """
        )
    )
    tiers = load_tiers(custom)
    assert tiers.cheap.model == "my-cheap-model"
    assert tiers.frontier.model == "my-frontier-model"


def test_missing_tiers_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_tiers(tmp_path / "nope.yaml")


def test_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.upstream_base_url == "https://api.openai.com/v1"
    assert settings.upstream_api_key is None
    assert settings.tiers_file is None
    assert settings.upstream_timeout_s > 0
