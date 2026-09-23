"""Pydantic v2 models for the digifetch x Gloomberb data layer (#4069, #4110).

This package is the data layer for the `digifetch_*` tools described in
``docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`` §5, expanded
past the original 13-tool contract by #4110 phase 1 (econ calendar/series,
yield curve, CDS, research search, congress trades, transcripts). It is
approach (c): a Python HTTP client over ``https://api.gloom.sh`` built on the
digifetch transport engine.

Layout:

* :mod:`digiquant.data.gloomberb.models` - input/output models, the shared
  ``DigifetchEnvelope[T]``/``DigifetchError`` contract, and the §5.2
  resolution x range caps.
* :mod:`digiquant.data.gloomberb.normalizers` - ported §5.4 normalizers
  (currency units, interval tokens, exchange-timezone dates, malformed
  intraday, day-range reconciliation) and the §5.3 freshness union.
* :mod:`digiquant.data.gloomberb.client` - the HTTP client (endpoints, error
  mapping, cache, circuit breaker, kill switch, session cookie).

Wire payloads are camelCase; models expose snake_case attributes via a
``to_camel`` alias generator. Unknown wire fields are preserved
(``extra="allow"``) so an undocumented upstream addition is not silently
dropped. Input models forbid unknown fields so a typo fails loudly.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar  # score:allow untyped any — wire JSON

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.alias_generators import to_camel

__all__ = [
    "SOURCE",
    "PROVIDER_ID",
    "PREVIEW_ACCESS_WARNING",
    "Resolution",
    "Range",
    "RANGE_ORDER",
    "RESOLUTION_MAX_RANGE",
    "INTRADAY_RESOLUTIONS",
    "RESOLUTION_MAX_RANGE_LABELS",
    "EPOCH_SECONDS_CEILING",
    "Symbol",
    "DigifetchError",
    "DigifetchEnvelope",
    # inputs
    "QuoteInput",
    "QuotesBatchInput",
    "PriceHistoryInput",
    "TickerFinancialsInput",
    "OptionsChainInput",
    "SecFilingsInput",
    "HoldersInput",
    "AnalystResearchInput",
    "CorporateActionsInput",
    "EarningsCalendarInput",
    "ExchangeRateInput",
    "SearchInput",
    "NewsInput",
    "EconCalendarInput",
    "EconSeriesInput",
    "YieldCurveInput",
    "CdsInput",
    "ResearchSearchInput",
    "CongressTradesInput",
    "TranscriptsInput",
    # coverage expansion (#4110 phase 2)
    "StatementsInput",
    "TickerTweetsInput",
    "TweetSearchInput",
    "VenuesInput",
    # coverage expansion (#4110 phase 4a)
    "SavedSearchesInput",
    "ScreenerInput",
    "ThirteenFFundsInput",
    "ThirteenFHoldingsInput",
    # coverage expansion (#4110 phase 3)
    "ShillerInput",
    "ProxyStatementsInput",
    "FilingEventsInput",
    "RiskReportsInput",
    "ShortInterestInput",
    "EquityDiagnosticInput",
    # wire/output payload models
    "Quote",
    "QuoteBatchItem",
    "PriceBar",
    "PriceHistoryMetadata",
    "PriceHistoryResult",
    "QuoteResult",
    "QuotesBatchResult",
    "CompanyProfile",
    "Fundamentals",
    "FinancialStatement",
    "StatementHistory",
    "TickerFinancials",
    "TickerFinancialsResult",
    "OptionContract",
    "OptionsChain",
    "OptionsChainResult",
    "SecFiling",
    "SecFilingDocument",
    "SecFilingsResult",
    "Holder",
    "HoldersResult",
    "AnalystPriceTarget",
    "AnalystAction",
    "AnalystResearchResult",
    "CorporateAction",
    "CorporateActionsResult",
    "EarningsEvent",
    "EarningsCalendarResult",
    "ExchangeRateResult",
    "InstrumentSearchResult",
    "SearchResult",
    "NewsScores",
    "NewsFlags",
    "NewsTickerLink",
    "NewsStoryItem",
    "NewsItem",
    "NewsResult",
    # coverage expansion (#4110 phase 1)
    "EconCalendarEvent",
    "EconCalendarResult",
    "EconSeriesObservation",
    "EconSeriesInfo",
    "EconSeriesResult",
    "YieldCurvePoint",
    "YieldCurveResult",
    "CdsTrade",
    "CdsResult",
    "ResearchHit",
    "ResearchSearchPagination",
    "ResearchSearchResult",
    "CongressTrade",
    "CongressTradesResult",
    "Transcript",
    "TranscriptId",
    "TranscriptsResult",
    # coverage expansion (#4110 phase 2)
    "StatementRow",
    "StatementsResult",
    # coverage expansion (#4110 phase 4a)
    "SavedSearch",
    "SavedSearchesResult",
    "TweetAuthor",
    "TweetMetrics",
    "Tweet",
    "TweetsResult",
    "Venue",
    "VenuesResult",
    "ScreenerRow",
    "ScreenerResult",
    "Fund13F",
    "TopFund13F",
    "TickerInfo13F",
    "FundHolders13F",
    "Funds13FResult",
    "Filing13F",
    "Holding13F",
    "Holdings13FResult",
    # coverage expansion (#4110 phase 3)
    "CompanyRef",
    "ShillerObservation",
    "ShillerResult",
    "ExecutivePay",
    "ProxySummary",
    "HighlightFigure",
    "ProxyStatement",
    "ProxyStatementsResult",
    "FilingPerson",
    "FilingEvent",
    "FilingEventsResult",
    "RiskFactor",
    "RiskNote",
    "RiskRemoved",
    "RiskReworded",
    "RiskDiff",
    "RiskNotes",
    "RiskSummary",
    "RiskReport",
    "RiskReportsResult",
    "ShortInterestPoint",
    "ShortInterestResult",
    "EquityDiagnosticPending",
    "EquityDiagnosticFinding",
    "EquityDiagnosticCoverage",
    "EquityDiagnosticEvidence",
    "EquityDiagnosticReport",
    "EquityDiagnosticResult",
    # concrete envelopes
    "QuoteEnvelope",
    "QuotesBatchEnvelope",
    "PriceHistoryEnvelope",
    "TickerFinancialsEnvelope",
    "OptionsChainEnvelope",
    "SecFilingsEnvelope",
    "HoldersEnvelope",
    "AnalystResearchEnvelope",
    "CorporateActionsEnvelope",
    "EarningsCalendarEnvelope",
    "ExchangeRateEnvelope",
    "SearchEnvelope",
    "NewsEnvelope",
    "EconCalendarEnvelope",
    "EconSeriesEnvelope",
    "YieldCurveEnvelope",
    "CdsEnvelope",
    "ResearchSearchEnvelope",
    "CongressTradesEnvelope",
    "TranscriptsEnvelope",
    "StatementsEnvelope",
    "TweetsEnvelope",
    "VenuesEnvelope",
    # coverage expansion (#4110 phase 4a)
    "SavedSearchesEnvelope",
    "ScreenerEnvelope",
    "Funds13FEnvelope",
    "Holdings13FEnvelope",
    "ShillerEnvelope",
    "ProxyStatementsEnvelope",
    "FilingEventsEnvelope",
    "RiskReportsEnvelope",
    "ShortInterestEnvelope",
    "EquityDiagnosticEnvelope",
]

SOURCE: Literal["gloomberb"] = "gloomberb"
PROVIDER_ID = "gloomberb-cloud"

# §5.2 resolution x range caps. Resolution is the chart-resolution enum
# (1m...1mo); Range is the TimeRange enum (1D...5Y, ALL).
Resolution = Literal["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]
Range = Literal["1D", "1W", "1M", "3M", "6M", "1Y", "5Y", "ALL"]

RANGE_ORDER: tuple[str, ...] = ("1D", "1W", "1M", "3M", "6M", "1Y", "5Y", "ALL")

# Contract caps from §5.2. `1wk -> 5Y` is the recorded deviation from the
# issue's all-time promise: a live anonymous probe returned 29 weekly bars for
# rangeKey=ALL, and a direct client has no Yahoo fallback.
RESOLUTION_MAX_RANGE: dict[str, str] = {
    "1m": "1W",
    "5m": "1W",
    "15m": "1M",
    "30m": "6M",
    "1h": "3M",
    "1d": "5Y",
    "1wk": "5Y",
    "1mo": "ALL",
}

RESOLUTION_MAX_RANGE_LABELS: dict[str, str] = {
    "1W": "1 week",
    "1M": "1 month",
    "3M": "3 months",
    "6M": "6 months",
    "1Y": "1 year",
    "5Y": "5 years",
    "ALL": "all-time",
}

# Intraday resolutions share the chart-resolution vocabulary; 45m and 1h are
# accepted by the upstream interval mapper but not part of this contract.
INTRADAY_RESOLUTIONS: frozenset[str] = frozenset({"1m", "5m", "15m", "30m", "45m", "1h"})

# §5.2: the contract default range is 5 years for 1d. Any other resolution
# must state its range explicitly - the validator never clamps silently.
DEFAULT_RANGE: Range = "5Y"

# Any epoch value at/above this ceiling is milliseconds, not seconds (10**11
# seconds is year ~5138; today's millisecond timestamps are ~10**12+).
EPOCH_SECONDS_CEILING = 100_000_000_000

# Strict ISO calendar date (`YYYY-MM-DD`). Shared by the 13F date fields and
# the #4100 price-history window; a bare pydantic `date` parse is deliberately
# not trusted, because it also coerces numeric timestamps (1420070400.0 ->
# 2015-01-01) and midnight datetime strings.
_ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

Symbol = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
CurrencyCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=3,
        max_length=3,
        pattern=r"^[A-Za-z]{3}$",
    ),
]
ErrorCode = Literal[
    "auth_required",
    "pro_required",
    "not_found",
    "rate_limited",
    "upstream_error",
    "invalid_input",
]

# Envelope warning appended when the equity diagnostic serves a preview report
# (`access == "preview"`) to a free session. A stable, machine-matchable marker;
# `data.report.access` stays the canonical passthrough field (#4110 phase 5).
PREVIEW_ACCESS_WARNING = "preview access: report is a free-tier preview (access=preview)"


class _CamelModel(BaseModel):
    """Base for wire-facing models: camelCase aliases, extras preserved."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
    )


class _InputModel(BaseModel):
    """Base for tool inputs: camelCase aliases, unknown fields rejected."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


# ---------------------------------------------------------------------------
# Shared envelope / error contract (§5.3)
# ---------------------------------------------------------------------------


class DigifetchError(_CamelModel):
    """Typed failure carried in the envelope ``data`` slot.

    The code vocabulary is the §5.3 table. ``retryable`` mirrors the table's
    explicit annotations: only ``upstream_error`` from a wire 5xx/timeout is
    retryable; the client itself never retries 401/404/429.
    """

    code: ErrorCode
    message: str
    retryable: bool = False


DataT = TypeVar("DataT")


class DigifetchEnvelope(_CamelModel, Generic[DataT]):
    """The one shared envelope, generic over the tool payload (§5.3).

    ``data`` is either the success payload or a typed :class:`DigifetchError`;
    tools never raise to the transport.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="allow",
        frozen=True,
    )

    source: Literal["gloomberb"] = "gloomberb"
    provider_id: str = PROVIDER_ID
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    stale: bool = False
    delay_note: str | None = None
    warnings: list[str] = Field(default_factory=list)
    data: DataT | DigifetchError


# ---------------------------------------------------------------------------
# Input models (one per tool, §5.1)
# ---------------------------------------------------------------------------


class QuoteInput(_InputModel):
    symbol: Symbol
    exchange: str | None = None


class QuotesBatchInput(_InputModel):
    symbols: list[Symbol] = Field(min_length=1, max_length=20)


class PriceHistoryInput(_InputModel):
    """One chart-history read (§5.2 caps, plus the #4100 date window).

    ``range`` is the contract dimension: capped per resolution and rejected
    (never clamped) outside the table. ``start_date``/``end_date`` are the
    #4100 widening escape hatch: an explicit ISO window is **mutually
    exclusive** with ``range`` and bypasses the caps — the client maps it to
    the probe-verified ``rangeKey=ALL`` + ``startDate``/``endDate`` upstream
    combination, which serves weekly bars beyond Cloud's declared 5Y (live:
    610 bars back to 2015-01-05). Only the weekly (``1wk``) window path is
    probe-verified; intraday windows are allowed but upstream-unverified.
    Either end may be omitted (open-ended window); the caller's dates bound
    the read instead of a range key.
    """

    symbol: Symbol
    resolution: Resolution
    # None means "contract default": resolved to 5Y for 1d only. Never clamped.
    range: Range | None = None
    start_date: date | None = None
    end_date: date | None = None
    exchange: str | None = None

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def _only_strict_iso_dates(cls, value: object) -> object:
        """Accept only ``YYYY-MM-DD`` strings (or a real ``date``).

        Pydantic's bare ``date`` parse would also coerce numeric timestamps
        (``1420070400.0`` -> 2015-01-01) and midnight datetime strings, which
        would silently reinterpret a raw-dict caller's window; this gate keeps
        the contract strict (#4100 review F3).
        """
        if value is None:
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, str):
            candidate = value.strip()
            if re.fullmatch(_ISO_DATE_PATTERN, candidate):
                return candidate
        raise ValueError(
            f"must be an ISO YYYY-MM-DD date string (or date); got {type(value).__name__} {value!r}"
        )

    @model_validator(mode="after")
    def _enforce_resolution_range_caps(self) -> PriceHistoryInput:
        if self.start_date is not None or self.end_date is not None:
            if self.range is not None:
                raise ValueError(
                    "start_date/end_date and range are mutually exclusive: an "
                    "explicit date window replaces the range key (the client "
                    "sends rangeKey=ALL with it)"
                )
            if (
                self.start_date is not None
                and self.end_date is not None
                and self.start_date > self.end_date
            ):
                raise ValueError(
                    f"start_date must be on or before end_date "
                    f"(got {self.start_date.isoformat()} > {self.end_date.isoformat()})"
                )
            return self
        cap = RESOLUTION_MAX_RANGE[self.resolution]
        if self.range is None:
            if self.resolution != "1d":
                raise ValueError(
                    f"range is required for resolution {self.resolution!r} "
                    f"(contract max {RESOLUTION_MAX_RANGE_LABELS[cap]}); "
                    "the client never clamps silently"
                )
            self.range = DEFAULT_RANGE
            return self
        if RANGE_ORDER.index(self.range) > RANGE_ORDER.index(cap):
            raise ValueError(
                f"resolution {self.resolution!r} caps range at "
                f"{RESOLUTION_MAX_RANGE_LABELS[cap]}; {self.range!r} is outside "
                "the contract (requests are rejected, never trimmed)"
            )
        return self


class TickerFinancialsInput(_InputModel):
    symbol: Symbol
    exchange: str | None = None
    extended_statements: bool = False


class OptionsChainInput(_InputModel):
    symbol: Symbol
    exchange: str | None = None
    # Upstream is epoch seconds (`expirationDate`), not milliseconds. Values at
    # or above the seconds ceiling are millisecond timestamps and are rejected
    # with invalid_input rather than silently reinterpreted.
    expiration: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _reject_millisecond_expiration(self) -> OptionsChainInput:
        if self.expiration is not None and self.expiration >= EPOCH_SECONDS_CEILING:
            raise ValueError(
                "expiration must be epoch seconds, not milliseconds "
                f"(got {self.expiration}); multiply seconds by 1000 only if you "
                "meant milliseconds"
            )
        return self


class SecFilingsInput(_InputModel):
    ticker: Symbol
    what: Literal["filings", "documents", "content"] = "filings"
    # One filings page; 1-40 bounds a single enrichment read (default 15).
    count: int = Field(default=15, ge=1, le=40)
    cik: str | None = None
    accession: str | None = None
    form: str | None = None

    @model_validator(mode="after")
    def _require_filing_identity_for_documents(self) -> SecFilingsInput:
        if self.what in ("documents", "content") and not (self.cik and self.accession):
            raise ValueError(
                f"what={self.what!r} requires both cik and accession "
                "(from an earlier filings lookup)"
            )
        return self


class HoldersInput(_InputModel):
    symbol: Symbol
    owner_type: Literal["all", "insider", "institution", "fund", "direct"] = "all"


class AnalystResearchInput(_InputModel):
    symbol: Symbol
    # Bounded so one enrichment read cannot fan out unboundedly.
    limit: int = Field(default=20, ge=1, le=100)


class CorporateActionsInput(_InputModel):
    symbol: Symbol


class EarningsCalendarInput(_InputModel):
    symbols: list[Symbol] = Field(min_length=1, max_length=20)
    horizon_days: int = Field(default=90, ge=1)


class ExchangeRateInput(_InputModel):
    from_currency: CurrencyCode
    to_currency: CurrencyCode = "USD"

    @model_validator(mode="after")
    def _only_usd_target_supported(self) -> ExchangeRateInput:
        if self.to_currency != "USD":
            raise ValueError(
                "the Cloud exchange-rate route is USD-based only; "
                f"to_currency must be 'USD', got {self.to_currency!r}"
            )
        return self


class SearchInput(_InputModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    # Spec §5.1: the Cloud client wrapper caps at 10. Values above the cap are
    # accepted, clamped to 10 client-side, and flagged with `limit_clamped` in
    # the result (never rejected).
    limit: int = Field(default=10, ge=1)


class NewsInput(_InputModel):
    feed: Literal["latest", "top", "breaking", "ticker", "sector", "topic"] = "latest"
    ticker: Symbol | None = None
    story_id: str | None = None
    # Bounded so one enrichment read cannot fan out unboundedly.
    limit: int = Field(default=20, ge=1, le=100)


# ---------------------------------------------------------------------------
# Coverage-expansion inputs (#4110 phase 1)
# ---------------------------------------------------------------------------


class EconCalendarInput(_InputModel):
    """The Cloud econ-calendar route takes no parameters.

    The upstream ignores ``limit`` (live probe: a fixed ~105-row window), so
    the contract deliberately exposes no page-size knob.
    """


class EconSeriesInput(_InputModel):
    series_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    # FRED-style observation pages can be long; bounded at one page worth.
    limit: int = Field(default=100, ge=1, le=1000)
    sort_order: Literal["asc", "desc"] = "desc"


class YieldCurveInput(_InputModel):
    """The Cloud yield-curve route takes no parameters (maturities are fixed)."""


class CdsInput(_InputModel):
    issuer: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    # The Cloud route answers HTTP 400 outside 1..90; the input model rejects it
    # first so the caller gets a typed invalid_input without a request.
    days: int = Field(default=30, ge=1, le=90)
    limit: int = Field(default=100, ge=1, le=200)


class ResearchSearchInput(_InputModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    limit: int = Field(default=10, ge=1, le=100)
    # First page by default; bounded so one read cannot walk an unbounded cursor.
    offset: int = Field(default=0, ge=0, le=10_000)


class CongressTradesInput(_InputModel):
    year: int | None = Field(default=None, ge=1970, le=2100)
    limit: int = Field(default=50, ge=1, le=200)


#: One transcript id from a `gloomberb_get_transcripts` list row
#: (`/cloud/transcripts/{id}`; probe-pending shape, so the bound is generous).
TranscriptId = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
]


class TranscriptsInput(_InputModel):
    """List one ticker's calls, or fetch one call by id (exactly one target).

    `ticker` selects ``GET /cloud/transcripts``; `transcript_id` (from a list
    row) selects ``GET /cloud/transcripts/{id}``. Both routes are session-gated
    and require a Gloomberb Pro plan.
    """

    ticker: Symbol | None = None
    transcript_id: TranscriptId | None = None
    limit: int = Field(default=20, ge=1, le=100)

    @model_validator(mode="after")
    def _exactly_one_target(self) -> "TranscriptsInput":
        if (self.ticker is None) == (self.transcript_id is None):
            raise ValueError("provide exactly one of ticker or transcript_id")
        return self


# ---------------------------------------------------------------------------
# Coverage-expansion inputs (#4110 phase 2)
# ---------------------------------------------------------------------------


class StatementsInput(_InputModel):
    symbol: Symbol
    period: Literal["annual", "quarterly", "both"] = "annual"
    exchange: str | None = None


class TickerTweetsInput(_InputModel):
    ticker: Symbol
    # The upstream answers its cached window and echoes `limit` without
    # shrinking the list (live-verified); the client slices to this bound and
    # flags `truncated`.
    limit: int = Field(default=50, ge=1, le=200)
    hours: int | None = Field(default=None, ge=1, le=720)
    include_replies: bool = False


class TweetSearchInput(_InputModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    query_type: Literal["Latest", "Top"] = "Latest"
    limit: int = Field(default=50, ge=1, le=200)
    hours: int | None = Field(default=None, ge=1, le=720)


class VenuesInput(_InputModel):
    """The Cloud venues route takes no parameters."""


class SavedSearchesInput(_InputModel):
    """The Cloud saved-searches route takes no parameters."""


class ScreenerInput(_InputModel):
    category: Literal["gainers", "losers", "most-active"]
    count: int = Field(default=25, ge=1, le=50)
    mode: Literal["cache-first", "refresh"] = "cache-first"


Cusip = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=12)]
# ISO date only; the upstream answers 500/400 for malformed values such as
# 2026-6-1, so the contract rejects them before any request.
DateIso = Annotated[str, StringConstraints(strip_whitespace=True, pattern=_ISO_DATE_PATTERN)]
# Live-verified 13F quarter token: 2026Q2 (a dashed 2026-Q2 is rejected upstream).
Quarter13F = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=6,
        max_length=6,
        pattern=r"^\d{4}[Qq][1-4]$",
    ),
]


class ThirteenFFundsInput(_InputModel):
    """The 13F funds surface, discriminated by ``what``.

    search -> ``name`` (query); top -> ``quarter``; tickers -> ``tickers``;
    holders -> ``cusip`` + ``period_of_report``. The route family is anonymous
    (live-verified for search/top/tickers).
    """

    what: Literal["search", "top", "tickers", "holders"]
    query: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
        | None
    ) = None
    quarter: Quarter13F | None = None
    tickers: list[Symbol] = Field(default_factory=list, max_length=50)
    cusip: Cusip | None = None
    period_of_report: str | None = None
    limit: int = Field(default=25, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10_000)

    @model_validator(mode="after")
    def _require_fields_for_what(self) -> ThirteenFFundsInput:
        if self.what == "search" and not self.query:
            raise ValueError("what='search' requires query")
        if self.what == "top" and not self.quarter:
            raise ValueError("what='top' requires quarter (YYYYQn, e.g. 2026Q2)")
        if self.what == "tickers" and not self.tickers:
            raise ValueError("what='tickers' requires 1-50 tickers")
        if self.what == "holders" and not (self.cusip and self.period_of_report):
            raise ValueError("what='holders' requires both cusip and period_of_report")
        return self


class ThirteenFHoldingsInput(_InputModel):
    """The 13F filings/forms/holdings surface, discriminated by ``what``.

    filings -> ``from_date`` + ``to_date`` (ISO ``YYYY-MM-DD``); forms ->
    ``cik``; form -> ``cik`` + ``accession_number`` (dashed or undashed 18
    digits — the client normalizes to the SEC's ``XXXXXXXXXX-YY-ZZZZZZ``
    form). Anonymous (live-verified).
    """

    what: Literal["filings", "forms", "form"]
    cik: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10)] | None
    ) = None
    accession_number: (
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)] | None
    ) = None
    from_date: DateIso | None = None
    to_date: DateIso | None = None
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("cik")
    @classmethod
    def _normalize_cik(cls, value: str | None) -> str | None:
        """Zero-pad a bare CIK to the SEC's 10-digit form (live-verified)."""
        if value is None:
            return None
        digits = value.strip()
        if not digits.isdigit():
            raise ValueError("cik must be digits only")
        return digits.zfill(10)

    @field_validator("accession_number")
    @classmethod
    def _normalize_accession_number(cls, value: str | None) -> str | None:
        """Normalize an 18-digit accession to the SEC's dashed form.

        The upstream accepts the undashed form but the dashed form is the
        canonical wire value; an undashed value passed through unchanged
        silently returns an empty result set (live-verified), so it is
        normalized here and anything else is rejected.
        """
        if value is None:
            return None
        digits = value.replace("-", "")
        if len(digits) != 18 or not digits.isdigit():
            raise ValueError(
                f"accession_number must be 18 digits (dashed or undashed), got {value!r}"
            )
        return f"{digits[:10]}-{digits[10:12]}-{digits[12:]}"

    @model_validator(mode="after")
    def _require_fields_for_what(self) -> ThirteenFHoldingsInput:
        if self.what == "filings" and not (self.from_date and self.to_date):
            raise ValueError("what='filings' requires both from_date and to_date")
        if self.what in ("forms", "form") and not self.cik:
            raise ValueError(f"what={self.what!r} requires cik")
        if self.what == "form" and not self.accession_number:
            raise ValueError("what='form' requires accession_number")
        return self


# ---------------------------------------------------------------------------
# Coverage-expansion inputs (#4110 phase 3)
# ---------------------------------------------------------------------------


class ShillerInput(_InputModel):
    # Return the most recent N monthly observations (the full series is ~1869
    # rows back to 1871); the client slices the tail and flags truncation.
    limit: int = Field(default=240, ge=1, le=2000)


class ProxyStatementsInput(_InputModel):
    """Gloom Cloud's open proxy-statement reads (executive compensation).

    ``year`` is the **proxy** year (the filing year), not the fiscal year:
    AAPL's 2026 proxy reports fiscal 2025, and asking for the fiscal year 404s
    (live-verified).
    """

    what: Literal["list", "statement"] = "list"
    ticker: Symbol
    year: int | None = Field(default=None, ge=1990, le=2100)

    @model_validator(mode="after")
    def _statement_requires_year(self) -> ProxyStatementsInput:
        if self.what == "statement" and self.year is None:
            raise ValueError("what='statement' requires year (the proxy year)")
        return self


class FilingEventsInput(_InputModel):
    ticker: Symbol
    limit: int = Field(default=20, ge=1, le=200)


class RiskReportsInput(_InputModel):
    """Annual 10-K risk-factor extraction, diffed against the prior year."""

    what: Literal["list", "report"] = "list"
    ticker: Symbol
    year: int | None = Field(default=None, ge=1990, le=2100)

    @model_validator(mode="after")
    def _report_requires_year(self) -> RiskReportsInput:
        if self.what == "report" and self.year is None:
            raise ValueError("what='report' requires year (the report year)")
        return self


class ShortInterestInput(_InputModel):
    symbol: Symbol
    # Live-verified upstream behavior: 1→24 points, 5→120, 10→209; 0/11/99
    # silently fall back to the 3-year window, so the contract bounds it here.
    years: int = Field(default=3, ge=1, le=10)


class EquityDiagnosticInput(_InputModel):
    """On-demand AI evidence review for one listing (cookie-gated).

    ``refresh`` asks the server to regenerate; a free session only ever gets
    ``access="preview"`` results. The first call for a symbol answers HTTP 202
    with a ``generating`` pending payload and a retry hint.
    """

    symbol: Symbol
    exchange: str | None = None
    mode: Literal["cache-first", "refresh"] = "cache-first"


# ---------------------------------------------------------------------------
# Payload models (wire-facing)
# ---------------------------------------------------------------------------


class Quote(_CamelModel):
    """A quote observation; the long tail of wire fields is preserved as extras."""

    symbol: str
    price: float
    currency: str = ""
    change: float = 0.0
    change_percent: float = 0.0
    previous_close: float | None = None
    regular_close: float | None = None
    regular_close_session_date: str | None = None
    change_session_date: str | None = None
    # Explicit aliases: `to_camel("high52w")` would produce "high52W" (digit
    # followed by a lowercase letter defeats pydantic's identity shortcut).
    high52w: float | None = Field(default=None, alias="high52w")
    low52w: float | None = Field(default=None, alias="low52w")
    market_cap: float | None = None
    volume: float | None = None
    name: str | None = None
    last_updated: float | None = None
    stale: bool | None = None
    exchange_name: str | None = None
    full_exchange_name: str | None = None
    listing_exchange_name: str | None = None
    listing_exchange_full_name: str | None = None
    market_state: str | None = None
    session_confidence: str | None = None
    pre_market_price: float | None = None
    pre_market_change: float | None = None
    pre_market_change_percent: float | None = None
    post_market_price: float | None = None
    post_market_change: float | None = None
    post_market_change_percent: float | None = None
    bid: float | None = None
    ask: float | None = None
    bid_size: float | None = None
    ask_size: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    mark: float | None = None
    last_trade_price: float | None = None
    last_trade_time: float | None = None
    provider_id: str | None = None
    instrument_type: str | None = None
    data_source: str | None = None


class QuoteBatchItem(_CamelModel):
    symbol: str
    exchange: str = ""
    status: str
    quote: Quote | None = None
    reason_code: str | None = None


class QuoteResult(_CamelModel):
    quote: Quote | None = None


class QuotesBatchResult(_CamelModel):
    quotes: list[QuoteBatchItem] = Field(default_factory=list)


class PriceBar(_CamelModel):
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float
    volume: float | None = None


class PriceHistoryMetadata(_CamelModel):
    symbol: str
    exchange: str = ""
    resolution: str
    range: str
    bar_count: int = 0
    timezone: str | None = None
    currency: str | None = None
    upstream_provider: str | None = None


class PriceHistoryResult(_CamelModel):
    bars: list[PriceBar] = Field(default_factory=list)
    metadata: PriceHistoryMetadata


class CompanyProfile(_CamelModel):
    description: str | None = None
    sector: str | None = None
    industry: str | None = None


class Fundamentals(_CamelModel):
    """Common fundamentals subset; unlisted wire fields are kept as extras."""

    source: str | None = None
    fetched_at: str | None = None
    stale: bool | None = None
    financial_currency: str | None = None
    market_cap: float | None = None
    market_cap_currency: str | None = None
    trailing_pe: float | None = None
    forward_pe: float | None = None
    peg_ratio: float | None = None
    enterprise_value: float | None = None
    enterprise_to_revenue: float | None = None
    operating_cash_flow: float | None = None
    free_cash_flow: float | None = None
    dividend_yield: float | None = None
    revenue: float | None = None
    net_income: float | None = None
    eps: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    revenue_growth: float | None = None
    shares_outstanding: float | None = None


class FinancialStatement(_CamelModel):
    """Statement row with the common fields typed; the rest preserved as extras."""

    date: str | None = None
    currency: str | None = None
    available_at: str | None = None
    eps: float | None = None
    total_revenue: float | None = None
    net_income: float | None = None
    ebitda: float | None = None
    free_cash_flow: float | None = None
    total_assets: float | None = None
    total_liabilities: float | None = None
    total_equity: float | None = None


class StatementHistory(_CamelModel):
    mode: str | None = None
    source: str | None = None
    status: str | None = None
    fetched_at: str | None = None
    reason: str | None = None


class TickerFinancials(_CamelModel):
    quote: Quote | None = None
    financial_currency: str | None = None
    statement_history: StatementHistory | None = None
    profile: CompanyProfile | None = None
    fundamentals: Fundamentals | None = None
    annual_statements: list[FinancialStatement] = Field(default_factory=list)
    quarterly_statements: list[FinancialStatement] = Field(default_factory=list)
    price_history: list[PriceBar] = Field(default_factory=list)


class TickerFinancialsResult(_CamelModel):
    financials: TickerFinancials


class OptionContract(_CamelModel):
    """One option leg. ``side`` normalizes the wire ``calls``/``puts`` arrays."""

    contract_symbol: str
    side: Literal["call", "put"]
    strike: float
    currency: str = ""
    last_price: float = 0.0
    change: float = 0.0
    percent_change: float = 0.0
    volume: float | None = None
    open_interest: float | None = None
    bid: float = 0.0
    ask: float = 0.0
    implied_volatility: float = 0.0
    in_the_money: bool = False
    # Epoch seconds upstream, matching OptionsChainInput.expiration.
    expiration: float | None = None
    last_trade_date: float | None = None
    last_updated: float | None = None


class OptionsChain(_CamelModel):
    underlying_symbol: str
    expiration_dates: list[float] = Field(default_factory=list)
    calls: list[OptionContract] = Field(default_factory=list)
    puts: list[OptionContract] = Field(default_factory=list)
    provider_id: str | None = None
    data_source: str | None = None
    feed: str | None = None
    delay_minutes: float | None = None
    realtime_eligible: bool | None = None
    as_of: str | None = None


class OptionsChainResult(_CamelModel):
    chain: OptionsChain


class SecFiling(_CamelModel):
    accession_number: str
    form: str
    filing_date: str
    accepted_at: str | None = None
    accepted_at_raw: str | None = None
    primary_document: str | None = None
    primary_doc_description: str | None = None
    items: str | None = None
    cik: str
    company_name: str | None = None
    filing_url: str
    primary_document_url: str | None = None


class SecFilingDocument(_CamelModel):
    sequence: str | None = None
    type: str
    description: str | None = None
    document: str
    url: str
    size: str | None = None
    is_primary: bool = False


class SecFilingsResult(_CamelModel):
    """One tool, ``what`` discriminator: exactly one slot is populated."""

    filings: list[SecFiling] | None = None
    documents: list[SecFilingDocument] | None = None
    content: str | None = None


class Holder(_CamelModel):
    provider_id: str | None = None
    owner_type: str
    name: str
    report_date: str | None = None
    shares: float | None = None
    value: float | None = None
    percent_held: float | None = None
    change_shares: float | None = None
    change_percent: float | None = None


class HoldersResult(_CamelModel):
    holders: list[Holder] = Field(default_factory=list)


class AnalystPriceTarget(_CamelModel):
    high: float | None = None
    median: float | None = None
    low: float | None = None
    average: float | None = None
    current: float | None = None
    currency: str | None = None


class AnalystAction(_CamelModel):
    date: str | None = None
    firm: str
    action: str | None = None
    current: str | None = None
    prior: str | None = None
    current_price_target: float | None = None
    prior_price_target: float | None = None


class AnalystResearchResult(_CamelModel):
    recommendation: float | None = None
    price_target: AnalystPriceTarget | None = None
    actions: list[AnalystAction] = Field(default_factory=list)


class CorporateAction(_CamelModel):
    """Flattened dividend/split/earnings record with a ``kind`` discriminator."""

    kind: Literal["dividend", "split", "earnings"]
    date: str
    amount: float | None = None
    description: str | None = None
    ratio: float | None = None
    from_factor: float | None = None
    to_factor: float | None = None
    date_type: str | None = None
    currency: str | None = None
    time: str | None = None
    eps_estimate: float | None = None
    eps_actual: float | None = None
    difference: float | None = None
    surprise_percent: float | None = None


class CorporateActionsResult(_CamelModel):
    actions: list[CorporateAction] = Field(default_factory=list)


class EarningsEvent(_CamelModel):
    symbol: str
    name: str | None = None
    earnings_date: date
    eps_estimate: float | None = None
    eps_actual: float | None = None
    timing: str = ""
    is_date_estimate: bool | None = None


class EarningsCalendarResult(_CamelModel):
    events: list[EarningsEvent] = Field(default_factory=list)


class ExchangeRateResult(_CamelModel):
    rate: float
    as_of: str | None = None
    stale: bool = False
    delay_note: str | None = None


class InstrumentSearchResult(_CamelModel):
    provider_id: str = ""
    symbol: str
    name: str = ""
    exchange: str = ""
    type: str = ""
    currency: str | None = None
    primary_exchange: str | None = None


class SearchResult(_CamelModel):
    results: list[InstrumentSearchResult] = Field(default_factory=list)
    limit_clamped: bool = False


class NewsScores(_CamelModel):
    importance: float | None = None
    urgency: float | None = None
    market_impact: float | None = None
    novelty: float | None = None
    confidence: float | None = None


class NewsFlags(_CamelModel):
    breaking: bool | None = None
    developing: bool | None = None
    stale: bool | None = None


class NewsTickerLink(_CamelModel):
    symbol: str
    exchange: str | None = None
    canonical_ticker: str | None = None
    relation_type: str | None = None
    display_tier: str | None = None
    confidence: float | None = None
    relevance_score: float | None = None
    impact_score: float | None = None
    sentiment: str | None = None


class NewsStoryItem(_CamelModel):
    id: str
    source_key: str = ""
    source_name: str = ""
    title: str
    summary: str | None = None
    url: str = ""
    published_at: str | None = None
    has_article_text: bool | None = None


class NewsItem(_CamelModel):
    id: str
    headline: str
    summary: str = ""
    topic: str | None = None
    topics: list[str] = Field(default_factory=list)
    category: str | None = None
    sentiment: str | None = None
    sectors: list[str] = Field(default_factory=list)
    first_published_at: str | None = None
    last_published_at: str | None = None
    first_seen_at: str | None = None
    last_seen_at: str | None = None
    primary_url: str = ""
    primary_source: str = ""
    source_count: int = 0
    scores: NewsScores | None = None
    flags: NewsFlags | None = None
    ticker_links: list[NewsTickerLink] = Field(default_factory=list)
    items: list[NewsStoryItem] = Field(default_factory=list)


class NewsResult(_CamelModel):
    items: list[NewsItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Coverage-expansion payloads (#4110 phase 1)
# ---------------------------------------------------------------------------


class EconCalendarEvent(_CamelModel):
    """One macro calendar row.

    The wire types are unprobed for this route: ``actual``/``forecast``/``prior``
    may be numbers or text prints (e.g. ``"3.2%"``), so both are accepted and
    preserved. Unknown fields stay as extras.
    """

    id: str | int | None = None
    date: str
    time: str | None = None
    country: str = ""
    event: str
    actual: float | str | None = None
    forecast: float | str | None = None
    prior: float | str | None = None
    impact: str | None = None


class EconCalendarResult(_CamelModel):
    events: list[EconCalendarEvent] = Field(default_factory=list)


class EconSeriesObservation(_CamelModel):
    date: str
    # FRED-style sparse series answer "." for a missing print; the normalizer
    # maps that to null. Unknown fields stay as extras.
    value: float | None = None


class EconSeriesInfo(_CamelModel):
    """Series metadata; the long tail (frequency/source/notes/...) stays extras."""

    id: str | int | None = None
    title: str | None = None
    units: str | None = None
    frequency: str | None = None
    source: str | None = None
    last_updated: str | None = None


class EconSeriesResult(_CamelModel):
    observations: list[EconSeriesObservation] = Field(default_factory=list)
    info: EconSeriesInfo | None = None


class YieldCurvePoint(_CamelModel):
    """One curve tenor.

    ``yield`` is a Python keyword, so the attribute is ``yield_`` with an
    explicit wire alias (the alias generator alone produces ``yield_``).
    """

    maturity: str
    maturity_years: float | None = None
    yield_: float | None = Field(default=None, alias="yield")
    as_of: str | None = None
    fetched_at: str | None = None
    stale: bool | None = None


class YieldCurveResult(_CamelModel):
    points: list[YieldCurvePoint] = Field(default_factory=list)


class CdsTrade(_CamelModel):
    """One DTCC PPD CDS trade record; sparse by nature, so all fields optional."""

    dissemination_id: str | int | None = None
    action_type: str | None = None
    event_timestamp: str | None = None
    execution_timestamp: str | None = None
    effective_date: str | None = None
    expiration_date: str | None = None
    maturity_date: str | None = None
    issuer_name: str | None = None
    underlier_id: str | int | None = None
    underlier_id_source: str | None = None
    upi: str | None = None
    upi_fisn: str | None = None
    upi_underlier_name: str | None = None
    notional_amount: float | None = None
    notional_capped: bool | None = None
    notional_currency: str | None = None
    fixed_rate: float | None = None
    reported_spread: float | None = None


class CdsResult(_CamelModel):
    source: str | None = None
    as_of: str | None = None
    trades: list[CdsTrade] = Field(default_factory=list)


class ResearchHit(_CamelModel):
    id: str | int
    doc_type: str | None = None
    source_id: str | int | None = None
    chunk_index: int | None = None
    ticker: str | None = None
    published_at: str | None = None
    title: str | None = None
    url: str | None = None
    snippet: str | None = None


class ResearchSearchPagination(_CamelModel):
    """Pagination metadata from the ``/cloud/search`` payload (live-verified)."""

    total: int | None = None
    has_more: bool | None = None
    next_offset: int | None = None
    count_capped: bool | None = None


class ResearchSearchResult(_CamelModel):
    hits: list[ResearchHit] = Field(default_factory=list)
    pagination: ResearchSearchPagination | None = None


class CongressTrade(_CamelModel):
    """One House disclosure row.

    The upstream OCR path is currently failing (HTTP 500) and its row schema is
    only partly known; the typed subset follows the live field names
    (``memberName``/``assetName``/``sourceUrl``/``filingDate``/
    ``notificationDate``) and everything else is preserved as extras.
    """

    id: str | int | None = None
    member_name: str | None = None
    ticker: str | None = None
    transaction_date: str | None = None
    filing_date: str | None = None
    notification_date: str | None = None
    transaction_type: str | None = None
    amount: str | None = None
    asset_name: str | None = None
    source_url: str | None = None


class CongressTradesResult(_CamelModel):
    trades: list[CongressTrade] = Field(default_factory=list)


class Transcript(_CamelModel):
    """One earnings-call row from the upstream ``calls`` list (Gloomberb Pro).

    The live list payload is ``CloudEarningsCallListPayload`` whose rows carry
    ``companyName``/``callAt``/``webcastUrl``; unknown fields stay extras.
    """

    id: str | int
    ticker: str | None = None
    company_name: str | None = None
    call_at: str | None = None
    webcast_url: str | None = None


class TranscriptsResult(_CamelModel):
    transcripts: list[Transcript] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Coverage-expansion payloads (#4110 phase 2)
# ---------------------------------------------------------------------------


class StatementRow(_CamelModel):
    """One statement row.

    The upstream rows are sparse annual/quarterly fundamentals: ``date`` and
    ``currency`` are stable, a handful of common fields are typed, and the long
    tail (hundreds of line items) is preserved as extras.
    """

    date: str
    currency: str | None = None
    date_source: str | None = None
    net_income_continuous_operations: float | None = None
    cash_and_cash_equivalents: float | None = None
    issuance_of_debt: float | None = None
    purchase_of_business: float | None = None
    total_equity: float | None = None
    basic_shares: float | None = None


class StatementsResult(_CamelModel):
    annual_statements: list[StatementRow] = Field(default_factory=list)
    quarterly_statements: list[StatementRow] = Field(default_factory=list)


class TweetAuthor(_CamelModel):
    id: str | int | None = None
    user_name: str | None = None
    name: str | None = None


class TweetMetrics(_CamelModel):
    retweets: int | None = None
    replies: int | None = None
    likes: int | None = None
    quotes: int | None = None
    views: int | None = None
    bookmarks: int | None = None


class Tweet(_CamelModel):
    """One X/Twitter post row; unknown fields stay extras."""

    id: str | int
    url: str | None = None
    text: str = ""
    created_at: str | None = None
    lang: str | None = None
    is_reply: bool | None = None
    author: TweetAuthor | None = None
    metrics: TweetMetrics | None = None


class TweetsResult(_CamelModel):
    """The tweets payload's own metadata plus the client-reduced rows.

    The upstream echoes ``limit``/``hours`` without applying either (live
    probes: 375 rows for limit=1; ~394 rows spanning ~13 days for hours=1), so
    the client applies both: rows older than ``now - hours`` are dropped when
    ``hours`` was requested (an unparseable ``createdAt`` is dropped while a
    window is active), then the remainder is sliced to ``limit``.
    ``total_available`` is the upstream row count before either reduction, and
    ``truncated`` says whether either reduction dropped rows.
    """

    query: str = ""
    query_type: str | None = None
    since: str | None = None
    until: str | None = None
    as_of: str | None = None
    cached: bool | None = None
    hours: int | None = None
    ticker: str | None = None
    cashtag: str | None = None
    include_replies: bool | None = None
    tweets: list[Tweet] = Field(default_factory=list)
    total_available: int = 0
    truncated: bool = False


class Venue(_CamelModel):
    """One exchange venue row; ``mic`` is the identity, the rest is optional."""

    mic: str
    name: str = ""
    title: str | None = None
    country: str | None = None
    country_code: str | None = None
    city: str | None = None
    timezone: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    is_open: bool | None = None
    time_after_open_seconds: int | None = None
    time_to_open_seconds: int | None = None
    time_to_close_seconds: int | None = None


class VenuesResult(_CamelModel):
    provider_id: str | None = None
    checked_at: int | None = None
    refresh_at: int | None = None
    venues: list[Venue] = Field(default_factory=list)


class SavedSearch(_CamelModel):
    """One saved-search row from ``/cloud/search/saved`` (shape probe-pending).

    The live row shape is unverified (the probed session returned an empty
    list); the common fields are typed optionally and unknown fields stay
    extras until a probe records the payload.
    """

    id: str | int | None = None
    name: str | None = None
    query: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class SavedSearchesResult(_CamelModel):
    searches: list[SavedSearch] = Field(default_factory=list)


class ScreenerRow(_CamelModel):
    """One screener row.

    Shape source: the gloomberb TS plugin's ``CloudMarketScreenerItem`` (the
    Pro success payload cannot be observed from a free session — the route
    answers PRO_REQUIRED). Every field is optional and unknown keys stay
    extras; ``market_cap`` is not part of the upstream item type and was
    dropped.
    """

    symbol: str | None = None
    name: str | None = None
    exchange: str | None = None
    price: float | None = None
    change: float | None = None
    change_percent: float | None = None
    volume: float | None = None
    rank: int | None = None
    currency: str | None = None
    trade_count: int | None = None
    # Explicit aliases: `to_camel("high52w")` would produce "high52W" (digit
    # followed by a lowercase letter defeats pydantic's identity shortcut).
    high52w: float | None = Field(default=None, alias="high52w")
    low52w: float | None = Field(default=None, alias="low52w")
    day_high: float | None = None
    day_low: float | None = None
    last_updated: float | None = None
    data_source: str | None = None


class ScreenerResult(_CamelModel):
    """The screener payload envelope (``CloudMarketScreenerItem`` list).

    Payload-level fields follow the TS type's envelope
    (``providerId``/``category``/``asOf``/``stale``/``items``); rows are
    exposed as ``rows``.
    """

    provider_id: str | None = None
    category: str | None = None
    as_of: str | None = None
    stale: bool | None = None
    rows: list[ScreenerRow] = Field(default_factory=list)


class Fund13F(_CamelModel):
    """One ``/cloud/sec/13f/funds`` search row; the wire key is ``CIK``."""

    name: str = ""
    cik: str | None = Field(default=None, alias="CIK")


class TopFund13F(_CamelModel):
    cik: str | None = None
    name: str | None = None
    period_of_report: str | None = None
    pnl: float | None = None


class TickerInfo13F(_CamelModel):
    cusip: str
    ticker: str | None = None
    company_name: str | None = None


class FundHolders13F(_CamelModel):
    """Holders of one CUSIP for a period; the wire period key is camelCase."""

    cusip: str | None = None
    period_of_report: str | None = Field(default=None, alias="periodOfReport")
    ciks: list[str] = Field(default_factory=list)


class Funds13FResult(_CamelModel):
    """One tool, ``what`` discriminator: exactly one slot is populated."""

    what: Literal["search", "top", "tickers", "holders"]
    funds: list[Fund13F] | None = None
    top_funds: list[TopFund13F] | None = None
    tickers: list[TickerInfo13F] | None = None
    holders: FundHolders13F | None = None


class Filing13F(_CamelModel):
    """One 13F filing/forms row (SEC index metadata); extras keep the rest."""

    accession_number: str
    cik: str | None = None
    company_name: str | None = None
    form_type: str | None = None
    submission_type: str | None = None
    period_of_report: str | None = None
    filed_as_of_date: str | None = None
    effectiveness_date: str | None = None
    table_value_total: float | None = None
    table_entry_total: int | None = None
    url: str | None = None
    is_amendment: bool | None = None
    amendment_type: str | None = None
    state_of_incorporation: str | None = None
    film_number: str | None = None


class Holding13F(_CamelModel):
    """One 13F holding row, mapped to the TS plugin's semantic names.

    Wire names are snake_case (``name_of_issuer``/``ssh_prnamt``/
    ``ssh_prnamt_type``); the attributes expose ``issuer``/``shares``/
    ``share_type`` and the remaining columns stay typed as wire.
    """

    accession_number: str | None = None
    cik: str | None = None
    issuer: str | None = Field(default=None, alias="name_of_issuer")
    title_of_class: str | None = Field(default=None, alias="title_of_class")
    cusip: str | None = None
    ticker: str | None = None
    value: float | None = None
    shares: float | None = Field(default=None, alias="ssh_prnamt")
    share_type: str | None = Field(default=None, alias="ssh_prnamt_type")
    investment_discretion: str | None = None
    voting_authority_sole: float | None = None
    voting_authority_shared: float | None = None
    voting_authority_none: float | None = None
    put_call: str | None = None
    pnl: float | None = None


class Holdings13FResult(_CamelModel):
    """One tool, ``what`` discriminator: exactly one slot is populated."""

    what: Literal["filings", "forms", "form"]
    filings: list[Filing13F] | None = None
    forms: list[Filing13F] | None = None
    holdings: list[Holding13F] | None = None
    # Computed as ``len(rows) >= limit``: the upstream returns a bare array
    # with no continuation token (live-verified).
    has_more: bool | None = None


# ---------------------------------------------------------------------------
# Coverage-expansion payloads (#4110 phase 3)
# ---------------------------------------------------------------------------


class CompanyRef(_CamelModel):
    """The company block every public filing product nests in its payloads."""

    ticker: str
    cik: str | None = None
    name: str = ""
    short_name: str | None = None


class ShillerObservation(_CamelModel):
    """One month of Robert Shiller's dataset (live: ~1869 rows from 1871)."""

    date: str
    price: float | None = None
    dividend: float | None = None
    earnings: float | None = None
    cpi: float | None = None
    long_rate: float | None = None
    cape: float | None = None
    # CAPE earnings yield over the real 10-year rate (Shiller's ERP).
    excess_cape_yield: float | None = None


class ShillerResult(_CamelModel):
    """The monthly valuation series, most-recent ``limit`` rows (ascending).

    ``total_available`` is the full upstream row count and ``truncated`` flags
    the client-side tail slice.
    """

    observations: list[ShillerObservation] = Field(default_factory=list)
    source_url: str | None = None
    dataset_fetched_at: str | None = None
    total_available: int = 0
    truncated: bool = False


class ExecutivePay(_CamelModel):
    """One named-executive compensation row (annual proxy).

    ``prior_year_total`` is only present on the CEO row upstream; extras keep
    anything the extractor adds later.
    """

    name: str
    title: str | None = None
    salary: float | None = None
    bonus: float | None = None
    stock_awards: float | None = None
    option_awards: float | None = None
    non_equity_incentive: float | None = None
    pension_and_deferred: float | None = None
    all_other: float | None = None
    total: float | None = None
    prior_year_total: float | None = None


class ProxySummary(_CamelModel):
    """One proxy filing summary (list row / ``otherYears`` row)."""

    id: str
    ticker: str
    company: CompanyRef
    proxy_year: int
    fiscal_year: int | None = None
    fiscal_year_label: str | None = None
    filed_at: str | None = None
    meeting_date: str | None = None
    updated_at: str | None = None
    ceo_name: str | None = None
    ceo_title: str | None = None
    ceo_total: float | None = None
    ceo_prior_year_total: float | None = None
    pay_ratio: float | None = None
    median_employee_pay: float | None = None


class HighlightFigure(_CamelModel):
    """A key figure on a proxy statement (label/value/note triple)."""

    label: str
    value: str
    note: str | None = None


class ProxyStatement(ProxySummary):
    """One full proxy statement (compensation tables + extracted highlights)."""

    doc_url: str | None = None
    ceo: ExecutivePay | None = None
    named_executives: list[ExecutivePay] = Field(default_factory=list)
    say_on_pay_prior_support: float | None = None
    highlights: str | None = None
    key_figures: list[HighlightFigure] = Field(default_factory=list)
    other_years: list[ProxySummary] = Field(default_factory=list)


class ProxyStatementsResult(_CamelModel):
    what: Literal["list", "statement"]
    company: CompanyRef | None = None
    proxies: list[ProxySummary] | None = None
    statement: ProxyStatement | None = None


class FilingPerson(_CamelModel):
    """A person named in a material 8-K event (officer change and similar)."""

    name: str
    role: str | None = None
    action: str | None = None
    effective: str | None = None


class FilingEvent(_CamelModel):
    """One 8-K, classified by item labels and, when it carried news, read."""

    id: str
    ticker: str
    company: CompanyRef | None = None
    filed_at: str | None = None
    filing_date: str | None = None
    doc_url: str | None = None
    items: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    kinds: list[str] = Field(default_factory=list)
    material: bool = False
    headline: str | None = None
    summary: str | None = None
    people: list[FilingPerson] = Field(default_factory=list)
    read: bool = False


class FilingEventsResult(_CamelModel):
    ticker: str = ""
    events: list[FilingEvent] = Field(default_factory=list)


class RiskFactor(_CamelModel):
    """One extracted 10-K risk factor (heading + excerpt)."""

    heading: str
    group: str | None = None
    excerpt: str = ""
    words: int | None = None


class RiskNote(_CamelModel):
    index: int
    text: str


class RiskRemoved(_CamelModel):
    heading: str
    group: str | None = None
    excerpt: str = ""


class RiskReworded(_CamelModel):
    index: int
    similarity: float | None = None
    heading_changed: bool | None = None
    prior_heading: str | None = None


class RiskDiff(_CamelModel):
    """Year-over-year risk-factor diff (present when a prior report exists)."""

    added: list[int] = Field(default_factory=list)
    removed: list[RiskRemoved] = Field(default_factory=list)
    reworded: list[RiskReworded] = Field(default_factory=list)
    matched: int | None = None
    prior_risk_count: int | None = None


class RiskNotes(_CamelModel):
    added: list[RiskNote] = Field(default_factory=list)
    removed: list[RiskNote] = Field(default_factory=list)
    reworded: list[RiskNote] = Field(default_factory=list)
    top: list[RiskNote] = Field(default_factory=list)


class RiskSummary(_CamelModel):
    """One risk-report summary (list row / ``otherYears`` row)."""

    id: str
    ticker: str
    company: CompanyRef
    report_year: int
    filed_at: str | None = None
    updated_at: str | None = None
    risk_count: int = 0
    group_count: int = 0
    word_count: int = 0
    added_count: int | None = None
    removed_count: int | None = None
    reworded_count: int | None = None
    overview: str | None = None


class RiskReport(RiskSummary):
    """One full risk-factor report with groups, risks, diff, and notes."""

    doc_url: str | None = None
    groups: list[str] = Field(default_factory=list)
    risks: list[RiskFactor] = Field(default_factory=list)
    diff: RiskDiff | None = None
    notes: RiskNotes | None = None
    other_years: list[RiskSummary] = Field(default_factory=list)


class RiskReportsResult(_CamelModel):
    what: Literal["list", "report"]
    company: CompanyRef | None = None
    reports: list[RiskSummary] | None = None
    report: RiskReport | None = None


class ShortInterestPoint(_CamelModel):
    """One biweekly exchange settlement row."""

    settlement_date: str
    shares_short: float
    previous_shares_short: float | None = None
    average_daily_volume: float | None = None
    days_to_cover: float | None = None
    change_percent: float | None = None
    revised: bool = False


class ShortInterestResult(_CamelModel):
    symbol: str = ""
    issue_name: str | None = None
    points: list[ShortInterestPoint] = Field(default_factory=list)


class EquityDiagnosticPending(_CamelModel):
    """Generation has not finished; retry after ``retry_after_ms``."""

    status: Literal["generating"]
    retry_after_ms: int


class EquityDiagnosticFinding(_CamelModel):
    """One finding; observation and interpretation are deliberately separate."""

    id: str
    kind: Literal["red_flag", "green_flag", "anomaly"]
    severity: int
    confidence: float | None = None
    title: str = ""
    observation: str = ""
    interpretation: str = ""
    evidence_ids: list[str] = Field(default_factory=list)


class EquityDiagnosticCoverage(_CamelModel):
    dataset: str
    status: str
    as_of: str | None = None
    provider: str | None = None
    note: str | None = None


class EquityDiagnosticEvidence(_CamelModel):
    """A citation; the server owns the URLs."""

    id: str
    dataset: str = ""
    label: str = ""
    as_of: str | None = None
    provider: str | None = None
    url: str | None = None


class EquityDiagnosticReport(_CamelModel):
    """A completed AI-generated evidence review.

    Free (email-verified) sessions only receive ``access="preview"`` results;
    the verdict/summary are the model's reading, not investment advice.
    """

    schema_version: int | None = None
    access: Literal["preview", "full"] | None = None
    symbol: str
    exchange: str = ""
    company_name: str | None = None
    status: str
    verdict: str
    summary: str = ""
    confidence: float | None = None
    findings: list[EquityDiagnosticFinding] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    coverage: list[EquityDiagnosticCoverage] = Field(default_factory=list)
    evidence: list[EquityDiagnosticEvidence] = Field(default_factory=list)
    generated_at: str | None = None
    expires_at: str | None = None
    refresh_allowed_at: str | None = None
    cached: bool | None = None
    stale: bool | None = None
    prompt_version: int | None = None
    model: str | None = None


class EquityDiagnosticResult(_CamelModel):
    """One tool, pending-or-report: the first call per symbol is a 202 pending."""

    pending: EquityDiagnosticPending | None = None
    report: EquityDiagnosticReport | None = None


# ---------------------------------------------------------------------------
# Concrete envelopes (one per tool)
# ---------------------------------------------------------------------------

QuoteEnvelope = DigifetchEnvelope[QuoteResult]
QuotesBatchEnvelope = DigifetchEnvelope[QuotesBatchResult]
PriceHistoryEnvelope = DigifetchEnvelope[PriceHistoryResult]
TickerFinancialsEnvelope = DigifetchEnvelope[TickerFinancialsResult]
OptionsChainEnvelope = DigifetchEnvelope[OptionsChainResult]
SecFilingsEnvelope = DigifetchEnvelope[SecFilingsResult]
HoldersEnvelope = DigifetchEnvelope[HoldersResult]
AnalystResearchEnvelope = DigifetchEnvelope[AnalystResearchResult]
CorporateActionsEnvelope = DigifetchEnvelope[CorporateActionsResult]
EarningsCalendarEnvelope = DigifetchEnvelope[EarningsCalendarResult]
ExchangeRateEnvelope = DigifetchEnvelope[ExchangeRateResult]
SearchEnvelope = DigifetchEnvelope[SearchResult]
NewsEnvelope = DigifetchEnvelope[NewsResult]
EconCalendarEnvelope = DigifetchEnvelope[EconCalendarResult]
EconSeriesEnvelope = DigifetchEnvelope[EconSeriesResult]
YieldCurveEnvelope = DigifetchEnvelope[YieldCurveResult]
CdsEnvelope = DigifetchEnvelope[CdsResult]
ResearchSearchEnvelope = DigifetchEnvelope[ResearchSearchResult]
CongressTradesEnvelope = DigifetchEnvelope[CongressTradesResult]
TranscriptsEnvelope = DigifetchEnvelope[TranscriptsResult]
StatementsEnvelope = DigifetchEnvelope[StatementsResult]
TweetsEnvelope = DigifetchEnvelope[TweetsResult]
VenuesEnvelope = DigifetchEnvelope[VenuesResult]
SavedSearchesEnvelope = DigifetchEnvelope[SavedSearchesResult]
ScreenerEnvelope = DigifetchEnvelope[ScreenerResult]
Funds13FEnvelope = DigifetchEnvelope[Funds13FResult]
Holdings13FEnvelope = DigifetchEnvelope[Holdings13FResult]
ShillerEnvelope = DigifetchEnvelope[ShillerResult]
ProxyStatementsEnvelope = DigifetchEnvelope[ProxyStatementsResult]
FilingEventsEnvelope = DigifetchEnvelope[FilingEventsResult]
RiskReportsEnvelope = DigifetchEnvelope[RiskReportsResult]
ShortInterestEnvelope = DigifetchEnvelope[ShortInterestResult]
EquityDiagnosticEnvelope = DigifetchEnvelope[EquityDiagnosticResult]


def envelope_error(envelope: DigifetchEnvelope[Any]) -> DigifetchError | None:
    """Return the typed error carried by *envelope*, or None on success."""
    return envelope.data if isinstance(envelope.data, DigifetchError) else None
