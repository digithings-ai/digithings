"""Versioned Pydantic v2 schema for a user's asset preferences.

Companion to :class:`digiquant.profiles.investment_profile.InvestmentProfile`.
Split into a separate model because asset preferences (watchlists, exclusions)
mutate frequently while the underlying risk posture is stable — keeping them
apart simplifies cache invalidation and audit trails.

See ``digiquant/docs/profiles/README.md`` for the migration story.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _normalize_tickers(value: list[str]) -> list[str]:
    """Strip + upper-case + drop empties + de-duplicate (insertion-ordered)."""
    seen: dict[str, None] = {}
    for raw in value:
        if not isinstance(raw, str):
            raise TypeError(f"ticker entries must be str, got {type(raw)!r}")
        normalized = raw.strip().upper()
        if not normalized:
            continue
        seen.setdefault(normalized, None)
    return list(seen)


def _normalize_sectors(value: list[str]) -> list[str]:
    """Strip + lower-case + drop empties + de-duplicate (insertion-ordered)."""
    seen: dict[str, None] = {}
    for raw in value:
        if not isinstance(raw, str):
            raise TypeError(f"sector entries must be str, got {type(raw)!r}")
        normalized = raw.strip().lower()
        if not normalized:
            continue
        seen.setdefault(normalized, None)
    return list(seen)


class AssetPreferences(BaseModel):
    """User asset preferences (schema v1).

    Attributes
    ----------
    schema_version
        Monotonic schema version. Increment only on breaking changes.
    watchlists
        Named ticker baskets (e.g. ``{"core": ["SPY", "QQQ"], "thematic": ["NVDA"]}``).
        Each value is normalized to upper-case, de-duplicated, insertion-ordered.
    custom_universe
        Tickers the user wants Atlas to consider beyond the default watchlist.
        Same normalization as ``watchlists``.
    excluded_tickers
        Hard exclusions. Wins over inclusion on conflict — a ticker that
        appears in both a watchlist and ``excluded_tickers`` is dropped from
        the watchlist by the post-validation hook.
    excluded_sectors
        Sector-level exclusions (lower-cased, de-duplicated). Overlap with
        :attr:`InvestmentProfile.excluded_sectors` is allowed and intentional —
        the two have different update cadences.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    schema_version: int = Field(
        default=1,
        ge=1,
        description="Schema version; bump on breaking changes.",
    )
    watchlists: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Named ticker baskets, e.g. {'core': ['SPY', 'QQQ']}.",
    )
    custom_universe: list[str] = Field(
        default_factory=list,
        description="Additional tickers Atlas should consider.",
    )
    excluded_tickers: list[str] = Field(
        default_factory=list,
        description="Hard ticker exclusions; wins over inclusion on conflict.",
    )
    excluded_sectors: list[str] = Field(
        default_factory=list,
        description="Sector exclusions (lower-cased, de-duplicated).",
    )

    @field_validator("watchlists", mode="after")
    @classmethod
    def _normalize_watchlists(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for raw_name, tickers in value.items():
            name = raw_name.strip()
            if not name:
                raise ValueError("watchlist name must be non-empty after stripping")
            out[name] = _normalize_tickers(list(tickers))
        return out

    @field_validator("custom_universe", "excluded_tickers", mode="after")
    @classmethod
    def _normalize_ticker_list(cls, value: list[str]) -> list[str]:
        return _normalize_tickers(value)

    @field_validator("excluded_sectors", mode="after")
    @classmethod
    def _normalize_sector_list(cls, value: list[str]) -> list[str]:
        return _normalize_sectors(value)

    @model_validator(mode="after")
    def _exclusion_wins_over_inclusion(self) -> "AssetPreferences":
        """Drop excluded tickers from watchlists + custom_universe.

        Conflict resolution is silent (drop) rather than raising — most users
        edit lists incrementally and intermittent overlaps are expected. The
        post-validation pass is what makes the contract observable.
        """
        excluded = set(self.excluded_tickers)
        if not excluded:
            return self

        cleaned_watchlists = {
            name: [t for t in tickers if t not in excluded]
            for name, tickers in self.watchlists.items()
        }
        cleaned_universe = [t for t in self.custom_universe if t not in excluded]

        if cleaned_watchlists != self.watchlists or cleaned_universe != self.custom_universe:
            object.__setattr__(self, "watchlists", cleaned_watchlists)
            object.__setattr__(self, "custom_universe", cleaned_universe)
        return self
