"""Settings and tier configuration.

Tiers (which upstream model to use per tier, plus list prices for cost
estimation) live in a YAML file; a packaged default ships with the package.
Everything else comes from the environment with the `LAYA_ROUTER_` prefix.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PriceConfig(BaseModel):
    """List prices in USD per 1M tokens (used only for cost estimation).

    Zero is valid: free-tier models (e.g. glm-4.5-flash) price at 0.
    """

    input_per_m: float = Field(ge=0)
    output_per_m: float = Field(ge=0)


class TierConfig(BaseModel):
    model: str
    price: PriceConfig


class TiersConfig(BaseModel):
    cheap: TierConfig
    frontier: TierConfig

    def model_for(self, tier: str) -> str:
        try:
            return getattr(self, tier).model
        except AttributeError:
            raise ValueError(f"unknown tier: {tier!r}") from None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LAYA_ROUTER_", env_file=".env")

    upstream_base_url: str = "https://api.openai.com/v1"
    # When None, the client's Authorization header is forwarded as-is.
    upstream_api_key: Optional[str] = None
    # When None, the packaged default tiers.yaml is used.
    tiers_file: Optional[Path] = None
    upstream_timeout_s: float = 120.0
    # Escalate to frontier when laya's answer_confidence falls below this.
    # 0 disables the gate. TODO(tune via backtest cost/quality curve).
    min_confidence: float = 0.55
    # JSONL decision log destination; None disables logging.
    decision_log: Optional[Path] = None
    # Per-client-IP request limit per minute; 0 disables the limit.
    rate_limit_rpm: int = 0


def default_tiers_file() -> Path:
    return Path(str(resources.files("laya_router").joinpath("tiers.yaml")))


def load_tiers(path: Optional[Path] = None) -> TiersConfig:
    """Load tier configuration from `path` (default: the packaged tiers.yaml)."""
    resolved = Path(path) if path is not None else default_tiers_file()
    if not resolved.is_file():
        raise FileNotFoundError(f"tiers file not found: {resolved}")
    return TiersConfig.model_validate(yaml.safe_load(resolved.read_text(encoding="utf-8")))
