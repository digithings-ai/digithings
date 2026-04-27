"""User investment profile schemas.

Versioned Pydantic v2 models describing a user's investment posture:
risk tolerance, horizon, liquidity needs, base currency, tax jurisdiction,
ESG preferences, excluded sectors, experience level. Consumed by Atlas /
Hermes / Kairos to constrain idea generation and portfolio construction.

See ``digiquant/docs/profiles/README.md`` for the migration story.
"""

from __future__ import annotations

from digiquant.profiles.investment_profile import InvestmentProfile

__all__ = ["InvestmentProfile"]
