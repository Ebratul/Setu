"""Risk thresholds, read from `config/risk.yaml` (SR-1). The tier engine has no numbers of its own;
change the YAML and the documented thresholds change with it."""

from decimal import Decimal
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "risk.yaml"


class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tier1_max_usd: Decimal = Field(gt=0)
    fraud_score_tier3_above: int = Field(ge=0, le=100)
    new_beneficiary_days: int = Field(gt=0)
    cooling_off_minutes: int = Field(gt=0)
    inline_tier2_actions: frozenset[str]


@lru_cache(maxsize=1)
def load_policy(path: Path = CONFIG_PATH) -> RiskPolicy:
    return RiskPolicy.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


# SR-1: a Tier 1 (auto + notice) release is at most this much; above it is Tier 3.
TIER1_MAX_USD = load_policy().tier1_max_usd
# SR-9: Tier 3 cooling-off window.
COOLING_OFF_MINUTES = load_policy().cooling_off_minutes
