"""User investment profile + asset preferences schemas.

Versioned Pydantic v2 models describing a user's investment posture
(risk tolerance, horizon, currency, jurisdiction, ESG, sector exclusions,
experience level) and per-user asset preferences (watchlists, custom
universe, ticker / sector exclusions). Consumed by Atlas / Hermes /
Kairos to constrain idea generation and portfolio construction.

See ``digiquant/docs/profiles/README.md`` for the migration story.
"""

from __future__ import annotations

from digiquant.profiles.asset_preferences import AssetPreferences
from digiquant.profiles.investment_profile import InvestmentProfile

__all__ = ["AssetPreferences", "InvestmentProfile"]
