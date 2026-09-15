"""Pydantic v2 models for the digifetch x Gloomberb data layer (#4069).

This package is the data layer for the 13 `digifetch_*` tools described in
``docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`` §5. It is
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

from datetime import date, datetime, timezone
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.alias_generators import to_camel

__all__ = [
    "SOURCE",
    "PROVIDER_ID",
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
    "not_found",
    "rate_limited",
    "upstream_error",
    "invalid_input",
]


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
    symbol: Symbol
    resolution: Resolution
    # None means "contract default": resolved to 5Y for 1d only. Never clamped.
    range: Range | None = None
    exchange: str | None = None

    @model_validator(mode="after")
    def _enforce_resolution_range_caps(self) -> PriceHistoryInput:
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


def envelope_error(envelope: DigifetchEnvelope[Any]) -> DigifetchError | None:
    """Return the typed error carried by *envelope*, or None on success."""
    return envelope.data if isinstance(envelope.data, DigifetchError) else None
