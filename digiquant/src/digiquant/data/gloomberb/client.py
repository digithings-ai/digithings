"""Gloomberb Cloud HTTP client built on digifetch transport primitives (§5.5).

Approach (c) from the scoping spec: a Python HTTP client against
``https://api.gloom.sh``, anonymous cookie-less by default, with an optional
``GLOOMBERB_SESSION_COOKIE`` for the session-gated endpoints (holders, analyst
research, corporate actions, research search, transcripts; transcripts
additionally require a Pro plan). The client owns endpoint constants, error
mapping (§5.3), the 900s TTL cache, a circuit breaker, and the kill switch;
``digifetch`` stays the generic transport engine.

The kill switch is ``GLOOMBERB_ENABLED`` (default ON): tools are default-ON per
the author decision, and setting the flag to ``0``/``false``/``no``/``off``
disables the whole family. The session cookie is read from
``GLOOMBERB_SESSION_COOKIE`` - never logged, never part of tool input.

No environment variables are read at import time; the flags are resolved in
``__init__`` (explicit arguments win over the environment).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, NamedTuple, TypeVar, cast  # score:allow untyped any — wire JSON
from urllib.parse import quote

import httpx
from digifetch import (
    FetchResult,
    HttpFetcher,
    RateLimiter,
    RetryPolicy,
    SsrfBlockedError,
    with_retry,
)
from pydantic import BaseModel, ValidationError

from . import normalizers as nz
from .calculators import (
    black_scholes_iv,
    black_scholes_price,
    bond_metrics,
    kelly_fraction,
)
from .models import (
    PREVIEW_ACCESS_WARNING,
    AnalystResearchEnvelope,
    AnalystResearchInput,
    BondCalcEnvelope,
    BondCalcInput,
    BondCalcResult,
    CdsEnvelope,
    CdsInput,
    CdsResult,
    CongressTradesEnvelope,
    CongressTradesInput,
    CongressTradesResult,
    CorporateActionsEnvelope,
    CorporateActionsInput,
    CorporateActionsResult,
    DigifetchEnvelope,
    DigifetchError,
    DividendYieldEnvelope,
    DividendYieldInput,
    DividendYieldResult,
    EarningsCalendarEnvelope,
    EarningsCalendarInput,
    EarningsCalendarResult,
    EarningsEvent,
    EconCalendarEnvelope,
    EconCalendarInput,
    EconCalendarResult,
    EconSeriesEnvelope,
    EconSeriesInput,
    EquityDiagnosticEnvelope,
    EquityDiagnosticInput,
    EquityDiagnosticResult,
    ExchangeRateEnvelope,
    ExchangeRateInput,
    FilingEventsEnvelope,
    FilingEventsInput,
    Funds13FEnvelope,
    FxMatrixEnvelope,
    FxMatrixInput,
    FxMatrixResult,
    HoldersEnvelope,
    HoldersInput,
    HoldersResult,
    Holdings13FEnvelope,
    KellyEnvelope,
    KellyInput,
    KellyResult,
    NewsEnvelope,
    NewsInput,
    NewsResult,
    OptionsCalcEnvelope,
    OptionsCalcInput,
    OptionsCalcResult,
    OptionsChainEnvelope,
    OptionsChainInput,
    OptionsChainResult,
    PredictionMarketRow,
    PredictionMarketsEnvelope,
    PredictionMarketsInput,
    PredictionMarketsResult,
    PriceHistoryEnvelope,
    PriceHistoryInput,
    PriceHistoryMetadata,
    PriceHistoryResult,
    ProxyStatementsEnvelope,
    ProxyStatementsInput,
    QuoteEnvelope,
    QuoteInput,
    QuoteResult,
    QuotesBatchEnvelope,
    QuotesBatchInput,
    QuotesBatchResult,
    ResearchSearchEnvelope,
    ResearchSearchInput,
    RiskReportsEnvelope,
    RiskReportsInput,
    SavedSearchesEnvelope,
    SavedSearchesInput,
    ScreenerEnvelope,
    ScreenerInput,
    SearchEnvelope,
    SearchInput,
    SearchResult,
    SecFilingsEnvelope,
    SecFilingsInput,
    SecFilingsResult,
    ShillerEnvelope,
    ShillerInput,
    ShortInterestEnvelope,
    ShortInterestInput,
    StatementsEnvelope,
    StatementsInput,
    ThirteenFFundsInput,
    ThirteenFHoldingsInput,
    TickerFinancialsEnvelope,
    TickerFinancialsInput,
    TickerFinancialsResult,
    TickerTweetsInput,
    TranscriptsEnvelope,
    TranscriptsInput,
    TranscriptsResult,
    TweetSearchInput,
    TweetsEnvelope,
    VenuesEnvelope,
    VenuesInput,
    VixTermEnvelope,
    VixTermInput,
    VixTermResult,
    YieldCurveEnvelope,
    YieldCurveInput,
    YieldCurveResult,
)

__all__ = [
    "GLOOMBERB_BASE_URL",
    "GLOOMBERB_ENABLED_ENV",
    "GLOOMBERB_SESSION_COOKIE_ENV",
    "SESSION_COOKIE_NAMES",
    "session_cache_fingerprint",
    "DEFAULT_CACHE_TTL_SECONDS",
    "DEFAULT_MIN_INTERVAL_SECONDS",
    "DEFAULT_CIRCUIT_FAILURE_THRESHOLD",
    "DEFAULT_CIRCUIT_RESET_SECONDS",
    "RETRYABLE_EXCEPTIONS",
    "ENDPOINTS",
    "GloomberbClient",
    "gloomberb_enabled",
    "yfinance_earnings_events",
]

GLOOMBERB_BASE_URL = "https://api.gloom.sh"
GLOOMBERB_ENABLED_ENV = "GLOOMBERB_ENABLED"
GLOOMBERB_SESSION_COOKIE_ENV = "GLOOMBERB_SESSION_COOKIE"

# The free tier is rate-limited; one client-wide minimum-interval gate. Pinned
# here per §5.5 ("the RateLimiter interval is a client constant").
DEFAULT_MIN_INTERVAL_SECONDS = 0.5
# 900s TTL cache for enrichment reads, matching the R2 market-data-cache
# convention (§5.5).
DEFAULT_CACHE_TTL_SECONDS = 900.0
DEFAULT_CIRCUIT_FAILURE_THRESHOLD = 3
DEFAULT_CIRCUIT_RESET_SECONDS = 60.0
# Bounded sleep for a 429 Retry-After (a hostile/large value must not pin the
# caller); the client surfaces the header in the typed error either way.
DEFAULT_MAX_RETRY_AFTER_SECONDS = 5.0
# Cache is TTL'd and size-bounded; expired entries are evicted on access.
DEFAULT_CACHE_MAX_ENTRIES = 256
# Spec §5.1: the Cloud client wrapper caps search at 10 and flags the clamp.
SEARCH_LIMIT_CAP = 10

# The equity-diagnostic POST triggers server-side generation and carries no
# idempotency key, so it must not be retried: a timed-out attempt would silently
# re-request a generation. The server's `refreshAllowedAt` hints that it
# de-dupes concurrent requests, but that is unverified, so pin one attempt.
# (The shared policy still retries everything else.)
_SINGLE_ATTEMPT_POLICY = RetryPolicy(attempts=1)

# Upstream session cookie names (api-client/request.ts SESSION_COOKIE_NAMES).
SESSION_COOKIE_NAMES: tuple[str, ...] = (
    "__Secure-gloomberb.session_token",
    "gloomberb.session_token",
)


def session_cache_fingerprint(cookie: str | None) -> str:
    """Non-reversible cache discriminator for a session cookie (#4110 phase 5).

    Responses are entitlement-sensitive: a preview (or full) report cached by
    one session must not be served to a different session. The cache key
    therefore includes this fingerprint instead of the raw cookie — a
    truncated SHA-256 separates sessions without storing the secret. Anonymous
    clients share the ``"anon"`` fingerprint, exactly as before.
    """
    if not cookie:
        return "anon"
    return hashlib.sha256(cookie.encode("utf-8")).hexdigest()[:16]


DEFAULT_HEADERS: dict[str, str] = {"Accept": "application/json"}

# Real endpoint family map (§3, validation item 6): /market/*, /news, /cloud/*.
ENDPOINTS: dict[str, str] = {
    "quote": "/market/quote",
    "quotes_batch": "/market/quotes/batch",
    "history": "/market/history",
    "financials": "/market/financials",
    "options": "/market/options",
    "exchange_rate": "/market/exchange-rate",
    "search": "/market/search",
    "holders": "/market/holders",
    "analyst": "/market/analyst",
    "corporate_actions": "/market/corporate-actions",
    "news": "/news",
    "sec_filings": "/cloud/sec/filings",
    "sec_filing_documents": "/cloud/sec/filing/documents",
    "sec_filing_content": "/cloud/sec/filing/content",
    # coverage expansion (#4110 phase 1)
    "econ_calendar": "/cloud/econ/calendar",
    "econ_series": "/cloud/econ/series",
    "yield_curve": "/cloud/econ/yield-curve",
    "cds": "/cloud/credit/cds",
    "research_search": "/cloud/search",
    "congress_trades": "/cloud/congress/house",
    "transcripts": "/cloud/transcripts",
    # coverage expansion (#4110 phase 2)
    "statements": "/market/statements",
    "tweets": "/news/tweets",
    "tweet_search": "/news/tweets/search",
    "venues": "/market/venues",
    "screener": "/market/screener",
    "13f_funds": "/cloud/sec/13f/funds",
    "13f_topfunds": "/cloud/sec/13f/topfunds",
    "13f_tickers": "/cloud/sec/13f/tickers",
    "13f_holders": "/cloud/sec/13f/holders",
    "13f_filings": "/cloud/sec/13f/filings",
    "13f_forms": "/cloud/sec/13f/forms",
    "13f_form": "/cloud/sec/13f/form",
    # coverage expansion (#4110 phase 3)
    "shiller": "/cloud/econ/shiller",
    "proxy_statements": "/public/proxies",
    "filing_events": "/public/events",
    "risk_reports": "/public/risks",
    "short_interest": "/market/short-interest",
    "equity_diagnostic": "/research/equity-diagnostic",
    # coverage expansion (#4110 phase 4a)
    "saved_searches": "/cloud/search/saved",
}

# Prediction-markets venue catalog (#4813). No Gloomberb Cloud route exists
# for prediction markets, so the catalog reads the public venue APIs directly
# (the same hosts the gloom prediction-markets plugin reads client-side).
# Both are anonymous, unauthenticated, unofficial: shapes are parsed
# defensively and each venue fails soft into the result warnings.
POLYMARKET_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
POLYMARKET_EVENTS_PATH = "/events"
POLYMARKET_EVENT_URL = "https://polymarket.com/event/{slug}"
KALSHI_TRADE_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
KALSHI_EVENTS_PATH = "/events"
KALSHI_MARKET_URL = "https://kalshi.com/markets/{ticker}"

# Venue honesty: result-level attribution for venue-sourced rows. This names
# the venues, never Gloomberb Cloud (there is no term.gloom.sh page for
# venue rows), and carries the polling notice the plugin documents.
PREDICTION_MARKETS_ATTRIBUTION = (
    "Prediction-markets catalog sourced directly from the venues' public APIs "
    "(Polymarket Gamma, Kalshi trade API). Anonymous, polled reads: quotes may "
    "lag the venue order book. Enrichment only, never a pipeline primary."
)


def _venue_float(value: Any) -> float | None:
    """Coerce a loose venue number (numeric string, int, float) to float."""
    if isinstance(value, bool):
        return None
    if isinstance(value, str):
        text = value.strip().rstrip("%").strip()
        if not text:
            return None
        try:
            value = float(text)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _polymarket_yes_prob(market: Mapping[str, Any]) -> float | None:
    """Yes probability from a Gamma market's JSON-encoded outcome arrays."""
    outcomes = market.get("outcomes")
    prices = market.get("outcomePrices")
    if isinstance(outcomes, str):
        try:
            outcomes = json.loads(outcomes)
        except (json.JSONDecodeError, ValueError):
            outcomes = None
    if isinstance(prices, str):
        try:
            prices = json.loads(prices)
        except (json.JSONDecodeError, ValueError):
            prices = None
    if not isinstance(outcomes, list) or not isinstance(prices, list):
        return None
    names = [str(name).lower() for name in outcomes]
    index = names.index("yes") if "yes" in names else 0
    if index >= len(prices):
        return None
    prob = _venue_float(prices[index])
    return prob if prob is not None and 0.0 <= prob <= 1.0 else None


def _polymarket_tags(event: Mapping[str, Any]) -> str | None:
    """First Gamma tag label (``[{"label": "Macro"}]`` or plain strings)."""
    tags = event.get("tags")
    if not isinstance(tags, list):
        return None
    for tag in tags:
        if isinstance(tag, Mapping) and isinstance(tag.get("label"), str):
            return tag["label"]
        if isinstance(tag, str) and tag.strip():
            return tag.strip()
    return None


def _polymarket_rows(events: Any) -> list[PredictionMarketRow]:
    """Normalize a Gamma ``/events`` array to catalog rows (bad entries skipped)."""
    rows: list[PredictionMarketRow] = []
    if not isinstance(events, list):
        return rows
    for event in events:
        if not isinstance(event, Mapping):
            continue
        slug = event.get("slug")
        venue_url = POLYMARKET_EVENT_URL.format(slug=slug) if isinstance(slug, str) else ""
        markets = event.get("markets")
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, Mapping):
                continue
            title = market.get("question") or event.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            end_date = market.get("endDate")
            rows.append(
                PredictionMarketRow(
                    venue="polymarket",
                    title=title.strip(),
                    yes_prob=_polymarket_yes_prob(market),
                    spread=None,
                    volume_24h=_venue_float(market.get("volume24hr") or market.get("volume")),
                    liquidity=_venue_float(market.get("liquidity")),
                    open_interest=None,
                    ends_at=end_date if isinstance(end_date, str) else None,
                    status="open" if market.get("closed") is False else None,
                    category=_polymarket_tags(event),
                    venue_url=venue_url,
                )
            )
    return rows


def _kalshi_price(value: Any, cents: bool) -> float | None:
    """Kalshi price in probability units (dollar-or-cent wire values)."""
    prob = _venue_float(value)
    if prob is None:
        return None
    return prob / 100.0 if cents else prob


def _kalshi_rows(payload: Any) -> list[PredictionMarketRow]:
    """Normalize a Kalshi ``/events`` payload to catalog rows (bad entries skipped)."""
    rows: list[PredictionMarketRow] = []
    events = payload.get("events") if isinstance(payload, Mapping) else None
    if not isinstance(events, list):
        return rows
    for event in events:
        if not isinstance(event, Mapping):
            continue
        event_title = event.get("title")
        category = event.get("category")
        markets = event.get("markets")
        if not isinstance(markets, list):
            continue
        for market in markets:
            if not isinstance(market, Mapping):
                continue
            title = market.get("title") or event_title
            if not isinstance(title, str) or not title.strip():
                continue
            raw_bid = _venue_float(market.get("yes_bid"))
            raw_ask = _venue_float(market.get("yes_ask"))
            raw_last = _venue_float(market.get("last_price"))
            # Dollar-or-cent wire values: anything above 1 is cents.
            candidates = [v for v in (raw_bid, raw_ask, raw_last) if v is not None]
            cents = bool(candidates) and max(candidates) > 1.0
            bid = _kalshi_price(raw_bid, cents)
            ask = _kalshi_price(raw_ask, cents)
            ticker = market.get("ticker")
            close_time = market.get("close_time")
            rows.append(
                PredictionMarketRow(
                    venue="kalshi",
                    title=title.strip(),
                    yes_prob=_kalshi_price(raw_last, cents),
                    spread=(ask - bid)
                    if bid is not None and ask is not None and ask >= bid
                    else None,
                    volume_24h=_venue_float(market.get("volume")),
                    liquidity=None,
                    open_interest=_venue_float(market.get("open_interest")),
                    ends_at=close_time if isinstance(close_time, str) else None,
                    status=market.get("status") if isinstance(market.get("status"), str) else None,
                    category=category if isinstance(category, str) else None,
                    venue_url=KALSHI_MARKET_URL.format(ticker=ticker)
                    if isinstance(ticker, str)
                    else "",
                )
            )
    return rows


def _filter_prediction_markets(
    rows: list[PredictionMarketRow],
    *,
    query: str | None,
    category: str | None,
    tab: str,
    limit: int,
) -> list[PredictionMarketRow]:
    """Client-side catalog filter/sort/slice (venue search params are unprobed)."""
    if query:
        needle = query.lower()
        rows = [row for row in rows if needle in row.title.lower()]
    if category:
        needle = category.lower()
        rows = [row for row in rows if row.category is not None and needle in row.category.lower()]
    if tab == "ending_soon":
        rows = sorted(rows, key=lambda row: (row.ends_at is None, row.ends_at or ""))
    elif tab == "top":
        rows = sorted(rows, key=lambda row: (row.volume_24h is None, -(row.volume_24h or 0.0)))
    return rows[:limit]


_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag(name: str, *, default: bool) -> bool:
    """Resolve an env kill switch, failing closed for unrecognized values.

    Only ``1``/``true``/``yes``/``on`` (case-insensitive) enable the family. Any
    other non-empty value - including a typo like ``ture`` - leaves it disabled
    rather than silently ON.
    """
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUTHY_ENV_VALUES


def gloomberb_enabled() -> bool:
    """Resolve the family kill switch from env (``GLOOMBERB_ENABLED``, default ON).

    The same predicate ``GloomberbClient`` resolves at construction. Exposed so
    the in-process agent surface can stop *advertising* a disabled family rather
    than registering schemas whose every call returns the typed disabled
    envelope (#4146 review F1).
    """
    return _env_flag(GLOOMBERB_ENABLED_ENV, default=True)


def _parse_retry_after(value: str | None) -> float | None:
    """Seconds from a ``Retry-After`` header, or None when absent/unparseable.

    Only the delta-seconds form is honored; an HTTP-date form is ignored (the
    header is still surfaced in the typed error message).
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


# Plan-gated routes answer with a non-JSON text body ("Pro plan required",
# `/cloud/transcripts`), sometimes with a non-auth HTTP status, or with a
# 200 `status=unsupported` envelope whose reasonCode is `PRO_REQUIRED`
# (`/market/screener`). These markers route either shape to the typed
# `pro_required` error (distinct from `auth_required`: the caller has a
# session, it just is not entitled) instead of a generic upstream error or an
# empty success.
_PRO_PLAN_MARKERS: tuple[str, ...] = (
    "pro plan",
    "plan required",
    "upgrade",
    "subscription",
    "pro_required",
    "pro required",
)


def _plan_required_error(text: str) -> DigifetchError | None:
    """Typed `pro_required` when *text* reads as an upstream plan gate."""
    normalized = " ".join((text or "").split())
    if not normalized:
        return None
    lowered = normalized.lower()
    if not any(marker in lowered for marker in _PRO_PLAN_MARKERS):
        return None
    return DigifetchError(
        code="pro_required",
        message=(
            "This Gloomberb endpoint requires a Pro plan (the session cookie is "
            f"not entitled; upstream said: {normalized[:200]!r})"
        ),
        retryable=False,
    )


class _UpstreamServerError(RuntimeError):
    """A wire 5xx, wrapped so ``with_retry`` retries it without retrying 4xx."""


# The 13F routes proxy their service's 4xx as a wire 5xx whose text body names
# the real outcome (`Forms13F 400 for /holders`, live-verified). The inner
# status is the deterministic one: a proxied 4xx is bad input, not degradation.
_PROXY_STATUS_RE = re.compile(r"^Forms13F\s+(\d{3})\s+for\s+/")


def _parse_proxy_status(text: str) -> int | None:
    """Site-specific upstream status from a proxied 13F failure body, or None."""
    match = _PROXY_STATUS_RE.match((text or "").strip())
    return int(match[1]) if match else None


class _ProxyStatusError(RuntimeError):
    """A site-specific upstream 4xx proxied as a wire 5xx.

    Deliberately outside ``RETRYABLE_EXCEPTIONS`` so ``with_retry`` surfaces it
    immediately, and the caller maps it to a non-retryable ``invalid_input``
    without recording a breaker failure.
    """

    def __init__(self, status: int) -> None:
        super().__init__(f"Forms13F {status}")
        self.status = status


# Narrow retry classes: timeouts/connection faults and wire 5xx only. 401/404
# and every other 4xx propagate untouched (§5.5).
RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.TransportError,
    _UpstreamServerError,
)


class _RawResponse(NamedTuple):
    """The parts of a wire response the client needs after status mapping."""

    status: str
    data: Any
    reason_code: str | None
    stale: bool
    provider_meta: Mapping[str, Any]
    as_of: str | None
    currency: str | None


EnvT = TypeVar("EnvT", bound=DigifetchEnvelope[Any])
InputT = TypeVar("InputT", bound=BaseModel)


def _format_validation_error(exc: ValidationError, limit: int = 3) -> str:
    parts: list[str] = []
    errors = exc.errors()
    for error in errors[:limit]:
        location = ".".join(str(part) for part in error.get("loc", ()))
        parts.append(f"{location}: {error.get('msg')}")
    text = "; ".join(parts) or str(exc)
    if len(errors) > limit:
        text += f" (+{len(errors) - limit} more)"
    return text


def _coerce_earnings_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def yfinance_earnings_events(symbol: str) -> list[EarningsEvent]:
    """Default Yahoo earnings provider for ``digifetch_earnings_calendar``.

    Uses ``yfinance``'s calendar dict (no pandas frame on this path). The import
    is lazy: yfinance is an existing digiquant extra, not a hard dependency of
    this package's import path.
    """
    import yfinance as yf  # type: ignore[import-not-found]

    calendar_data = yf.Ticker(symbol).calendar or {}
    raw_dates = calendar_data.get("Earnings Date") or []
    eps_estimate = nz.finite_number(calendar_data.get("Earnings Average"))
    events: list[EarningsEvent] = []
    for value in raw_dates:
        earnings_date = _coerce_earnings_date(value)
        if earnings_date is None:
            continue
        events.append(
            EarningsEvent(symbol=symbol, earnings_date=earnings_date, eps_estimate=eps_estimate)
        )
    return events


class GloomberbClient:
    """Synchronous Gloomberb Cloud client returning typed envelopes.

    Args:
        fetcher:          Transport (tests inject a MockTransport-backed
                          :class:`digifetch.HttpFetcher`). A default fetcher is
                          created and owned by the client when omitted.
        base_url:         API root; defaults to ``https://api.gloom.sh``.
        enabled:          Kill switch; ``None`` reads ``GLOOMBERB_ENABLED``
                          (default ON). ``False`` makes every call return a
                          typed ``upstream_error`` envelope without any request.
        session_cookie:   Optional Gloom session cookie; ``None`` reads
                          ``GLOOMBERB_SESSION_COOKIE``. Accepts either a bare
                          token or ``name=value``. Never logged.
        rate_limiter:     Minimum-interval gate (default 0.5s).
        retry_policy:     Composable retry policy; narrowed to timeouts/5xx.
        cache_ttl:        Seconds an envelope stays fresh (900s default).
        cache_max_entries: Upper bound on cached envelopes (oldest evicted first).
        circuit_failure_threshold: Consecutive failures that open the breaker.
        circuit_reset_seconds:     Seconds before a half-open probe is allowed.
        max_retry_after_seconds:   Upper bound on the 429 Retry-After wait; a
                                   larger value is surfaced but not slept.
        monotonic:        Monotonic clock for cache/breaker (injected for tests).
        now:              Wall clock for ``fetched_at`` (injected for tests).
        sleep:            Blocking sleep used for a bounded Retry-After wait
                          (injected for tests; never called with a literal).
        earnings_provider: Yahoo-backed earnings callable (injected for tests).
    """

    def __init__(
        self,
        *,
        fetcher: HttpFetcher | None = None,
        base_url: str = GLOOMBERB_BASE_URL,
        enabled: bool | None = None,
        session_cookie: str | None = None,
        rate_limiter: RateLimiter | None = None,
        retry_policy: RetryPolicy | None = None,
        cache_ttl: float = DEFAULT_CACHE_TTL_SECONDS,
        cache_max_entries: int = DEFAULT_CACHE_MAX_ENTRIES,
        circuit_failure_threshold: int = DEFAULT_CIRCUIT_FAILURE_THRESHOLD,
        circuit_reset_seconds: float = DEFAULT_CIRCUIT_RESET_SECONDS,
        max_retry_after_seconds: float = DEFAULT_MAX_RETRY_AFTER_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        earnings_provider: Callable[[str], list[EarningsEvent]] | None = None,
    ) -> None:
        if fetcher is not None:
            self._fetcher = fetcher
            self._owns_fetcher = False
        else:
            self._fetcher = HttpFetcher(headers=DEFAULT_HEADERS)
            self._owns_fetcher = True
        self._base_url = base_url.rstrip("/")
        self._enabled = enabled if enabled is not None else gloomberb_enabled()
        if session_cookie is None:
            env_cookie = os.environ.get(GLOOMBERB_SESSION_COOKIE_ENV, "").strip()
            self._session_cookie: str | None = env_cookie or None
        else:
            self._session_cookie = session_cookie.strip() or None
        self._rate_limiter = rate_limiter or RateLimiter(DEFAULT_MIN_INTERVAL_SECONDS)
        self._retry_policy = retry_policy or RetryPolicy(
            attempts=3,
            base_delay=0.5,
            max_delay=5.0,
            retry_on=RETRYABLE_EXCEPTIONS,
        )
        self._cache_ttl = cache_ttl
        self._cache_max_entries = max(1, cache_max_entries)
        self._circuit_failure_threshold = max(1, circuit_failure_threshold)
        self._circuit_reset_seconds = circuit_reset_seconds
        self._max_retry_after_seconds = max_retry_after_seconds
        self._monotonic = monotonic
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._sleep = sleep
        self._earnings_provider = earnings_provider or yfinance_earnings_events
        self._cache: dict[tuple[str, str], tuple[float, DigifetchEnvelope[Any]]] = {}
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        # One shared client is used by parallel LangGraph nodes (#4146): the
        # cache dict and the breaker counters need their own locks. Never hold
        # both at once (``_cached`` and ``_record_*`` never nest).
        self._cache_lock = threading.Lock()
        self._breaker_lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------

    @property
    def enabled(self) -> bool:
        """Kill-switch state (default ON)."""
        return self._enabled

    def close(self) -> None:
        """Close the transport, but only when this client created it."""
        if self._owns_fetcher:
            self._fetcher.close()

    def __enter__(self) -> GloomberbClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- public tools (§5.1) ----------------------------------------------

    def quote(self, request: QuoteInput | Mapping[str, Any]) -> QuoteEnvelope:
        parsed = self._validate_input(QuoteInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(QuoteEnvelope, parsed)
        if not self._enabled:
            return self._disabled(QuoteEnvelope)

        def produce() -> QuoteEnvelope:
            params: dict[str, Any] = {"symbol": parsed.symbol}
            if parsed.exchange:
                params["exchange"] = parsed.exchange
            raw = self._request_json("GET", ENDPOINTS["quote"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(QuoteEnvelope, raw)
            result = self._data_or_error(raw, f"Cloud quotes are unavailable for {parsed.symbol}")
            if isinstance(result, DigifetchError):
                return self._error_envelope(QuoteEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "quote")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(QuoteEnvelope, payload)
            normalized = self._normalize(nz.normalize_quote, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(QuoteEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return QuoteEnvelope(
                data=QuoteResult(quote=normalized),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("quote", parsed, produce)

    def quotes_batch(self, request: QuotesBatchInput | Mapping[str, Any]) -> QuotesBatchEnvelope:
        parsed = self._validate_input(QuotesBatchInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(QuotesBatchEnvelope, parsed)
        if not self._enabled:
            return self._disabled(QuotesBatchEnvelope)

        def produce() -> QuotesBatchEnvelope:
            body = {
                "targets": [{"symbol": symbol} for symbol in parsed.symbols],
                "mode": "cache-first",
            }
            raw = self._request_json("POST", ENDPOINTS["quotes_batch"], body=body)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(QuotesBatchEnvelope, raw)
            result = self._data_or_error(raw, "Cloud quotes are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(QuotesBatchEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "quotes batch")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(QuotesBatchEnvelope, payload)
            items = payload.get("items")
            quotes = nz.normalize_quotes_batch_items(items if isinstance(items, list) else [])
            any_item_stale = any(
                isinstance(item, Mapping) and item.get("stale") is True
                for item in (items if isinstance(items, list) else [])
            )
            fresh = self._freshness(raw, payload, extra_stale=any_item_stale)
            return QuotesBatchEnvelope(
                data=QuotesBatchResult(quotes=quotes),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("quotes_batch", parsed, produce)

    def price_history(self, request: PriceHistoryInput | Mapping[str, Any]) -> PriceHistoryEnvelope:
        parsed = self._validate_input(PriceHistoryInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(PriceHistoryEnvelope, parsed)
        if not self._enabled:
            return self._disabled(PriceHistoryEnvelope)

        def produce() -> PriceHistoryEnvelope:
            # #4100: an explicit date window (mutually exclusive with `range`
            # at the model) maps to the probe-verified combination —
            # rangeKey=ALL + startDate/endDate serves bars beyond Cloud's
            # declared 5Y cap (live: 610 weekly bars back to 2015-01-05).
            windowed = parsed.start_date is not None or parsed.end_date is not None
            params: dict[str, Any] = {
                "symbol": parsed.symbol,
                "interval": nz.to_cloud_interval(parsed.resolution),
                "rangeKey": "ALL" if windowed else parsed.range,
            }
            if parsed.start_date is not None:
                params["startDate"] = parsed.start_date.isoformat()
            if parsed.end_date is not None:
                params["endDate"] = parsed.end_date.isoformat()
            if parsed.exchange:
                params["exchange"] = parsed.exchange
            raw = self._request_json("GET", ENDPOINTS["history"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(PriceHistoryEnvelope, raw)
            message = f"Cloud chart data is unavailable for {parsed.symbol}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(PriceHistoryEnvelope, result)
            data, warnings = result
            if not isinstance(data, list):
                return self._error_envelope(
                    PriceHistoryEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="history returned an unexpected payload",
                        retryable=False,
                    ),
                )
            exchange = str(parsed.exchange or raw.provider_meta.get("normalizedExchange") or "")
            currency_unit = nz.resolve_currency_unit(
                raw.currency if raw.currency is not None else raw.provider_meta.get("currency")  # type: ignore[arg-type]
            )
            timezone_name = raw.provider_meta.get("timezone")
            bars = nz.normalize_bars(
                data,
                resolution=parsed.resolution,
                exchange=exchange,
                divisor=currency_unit.divisor,
                timezone_name=str(timezone_name) if timezone_name else None,
            )
            upstream = (
                str(raw.provider_meta.get("provider") or raw.provider_meta.get("upstream") or "")
                .strip()
                .lower()
            )
            if nz.is_intraday_resolution(parsed.resolution) and upstream != "yahoo":
                if nz.is_malformed_intraday_history(bars):
                    return self._error_envelope(
                        PriceHistoryEnvelope,
                        DigifetchError(
                            code="upstream_error",
                            message=f"Cloud chart data failed OHLC validation for {parsed.symbol}",
                            retryable=False,
                        ),
                    )
            fresh = self._freshness(raw)
            metadata = PriceHistoryMetadata(
                symbol=parsed.symbol,
                exchange=exchange,
                resolution=parsed.resolution,
                range=parsed.range or "",
                bar_count=len(bars),
                timezone=str(timezone_name) if timezone_name else None,
                # Canonical unit: bars were divided by the subunit divisor
                # above, so metadata must not keep "GBp" while bars are GBP.
                currency=currency_unit.currency or None,
                upstream_provider=upstream or None,
            )
            return PriceHistoryEnvelope(
                data=PriceHistoryResult(bars=bars, metadata=metadata),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("price_history", parsed, produce)

    def ticker_financials(
        self, request: TickerFinancialsInput | Mapping[str, Any]
    ) -> TickerFinancialsEnvelope:
        parsed = self._validate_input(TickerFinancialsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TickerFinancialsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TickerFinancialsEnvelope)

        def produce() -> TickerFinancialsEnvelope:
            params: dict[str, Any] = {"symbol": parsed.symbol}
            if parsed.exchange:
                params["exchange"] = parsed.exchange
            if parsed.extended_statements:
                params["statementHistory"] = "extended"
            raw = self._request_json("GET", ENDPOINTS["financials"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TickerFinancialsEnvelope, raw)
            message = f"Cloud financials are unavailable for {parsed.symbol}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(TickerFinancialsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "financials")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(TickerFinancialsEnvelope, payload)
            normalized = self._normalize(nz.normalize_financials, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(TickerFinancialsEnvelope, normalized)
            quote_payload = payload.get("quote")
            fresh = self._freshness(
                raw,
                quote_payload if isinstance(quote_payload, Mapping) else None,
            )
            return TickerFinancialsEnvelope(
                data=TickerFinancialsResult(financials=normalized),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("ticker_financials", parsed, produce)

    def options_chain(self, request: OptionsChainInput | Mapping[str, Any]) -> OptionsChainEnvelope:
        parsed = self._validate_input(OptionsChainInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(OptionsChainEnvelope, parsed)
        if not self._enabled:
            return self._disabled(OptionsChainEnvelope)

        def produce() -> OptionsChainEnvelope:
            params: dict[str, Any] = {"symbol": parsed.symbol}
            if parsed.exchange:
                params["exchange"] = parsed.exchange
            if parsed.expiration is not None:
                params["expirationDate"] = str(parsed.expiration)
            raw = self._request_json("GET", ENDPOINTS["options"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(OptionsChainEnvelope, raw)
            message = f"Cloud options chains are unavailable for {parsed.symbol}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(OptionsChainEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "options chain")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(OptionsChainEnvelope, payload)
            normalized = self._normalize(nz.normalize_options_chain, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(OptionsChainEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return OptionsChainEnvelope(
                data=OptionsChainResult(chain=normalized),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("options_chain", parsed, produce)

    def sec_filings(self, request: SecFilingsInput | Mapping[str, Any]) -> SecFilingsEnvelope:
        parsed = self._validate_input(SecFilingsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SecFilingsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SecFilingsEnvelope)

        def produce() -> SecFilingsEnvelope:
            if parsed.what == "filings":
                message = f"Cloud SEC filings are unavailable for {parsed.ticker}"
                raw = self._request_json(
                    "GET",
                    ENDPOINTS["sec_filings"],
                    params={"ticker": parsed.ticker, "limit": str(parsed.count), "offset": "0"},
                )
            else:
                message = "Cloud SEC filing documents are unavailable"
                path = (
                    ENDPOINTS["sec_filing_documents"]
                    if parsed.what == "documents"
                    else ENDPOINTS["sec_filing_content"]
                )
                params: dict[str, Any] = {}
                if parsed.cik:
                    params["cik"] = parsed.cik
                if parsed.accession:
                    params["accession"] = parsed.accession
                if parsed.form:
                    params["form"] = parsed.form
                raw = self._request_json("GET", path, params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(SecFilingsEnvelope, raw)
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(SecFilingsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, f"SEC {parsed.what}")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(SecFilingsEnvelope, payload)
            if parsed.what == "filings":
                filings = self._normalize(nz.normalize_sec_filings, payload)
                if isinstance(filings, DigifetchError):
                    return self._error_envelope(SecFilingsEnvelope, filings)
                content = SecFilingsResult(filings=filings)
            elif parsed.what == "documents":
                documents = self._normalize(nz.normalize_sec_documents, payload)
                if isinstance(documents, DigifetchError):
                    return self._error_envelope(SecFilingsEnvelope, documents)
                content = SecFilingsResult(documents=documents)
            else:
                raw_content = payload.get("content")
                content = SecFilingsResult(
                    content=raw_content if isinstance(raw_content, str) else None
                )
            fresh = self._freshness(raw)
            return SecFilingsEnvelope(
                data=content,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("sec_filings", parsed, produce)

    def holders(self, request: HoldersInput | Mapping[str, Any]) -> HoldersEnvelope:
        parsed = self._validate_input(HoldersInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(HoldersEnvelope, parsed)
        if not self._enabled:
            return self._disabled(HoldersEnvelope)

        def produce() -> HoldersEnvelope:
            raw = self._request_json(
                "GET", ENDPOINTS["holders"], params={"symbol": parsed.symbol}, gated=True
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(HoldersEnvelope, raw)
            message = f"Cloud holders are unavailable for {parsed.symbol}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(HoldersEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "holders")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(HoldersEnvelope, payload)
            holders = self._normalize(nz.normalize_holders, payload, parsed.owner_type)
            if isinstance(holders, DigifetchError):
                return self._error_envelope(HoldersEnvelope, holders)
            fresh = self._freshness(raw)
            return HoldersEnvelope(
                data=HoldersResult(holders=holders),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("holders", parsed, produce)

    def analyst_research(
        self, request: AnalystResearchInput | Mapping[str, Any]
    ) -> AnalystResearchEnvelope:
        parsed = self._validate_input(AnalystResearchInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(AnalystResearchEnvelope, parsed)
        if not self._enabled:
            return self._disabled(AnalystResearchEnvelope)

        def produce() -> AnalystResearchEnvelope:
            raw = self._request_json(
                "GET", ENDPOINTS["analyst"], params={"symbol": parsed.symbol}, gated=True
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(AnalystResearchEnvelope, raw)
            message = f"Cloud analyst research is unavailable for {parsed.symbol}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(AnalystResearchEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "analyst research")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(AnalystResearchEnvelope, payload)
            normalized = self._normalize(nz.normalize_analyst_research, payload, parsed.limit)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(AnalystResearchEnvelope, normalized)
            fresh = self._freshness(raw)
            return AnalystResearchEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("analyst_research", parsed, produce)

    def corporate_actions(
        self, request: CorporateActionsInput | Mapping[str, Any]
    ) -> CorporateActionsEnvelope:
        parsed = self._validate_input(CorporateActionsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CorporateActionsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CorporateActionsEnvelope)

        def produce() -> CorporateActionsEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["corporate_actions"],
                params={"symbol": parsed.symbol},
                gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CorporateActionsEnvelope, raw)
            message = f"Cloud corporate actions are unavailable for {parsed.symbol}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(CorporateActionsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "corporate actions")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(CorporateActionsEnvelope, payload)
            actions = self._normalize(nz.normalize_corporate_actions, payload)
            if isinstance(actions, DigifetchError):
                return self._error_envelope(CorporateActionsEnvelope, actions)
            fresh = self._freshness(raw)
            return CorporateActionsEnvelope(
                data=CorporateActionsResult(actions=actions),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("corporate_actions", parsed, produce)

    def earnings_calendar(
        self, request: EarningsCalendarInput | Mapping[str, Any]
    ) -> EarningsCalendarEnvelope:
        """Yahoo-backed earnings calendar (no Cloud route; §5.1)."""
        parsed = self._validate_input(EarningsCalendarInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(EarningsCalendarEnvelope, parsed)
        if not self._enabled:
            return self._disabled(EarningsCalendarEnvelope)

        def produce() -> EarningsCalendarEnvelope:
            today = self._now().date()
            horizon = today + timedelta(days=parsed.horizon_days)
            events: list[EarningsEvent] = []
            warnings: list[str] = []
            for symbol in parsed.symbols:
                try:
                    symbol_events = self._earnings_provider(symbol)
                except ImportError as exc:
                    return self._error_envelope(
                        EarningsCalendarEnvelope,
                        DigifetchError(
                            code="upstream_error",
                            message=f"yfinance is unavailable for the Yahoo earnings path: {exc}",
                            retryable=False,
                        ),
                    )
                except Exception as exc:  # Yahoo is brittle; fail soft per symbol
                    warnings.append(f"{symbol}: {exc}")
                    continue
                events.extend(
                    event for event in symbol_events if today <= event.earnings_date <= horizon
                )
            return EarningsCalendarEnvelope(
                data=EarningsCalendarResult(events=events),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("earnings_calendar", parsed, produce)

    def exchange_rate(self, request: ExchangeRateInput | Mapping[str, Any]) -> ExchangeRateEnvelope:
        parsed = self._validate_input(ExchangeRateInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ExchangeRateEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ExchangeRateEnvelope)

        def produce() -> ExchangeRateEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["exchange_rate"],
                params={"fromCurrency": parsed.from_currency},
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ExchangeRateEnvelope, raw)
            message = f"Cloud exchange rate is unavailable for {parsed.from_currency}"
            result = self._data_or_error(raw, message)
            if isinstance(result, DigifetchError):
                return self._error_envelope(ExchangeRateEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "exchange rate")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(ExchangeRateEnvelope, payload)
            fresh = self._freshness(raw, payload)
            normalized = self._normalize(
                nz.normalize_exchange_rate,
                payload,
                response_as_of=raw.as_of,
                freshness=fresh,
            )
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(ExchangeRateEnvelope, normalized)
            return ExchangeRateEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("exchange_rate", parsed, produce)

    def search(self, request: SearchInput | Mapping[str, Any]) -> SearchEnvelope:
        parsed = self._validate_input(SearchInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SearchEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SearchEnvelope)

        def produce() -> SearchEnvelope:
            # Spec §5.1: clamp above the wrapper cap and flag it in the result.
            limit = min(parsed.limit, SEARCH_LIMIT_CAP)
            raw = self._request_json(
                "GET",
                ENDPOINTS["search"],
                params={"q": parsed.query, "limit": str(limit)},
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(SearchEnvelope, raw)
            result = self._data_or_error(raw, "Cloud search is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(SearchEnvelope, result)
            data, warnings = result
            results = self._normalize(nz.normalize_search_results, data)
            if isinstance(results, DigifetchError):
                return self._error_envelope(SearchEnvelope, results)
            fresh = self._freshness(raw)
            return SearchEnvelope(
                data=SearchResult(results=results, limit_clamped=parsed.limit > SEARCH_LIMIT_CAP),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("search", parsed, produce)

    def news(self, request: NewsInput | Mapping[str, Any]) -> NewsEnvelope:
        parsed = self._validate_input(NewsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(NewsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(NewsEnvelope)

        def produce() -> NewsEnvelope:
            if parsed.story_id:
                path = f"{ENDPOINTS['news']}/{quote(parsed.story_id, safe='')}"
                raw = self._request_json("GET", path)
            else:
                params: dict[str, Any] = {"feed": parsed.feed, "limit": str(parsed.limit)}
                if parsed.ticker:
                    params["tickers"] = parsed.ticker
                raw = self._request_json("GET", ENDPOINTS["news"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(NewsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud news is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(NewsEnvelope, result)
            data, warnings = result
            if parsed.story_id:
                payload = self._as_mapping(data, "news story")
                if isinstance(payload, DigifetchError):
                    return self._error_envelope(NewsEnvelope, payload)
                item = self._normalize(nz.normalize_news_item, payload)
                if isinstance(item, DigifetchError):
                    return self._error_envelope(NewsEnvelope, item)
                items = [item]
            else:
                payload = self._as_mapping(data, "news")
                if isinstance(payload, DigifetchError):
                    return self._error_envelope(NewsEnvelope, payload)
                items = self._normalize(nz.normalize_news_list, payload)
                if isinstance(items, DigifetchError):
                    return self._error_envelope(NewsEnvelope, items)
            fresh = self._freshness(raw)
            return NewsEnvelope(
                data=NewsResult(items=items),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("news", parsed, produce)

    # -- coverage expansion (#4110 phase 1) --------------------------------

    def econ_calendar(
        self, request: EconCalendarInput | Mapping[str, Any] | None = None
    ) -> EconCalendarEnvelope:
        """Structured economic calendar (anonymous; direct array payload)."""
        parsed = self._validate_input(EconCalendarInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(EconCalendarEnvelope, parsed)
        if not self._enabled:
            return self._disabled(EconCalendarEnvelope)

        def produce() -> EconCalendarEnvelope:
            raw = self._request_json("GET", ENDPOINTS["econ_calendar"], allow_array=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(EconCalendarEnvelope, raw)
            result = self._data_or_error(raw, "Cloud econ calendar is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(EconCalendarEnvelope, result)
            data, warnings = result
            events = self._normalize(nz.normalize_econ_calendar, data)
            if isinstance(events, DigifetchError):
                return self._error_envelope(EconCalendarEnvelope, events)
            fresh = self._freshness(raw, extra_stale=self._rows_stale(data))
            return EconCalendarEnvelope(
                data=EconCalendarResult(events=events),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("econ_calendar", parsed, produce)

    def econ_series(self, request: EconSeriesInput | Mapping[str, Any]) -> EconSeriesEnvelope:
        """FRED-style macro series observations + metadata (anonymous)."""
        parsed = self._validate_input(EconSeriesInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(EconSeriesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(EconSeriesEnvelope)

        def produce() -> EconSeriesEnvelope:
            path = f"{ENDPOINTS['econ_series']}/{quote(parsed.series_id, safe='')}"
            raw = self._request_json(
                "GET",
                path,
                params={"limit": str(parsed.limit), "sortOrder": parsed.sort_order},
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(EconSeriesEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud econ series is unavailable for {parsed.series_id}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(EconSeriesEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "econ series")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(EconSeriesEnvelope, payload)
            normalized = self._normalize(nz.normalize_econ_series, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(EconSeriesEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return EconSeriesEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("econ_series", parsed, produce)

    def yield_curve(
        self, request: YieldCurveInput | Mapping[str, Any] | None = None
    ) -> YieldCurveEnvelope:
        """Treasury yield curve (anonymous; direct array payload)."""
        parsed = self._validate_input(YieldCurveInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(YieldCurveEnvelope, parsed)
        if not self._enabled:
            return self._disabled(YieldCurveEnvelope)

        def produce() -> YieldCurveEnvelope:
            raw = self._request_json("GET", ENDPOINTS["yield_curve"], allow_array=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(YieldCurveEnvelope, raw)
            result = self._data_or_error(raw, "Cloud yield curve is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(YieldCurveEnvelope, result)
            data, warnings = result
            points = self._normalize(nz.normalize_yield_curve, data)
            if isinstance(points, DigifetchError):
                return self._error_envelope(YieldCurveEnvelope, points)
            fresh = self._freshness(raw, extra_stale=self._rows_stale(data))
            return YieldCurveEnvelope(
                data=YieldCurveResult(points=points),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("yield_curve", parsed, produce)

    def cds(self, request: CdsInput | Mapping[str, Any]) -> CdsEnvelope:
        """DTCC PPD CDS trade tape (anonymous; `days` validated client-side)."""
        parsed = self._validate_input(CdsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CdsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CdsEnvelope)

        def produce() -> CdsEnvelope:
            params: dict[str, Any] = {"days": str(parsed.days), "limit": str(parsed.limit)}
            if parsed.issuer:
                params["issuer"] = parsed.issuer
            raw = self._request_json("GET", ENDPOINTS["cds"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CdsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud CDS trades are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(CdsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "CDS trades")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(CdsEnvelope, payload)
            trades = self._normalize(nz.normalize_cds_trades, payload)
            if isinstance(trades, DigifetchError):
                return self._error_envelope(CdsEnvelope, trades)
            fresh = self._freshness(raw, payload)
            return CdsEnvelope(
                data=CdsResult(
                    source=payload.get("source")
                    if isinstance(payload.get("source"), str)
                    else None,
                    as_of=raw.as_of
                    or (payload.get("asOf") if isinstance(payload.get("asOf"), str) else None),
                    trades=trades,
                ),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("cds", parsed, produce)

    def research_search(
        self, request: ResearchSearchInput | Mapping[str, Any]
    ) -> ResearchSearchEnvelope:
        """Full-text research search (session-gated; 401 → auth_required)."""
        parsed = self._validate_input(ResearchSearchInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ResearchSearchEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ResearchSearchEnvelope)

        def produce() -> ResearchSearchEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["research_search"],
                params={
                    "q": parsed.query,
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                },
                gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ResearchSearchEnvelope, raw)
            result = self._data_or_error(raw, "Cloud research search is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(ResearchSearchEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "research search")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(ResearchSearchEnvelope, payload)
            normalized = self._normalize(nz.normalize_research_search, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(ResearchSearchEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return ResearchSearchEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("research_search", parsed, produce)

    def congress_trades(
        self, request: CongressTradesInput | Mapping[str, Any] | None = None
    ) -> CongressTradesEnvelope:
        """US House disclosure trades (anonymous; upstream OCR path may 500)."""
        parsed = self._validate_input(CongressTradesInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CongressTradesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CongressTradesEnvelope)

        def produce() -> CongressTradesEnvelope:
            params: dict[str, Any] = {"limit": str(parsed.limit)}
            if parsed.year is not None:
                params["year"] = str(parsed.year)
            raw = self._request_json(
                "GET", ENDPOINTS["congress_trades"], params=params, allow_array=True
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CongressTradesEnvelope, raw)
            result = self._data_or_error(raw, "Cloud congress trades are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(CongressTradesEnvelope, result)
            data, warnings = result
            trades = self._normalize(nz.normalize_congress_trades, data)
            if isinstance(trades, DigifetchError):
                return self._error_envelope(CongressTradesEnvelope, trades)
            fresh = self._freshness(
                raw,
                data,
                extra_stale=self._rows_stale(
                    data.get("trades") if isinstance(data, Mapping) else data
                ),
            )
            return CongressTradesEnvelope(
                data=CongressTradesResult(trades=trades),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("congress_trades", parsed, produce)

    def transcripts(self, request: TranscriptsInput | Mapping[str, Any]) -> TranscriptsEnvelope:
        """Earnings-call transcripts (session-gated; requires Gloomberb Pro).

        A free (email-verified) session answers a non-JSON "Pro plan required"
        body; the client maps that to a typed ``pro_required`` instead of an
        empty success or a generic upstream error.
        """
        parsed = self._validate_input(TranscriptsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TranscriptsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TranscriptsEnvelope)

        def produce() -> TranscriptsEnvelope:
            if parsed.transcript_id:
                path = f"{ENDPOINTS['transcripts']}/{quote(parsed.transcript_id, safe='')}"
                raw = self._request_json("GET", path, gated=True, pro_gated=True)
            else:
                raw = self._request_json(
                    "GET",
                    ENDPOINTS["transcripts"],
                    params={"ticker": parsed.ticker, "limit": str(parsed.limit)},
                    gated=True,
                    pro_gated=True,
                )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TranscriptsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud transcripts are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(TranscriptsEnvelope, result)
            data, warnings = result
            if parsed.transcript_id:
                row = self._normalize(nz.normalize_transcript_detail, data, parsed.transcript_id)
                if isinstance(row, DigifetchError):
                    return self._error_envelope(TranscriptsEnvelope, row)
                rows = [row]
                list_rows: Any = data
            else:
                rows = self._normalize(nz.normalize_transcripts, data)
                if isinstance(rows, DigifetchError):
                    return self._error_envelope(TranscriptsEnvelope, rows)
                # The live list payload wraps its rows under `calls`; `transcripts`
                # is accepted for a wrapped variant.
                list_rows = (
                    (data.get("calls") or data.get("transcripts"))
                    if isinstance(data, Mapping)
                    else data
                )
            fresh = self._freshness(
                raw,
                data,
                extra_stale=self._rows_stale(list_rows),
            )
            return TranscriptsEnvelope(
                data=TranscriptsResult(transcripts=rows),
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("transcripts", parsed, produce)

    # -- coverage expansion (#4110 phase 2) --------------------------------

    def statements(self, request: StatementsInput | Mapping[str, Any]) -> StatementsEnvelope:
        """Annual/quarterly statement rows (session-gated; direct envelope)."""
        parsed = self._validate_input(StatementsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(StatementsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(StatementsEnvelope)

        def produce() -> StatementsEnvelope:
            params: dict[str, Any] = {
                "symbol": parsed.symbol,
                "period": parsed.period,
            }
            if parsed.exchange:
                params["exchange"] = parsed.exchange
            raw = self._request_json("GET", ENDPOINTS["statements"], params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(StatementsEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud statements are unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(StatementsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "statements")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(StatementsEnvelope, payload)
            normalized = self._normalize(nz.normalize_statements, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(StatementsEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return StatementsEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("statements", parsed, produce)

    def ticker_tweets(self, request: TickerTweetsInput | Mapping[str, Any]) -> TweetsEnvelope:
        """Recent X/Twitter posts for one ticker (session-gated; direct payload)."""
        parsed = self._validate_input(TickerTweetsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TweetsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TweetsEnvelope)

        def produce() -> TweetsEnvelope:
            params: dict[str, Any] = {
                "ticker": parsed.ticker,
                "limit": str(parsed.limit),
                "includeReplies": "true" if parsed.include_replies else "false",
            }
            if parsed.hours is not None:
                params["hours"] = str(parsed.hours)
            raw = self._request_json("GET", ENDPOINTS["tweets"], params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TweetsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud tweets are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(TweetsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "tweets")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(TweetsEnvelope, payload)
            cutoff = (
                self._now() - timedelta(hours=parsed.hours) if parsed.hours is not None else None
            )
            normalized = self._normalize(
                nz.normalize_tweets, payload, parsed.limit, min_created_at=cutoff
            )
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(TweetsEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return TweetsEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("ticker_tweets", parsed, produce)

    def tweet_search(self, request: TweetSearchInput | Mapping[str, Any]) -> TweetsEnvelope:
        """Search X/Twitter posts by query (session-gated; direct payload)."""
        parsed = self._validate_input(TweetSearchInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TweetsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TweetsEnvelope)

        def produce() -> TweetsEnvelope:
            params: dict[str, Any] = {
                "query": parsed.query,
                "queryType": parsed.query_type,
                "limit": str(parsed.limit),
            }
            if parsed.hours is not None:
                params["hours"] = str(parsed.hours)
            raw = self._request_json("GET", ENDPOINTS["tweet_search"], params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TweetsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud tweet search is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(TweetsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "tweet search")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(TweetsEnvelope, payload)
            cutoff = (
                self._now() - timedelta(hours=parsed.hours) if parsed.hours is not None else None
            )
            normalized = self._normalize(
                nz.normalize_tweets, payload, parsed.limit, min_created_at=cutoff
            )
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(TweetsEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return TweetsEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("tweet_search", parsed, produce)

    def venues(self, request: VenuesInput | Mapping[str, Any] | None = None) -> VenuesEnvelope:
        """Exchange venue metadata (anonymous; enveloped payload)."""
        parsed = self._validate_input(VenuesInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(VenuesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(VenuesEnvelope)

        def produce() -> VenuesEnvelope:
            raw = self._request_json("GET", ENDPOINTS["venues"])
            if isinstance(raw, DigifetchError):
                return self._error_envelope(VenuesEnvelope, raw)
            result = self._data_or_error(raw, "Cloud venues are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(VenuesEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "venues")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(VenuesEnvelope, payload)
            normalized = self._normalize(nz.normalize_venues, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(VenuesEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return VenuesEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("venues", parsed, produce)

    # -- coverage expansion (#4110 phase 4a) --------------------------------

    def saved_searches(
        self, request: SavedSearchesInput | Mapping[str, Any] | None = None
    ) -> SavedSearchesEnvelope:
        """The signed-in session's saved searches (session-gated).

        Without ``GLOOMBERB_SESSION_COOKIE`` this returns a typed
        ``auth_required`` and makes no request (zero-HTTP gate).
        """
        parsed = self._validate_input(SavedSearchesInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SavedSearchesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SavedSearchesEnvelope)

        def produce() -> SavedSearchesEnvelope:
            raw = self._request_json("GET", ENDPOINTS["saved_searches"], gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(SavedSearchesEnvelope, raw)
            result = self._data_or_error(raw, "Cloud saved searches are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(SavedSearchesEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_saved_searches, data)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(SavedSearchesEnvelope, normalized)
            fresh = self._freshness(raw, data)
            return SavedSearchesEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("saved_searches", parsed, produce)

    def screener(self, request: ScreenerInput | Mapping[str, Any]) -> ScreenerEnvelope:
        """Market screener (session-gated; **requires Gloomberb Pro**).

        A free session answers ``{"status": "unsupported", "reasonCode":
        "PRO_REQUIRED"}`` with HTTP 200; ``pro_gated`` maps that (like the 402
        text body) to a typed ``pro_required`` instead of ``not_found``.
        """
        parsed = self._validate_input(ScreenerInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ScreenerEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ScreenerEnvelope)

        def produce() -> ScreenerEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["screener"],
                params={
                    "category": parsed.category,
                    "count": str(parsed.count),
                    "mode": parsed.mode,
                },
                gated=True,
                pro_gated=True,
                allow_array=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ScreenerEnvelope, raw)
            result = self._data_or_error(raw, "Cloud screener is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(ScreenerEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_screener, data, parsed.category)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(ScreenerEnvelope, normalized)
            fresh = self._freshness(raw, data, extra_stale=self._rows_stale(data))
            return ScreenerEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("screener", parsed, produce)

    def thirteen_f_funds(
        self, request: ThirteenFFundsInput | Mapping[str, Any]
    ) -> Funds13FEnvelope:
        """13F funds: search / top funds / ticker map / CUSIP holders (anonymous)."""
        parsed = self._validate_input(ThirteenFFundsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(Funds13FEnvelope, parsed)
        if not self._enabled:
            return self._disabled(Funds13FEnvelope)

        def produce() -> Funds13FEnvelope:
            if parsed.what == "search":
                path = ENDPOINTS["13f_funds"]
                params: dict[str, Any] = {
                    "name": parsed.query,
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                }
            elif parsed.what == "top":
                path = ENDPOINTS["13f_topfunds"]
                params = {
                    "quarter": parsed.quarter,
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                }
            elif parsed.what == "tickers":
                path = ENDPOINTS["13f_tickers"]
                params = {"tickers": ",".join(parsed.tickers)}
            else:
                path = ENDPOINTS["13f_holders"]
                params = {"cusip": parsed.cusip, "period_of_report": parsed.period_of_report}
            raw = self._request_json("GET", path, params=params, allow_array=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(Funds13FEnvelope, raw)
            result = self._data_or_error(raw, "Cloud 13F funds are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(Funds13FEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_funds_13f, data, parsed.what)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(Funds13FEnvelope, normalized)
            fresh = self._freshness(raw, data, extra_stale=self._rows_stale(data))
            return Funds13FEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("thirteen_f_funds", parsed, produce)

    def thirteen_f_holdings(
        self, request: ThirteenFHoldingsInput | Mapping[str, Any]
    ) -> Holdings13FEnvelope:
        """13F filings / fund forms / one form's holdings (anonymous)."""
        parsed = self._validate_input(ThirteenFHoldingsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(Holdings13FEnvelope, parsed)
        if not self._enabled:
            return self._disabled(Holdings13FEnvelope)

        def produce() -> Holdings13FEnvelope:
            if parsed.what == "filings":
                path = ENDPOINTS["13f_filings"]
                params: dict[str, Any] = {
                    "from": parsed.from_date,
                    "to": parsed.to_date,
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                }
            elif parsed.what == "forms":
                path = ENDPOINTS["13f_forms"]
                params = {
                    "cik": parsed.cik,
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                }
                if parsed.from_date:
                    params["from"] = parsed.from_date
                if parsed.to_date:
                    params["to"] = parsed.to_date
            else:
                path = ENDPOINTS["13f_form"]
                params = {
                    "cik": parsed.cik,
                    "accession_number": parsed.accession_number,
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                }
            raw = self._request_json("GET", path, params=params, allow_array=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(Holdings13FEnvelope, raw)
            result = self._data_or_error(raw, "Cloud 13F holdings are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(Holdings13FEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_holdings_13f, data, parsed.what, parsed.limit)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(Holdings13FEnvelope, normalized)
            fresh = self._freshness(raw, data, extra_stale=self._rows_stale(data))
            return Holdings13FEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("thirteen_f_holdings", parsed, produce)

    # -- coverage expansion (#4110 phase 3) --------------------------------

    def shiller(self, request: ShillerInput | Mapping[str, Any] | None = None) -> ShillerEnvelope:
        """Robert Shiller's monthly valuation series (anonymous)."""
        parsed = self._validate_input(ShillerInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ShillerEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ShillerEnvelope)

        def produce() -> ShillerEnvelope:
            raw = self._request_json("GET", ENDPOINTS["shiller"])
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ShillerEnvelope, raw)
            result = self._data_or_error(raw, "Cloud Shiller data is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(ShillerEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "Shiller data")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(ShillerEnvelope, payload)
            normalized = self._normalize(nz.normalize_shiller, payload, parsed.limit)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(ShillerEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return ShillerEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("shiller", parsed, produce)

    def proxy_statements(
        self, request: ProxyStatementsInput | Mapping[str, Any]
    ) -> ProxyStatementsEnvelope:
        """Executive compensation proxies (anonymous public reads)."""
        parsed = self._validate_input(ProxyStatementsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ProxyStatementsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ProxyStatementsEnvelope)

        def produce() -> ProxyStatementsEnvelope:
            path = f"{ENDPOINTS['proxy_statements']}/{quote(parsed.ticker.upper(), safe='')}"
            if parsed.what == "statement":
                path = f"{path}/{parsed.year}"
            raw = self._request_json("GET", path)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ProxyStatementsEnvelope, raw)
            result = self._data_or_error(
                raw, f"Proxy statements are unavailable for {parsed.ticker}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(ProxyStatementsEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_proxy_statements, data, parsed.what)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(ProxyStatementsEnvelope, normalized)
            fresh = self._freshness(raw, data)
            return ProxyStatementsEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("proxy_statements", parsed, produce)

    def filing_events(self, request: FilingEventsInput | Mapping[str, Any]) -> FilingEventsEnvelope:
        """Classified 8-K filing events for one ticker (anonymous)."""
        parsed = self._validate_input(FilingEventsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(FilingEventsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(FilingEventsEnvelope)

        def produce() -> FilingEventsEnvelope:
            raw = self._request_json(
                "GET",
                f"{ENDPOINTS['filing_events']}/{quote(parsed.ticker.upper(), safe='')}",
                params={"limit": str(parsed.limit)},
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(FilingEventsEnvelope, raw)
            result = self._data_or_error(raw, f"Filing events are unavailable for {parsed.ticker}")
            if isinstance(result, DigifetchError):
                return self._error_envelope(FilingEventsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "filing events")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(FilingEventsEnvelope, payload)
            normalized = self._normalize(nz.normalize_filing_events, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(FilingEventsEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return FilingEventsEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("filing_events", parsed, produce)

    def risk_reports(self, request: RiskReportsInput | Mapping[str, Any]) -> RiskReportsEnvelope:
        """10-K risk-factor reports with the year-over-year diff (anonymous)."""
        parsed = self._validate_input(RiskReportsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(RiskReportsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(RiskReportsEnvelope)

        def produce() -> RiskReportsEnvelope:
            path = f"{ENDPOINTS['risk_reports']}/{quote(parsed.ticker.upper(), safe='')}"
            if parsed.what == "report":
                path = f"{path}/{parsed.year}"
            raw = self._request_json("GET", path)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(RiskReportsEnvelope, raw)
            result = self._data_or_error(raw, f"Risk reports are unavailable for {parsed.ticker}")
            if isinstance(result, DigifetchError):
                return self._error_envelope(RiskReportsEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_risk_reports, data, parsed.what)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(RiskReportsEnvelope, normalized)
            fresh = self._freshness(raw, data)
            return RiskReportsEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("risk_reports", parsed, produce)

    def short_interest(
        self, request: ShortInterestInput | Mapping[str, Any]
    ) -> ShortInterestEnvelope:
        """Biweekly short-interest settlements (session-gated)."""
        parsed = self._validate_input(ShortInterestInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ShortInterestEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ShortInterestEnvelope)

        def produce() -> ShortInterestEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["short_interest"],
                params={"symbol": parsed.symbol, "years": str(parsed.years)},
                gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ShortInterestEnvelope, raw)
            result = self._data_or_error(raw, f"Short interest is unavailable for {parsed.symbol}")
            if isinstance(result, DigifetchError):
                return self._error_envelope(ShortInterestEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "short interest")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(ShortInterestEnvelope, payload)
            normalized = self._normalize(nz.normalize_short_interest, payload)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(ShortInterestEnvelope, normalized)
            fresh = self._freshness(raw, payload)
            return ShortInterestEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("short_interest", parsed, produce)

    def equity_diagnostic(
        self, request: EquityDiagnosticInput | Mapping[str, Any]
    ) -> EquityDiagnosticEnvelope:
        """On-demand AI evidence review (session-gated; may answer pending).

        The route's payload carries its own ``status`` (``generating`` /
        ``partial`` / ``complete``) rather than the CloudMarketResponse
        envelope, so it is read with ``direct_payload``. A pending payload is
        **never cached client-side** (a warm 900s cache would mask the finished
        generation); complete reports are cached normally. A report served with
        ``access="preview"`` (free session) gets the envelope-level
        :data:`PREVIEW_ACCESS_WARNING` marker in addition to the report's own
        ``access`` field, so an agent can tell the free-tier preview apart from
        a full PRO/enterprise report.
        """
        parsed = self._validate_input(EquityDiagnosticInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(EquityDiagnosticEnvelope, parsed)
        if not self._enabled:
            return self._disabled(EquityDiagnosticEnvelope)

        def produce() -> EquityDiagnosticEnvelope:
            body: dict[str, Any] = {
                "symbol": parsed.symbol.upper(),
                "mode": parsed.mode,
            }
            if parsed.exchange:
                body["exchange"] = parsed.exchange
            raw = self._request_json(
                "POST",
                ENDPOINTS["equity_diagnostic"],
                body=body,
                gated=True,
                direct_payload=True,
                retry_policy=_SINGLE_ATTEMPT_POLICY,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(EquityDiagnosticEnvelope, raw)
            result = self._data_or_error(
                raw, f"Equity diagnostic is unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(EquityDiagnosticEnvelope, result)
            data, warnings = result
            normalized = self._normalize(nz.normalize_equity_diagnostic, data)
            if isinstance(normalized, DigifetchError):
                return self._error_envelope(EquityDiagnosticEnvelope, normalized)
            if (
                isinstance(normalized, EquityDiagnosticResult)
                and normalized.report is not None
                and normalized.report.access == "preview"
            ):
                warnings = [*warnings, PREVIEW_ACCESS_WARNING]
            fresh = self._freshness(raw, data)
            return EquityDiagnosticEnvelope(
                data=normalized,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        def _cacheable(envelope: EquityDiagnosticEnvelope) -> bool:
            result = envelope.data
            return not isinstance(result, EquityDiagnosticResult) or result.pending is None

        return self._cached("equity_diagnostic", parsed, produce, should_cache=_cacheable)

    # -- prediction-markets venue catalog (#4813) ----------------------------

    def prediction_markets(
        self, request: PredictionMarketsInput | Mapping[str, Any] | None = None
    ) -> PredictionMarketsEnvelope:
        """Prediction-markets catalog (anonymous direct-to-venue reads).

        No Gloomberb Cloud route exists for prediction markets, so the client
        calls the Polymarket Gamma and Kalshi trade APIs directly through the
        shared digifetch transport (pacing, retry, breaker, SSRF guard) and
        normalizes the catalog rows. Only ``limit`` (plus Kalshi's ``open``
        status) is sent upstream — the Gamma/Kalshi search, category, and tab
        parameters are unprobed, so ``query`` / ``category`` / ``tab`` filter
        client-side. Each venue fails soft into the result ``warnings``; when
        every requested venue fails the envelope carries a typed
        ``upstream_error``.
        """
        parsed = self._validate_input(PredictionMarketsInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(PredictionMarketsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(PredictionMarketsEnvelope)

        def produce() -> PredictionMarketsEnvelope:
            rows: list[PredictionMarketRow] = []
            warnings: list[str] = []
            errors: list[DigifetchError] = []
            if parsed.venue in ("all", "polymarket"):
                poly_rows, poly_error = self._fetch_polymarket_catalog(parsed.limit)
                rows.extend(poly_rows)
                if poly_error is not None:
                    warnings.append(f"Polymarket catalog unavailable: {poly_error.message}")
                    errors.append(poly_error)
            if parsed.venue in ("all", "kalshi"):
                kal_rows, kal_error = self._fetch_kalshi_catalog(parsed.limit)
                rows.extend(kal_rows)
                if kal_error is not None:
                    warnings.append(f"Kalshi catalog unavailable: {kal_error.message}")
                    errors.append(kal_error)
            wanted = 2 if parsed.venue == "all" else 1
            if not rows and len(errors) == wanted:
                return self._error_envelope(
                    PredictionMarketsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"Prediction-markets catalog unavailable ({'; '.join(warnings)})",
                        retryable=any(error.retryable for error in errors),
                    ),
                )
            rows = _filter_prediction_markets(
                rows,
                query=parsed.query,
                category=parsed.category,
                tab=parsed.tab,
                limit=parsed.limit,
            )
            return PredictionMarketsEnvelope(
                data=PredictionMarketsResult(
                    markets=rows,
                    attribution=PREDICTION_MARKETS_ATTRIBUTION,
                    warnings=warnings,
                ),
                fetched_at=self._now(),
                provider_id="prediction-markets-venues",
                warnings=warnings,
            )

        return self._cached("prediction_markets", parsed, produce)

    def _fetch_polymarket_catalog(
        self, limit: int
    ) -> tuple[list[PredictionMarketRow], DigifetchError | None]:
        raw = self._request_json(
            "GET",
            POLYMARKET_EVENTS_PATH,
            params={"closed": "false", "limit": str(limit)},
            allow_array=True,
            base_url=POLYMARKET_GAMMA_BASE_URL,
            label="Polymarket",
        )
        if isinstance(raw, DigifetchError):
            return [], raw
        try:
            return _polymarket_rows(raw.data), None
        except (ValidationError, ValueError, TypeError) as exc:
            return [], DigifetchError(
                code="upstream_error",
                message=f"unexpected Polymarket payload shape: {exc}",
                retryable=False,
            )

    def _fetch_kalshi_catalog(
        self, limit: int
    ) -> tuple[list[PredictionMarketRow], DigifetchError | None]:
        raw = self._request_json(
            "GET",
            KALSHI_EVENTS_PATH,
            params={"limit": str(limit), "status": "open"},
            base_url=KALSHI_TRADE_BASE_URL,
            label="Kalshi",
        )
        if isinstance(raw, DigifetchError):
            return [], raw
        try:
            return _kalshi_rows(raw.data), None
        except (ValidationError, ValueError, TypeError) as exc:
            return [], DigifetchError(
                code="upstream_error",
                message=f"unexpected Kalshi payload shape: {exc}",
                retryable=False,
            )

    # -- calculators + compositions (130-coverage Task 2) --------------------
    #
    # Pure calculators run local math only (no transport, no cookies). The
    # compositions fan out to existing reads and derive their numbers locally.
    # All six are unattributed: a derived number must not claim Cloud sourcing.

    def options_calculator(
        self, request: OptionsCalcInput | Mapping[str, Any]
    ) -> OptionsCalcEnvelope:
        """European Black-Scholes price, with an optional IV solve (no transport)."""
        parsed = self._validate_input(OptionsCalcInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(OptionsCalcEnvelope, parsed)
        if not self._enabled:
            return self._disabled(OptionsCalcEnvelope)

        def produce() -> OptionsCalcEnvelope:
            try:
                if parsed.price is None:
                    price = black_scholes_price(
                        spot=parsed.spot,
                        strike=parsed.strike,
                        rate=parsed.rate,
                        vol=parsed.vol,
                        expiry_years=parsed.expiry_years,
                        kind=parsed.kind,
                    )
                    implied_vol: float | None = None
                else:
                    implied_vol = black_scholes_iv(
                        price=parsed.price,
                        spot=parsed.spot,
                        strike=parsed.strike,
                        rate=parsed.rate,
                        expiry_years=parsed.expiry_years,
                        kind=parsed.kind,
                    )
                    price = parsed.price
            except ValueError as exc:
                return self._error_envelope(
                    OptionsCalcEnvelope,
                    DigifetchError(code="invalid_input", message=str(exc), retryable=False),
                )
            return OptionsCalcEnvelope(
                data=OptionsCalcResult(price=price, implied_vol=implied_vol, kind=parsed.kind),
                fetched_at=self._now(),
            )

        return self._cached("options_calculator", parsed, produce)

    def bond_calculator(self, request: BondCalcInput | Mapping[str, Any]) -> BondCalcEnvelope:
        """Par-bond analytics over local discounting math (no transport)."""
        parsed = self._validate_input(BondCalcInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(BondCalcEnvelope, parsed)
        if not self._enabled:
            return self._disabled(BondCalcEnvelope)

        def produce() -> BondCalcEnvelope:
            try:
                metrics = bond_metrics(
                    coupon=parsed.coupon,
                    face=parsed.face,
                    ytm=parsed.ytm,
                    years=parsed.years,
                    freq=parsed.freq,
                )
            except ValueError as exc:
                return self._error_envelope(
                    BondCalcEnvelope,
                    DigifetchError(code="invalid_input", message=str(exc), retryable=False),
                )
            return BondCalcEnvelope(
                data=BondCalcResult(
                    price=metrics["price"],
                    accrued=metrics["accrued"],
                    duration=metrics["duration"],
                    convexity=metrics["convexity"],
                    dv01=metrics["dv01"],
                ),
                fetched_at=self._now(),
            )

        return self._cached("bond_calculator", parsed, produce)

    def kelly_sizer(self, request: KellyInput | Mapping[str, Any]) -> KellyEnvelope:
        """Kelly-criterion fraction from win probability and payoff ratio (no transport)."""
        parsed = self._validate_input(KellyInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(KellyEnvelope, parsed)
        if not self._enabled:
            return self._disabled(KellyEnvelope)

        def produce() -> KellyEnvelope:
            try:
                fraction = kelly_fraction(
                    win_prob=parsed.win_prob, win_loss_ratio=parsed.win_loss_ratio
                )
            except ValueError as exc:
                return self._error_envelope(
                    KellyEnvelope,
                    DigifetchError(code="invalid_input", message=str(exc), retryable=False),
                )
            return KellyEnvelope(
                data=KellyResult(fraction=fraction),
                fetched_at=self._now(),
            )

        return self._cached("kelly_sizer", parsed, produce)

    def dividend_yield(
        self, request: DividendYieldInput | Mapping[str, Any]
    ) -> DividendYieldEnvelope:
        """Trailing dividend yield over corporate-actions + quote (composition).

        Sums the trailing cash distributions and divides by the latest quote
        price locally. Warns and returns ``upstream_error`` when either leg
        errors (including the session gate on the corporate-actions leg).
        """
        parsed = self._validate_input(DividendYieldInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(DividendYieldEnvelope, parsed)
        if not self._enabled:
            return self._disabled(DividendYieldEnvelope)

        def produce() -> DividendYieldEnvelope:
            quote_env = self.quote({"symbol": parsed.symbol})
            corp_env = self.corporate_actions({"symbol": parsed.symbol})
            warnings: list[str] = [*quote_env.warnings, *corp_env.warnings]
            if isinstance(quote_env.data, DigifetchError):
                warnings.append(f"quote unavailable for {parsed.symbol}: {quote_env.data.message}")
            if isinstance(corp_env.data, DigifetchError):
                warnings.append(
                    f"corporate actions unavailable for {parsed.symbol}: {corp_env.data.message}"
                )
            if isinstance(quote_env.data, DigifetchError) or isinstance(
                corp_env.data, DigifetchError
            ):
                return DividendYieldEnvelope(
                    data=DigifetchError(
                        code="upstream_error",
                        message=f"dividend yield unavailable for {parsed.symbol} ({'; '.join(warnings)})",
                        retryable=any(
                            error.retryable
                            for error in (quote_env.data, corp_env.data)
                            if isinstance(error, DigifetchError)
                        ),
                    ),
                    fetched_at=self._now(),
                    warnings=warnings,
                )
            quote = quote_env.data.quote if not isinstance(quote_env.data, DigifetchError) else None
            actions = corp_env.data.actions if not isinstance(corp_env.data, DigifetchError) else []
            if quote is None:
                return self._error_envelope(
                    DividendYieldEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"quote payload missing for {parsed.symbol}",
                        retryable=False,
                    ),
                )
            if quote.price <= 0.0:
                return self._error_envelope(
                    DividendYieldEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"quote price non-positive for {parsed.symbol}",
                        retryable=False,
                    ),
                )
            distributions = [
                action.amount
                for action in actions
                if action.kind == "dividend" and action.amount is not None
            ]
            trailing = sum(distributions)
            return DividendYieldEnvelope(
                data=DividendYieldResult(
                    symbol=parsed.symbol,
                    price=quote.price,
                    trailing_dividends=trailing,
                    distribution_count=len(distributions),
                    dividend_yield=trailing / quote.price,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("dividend_yield", parsed, produce)

    def fx_cross_rates(self, request: FxMatrixInput | Mapping[str, Any]) -> FxMatrixEnvelope:
        """USD-pair FX matrix over the exchange-rate read (USD base only)."""
        parsed = self._validate_input(FxMatrixInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(FxMatrixEnvelope, parsed)
        if not self._enabled:
            return self._disabled(FxMatrixEnvelope)

        def produce() -> FxMatrixEnvelope:
            rates: dict[str, float] = {}
            warnings: list[str] = []
            for code in parsed.currencies:
                env = self.exchange_rate({"from_currency": code, "to_currency": parsed.to_currency})
                warnings.extend(env.warnings)
                if isinstance(env.data, DigifetchError):
                    return FxMatrixEnvelope(
                        data=DigifetchError(
                            code="upstream_error",
                            message=f"exchange rate unavailable for {code}: {env.data.message}",
                            retryable=env.data.retryable,
                        ),
                        fetched_at=self._now(),
                        warnings=warnings,
                    )
                rates[code] = env.data.rate
            crosses = {
                f"{base}/{quote_code}": rates[base] / rates[quote_code]
                for base in rates
                for quote_code in rates
                if base != quote_code
            }
            return FxMatrixEnvelope(
                data=FxMatrixResult(base=parsed.to_currency, rates=rates, crosses=crosses),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("fx_cross_rates", parsed, produce)

    def vix_term_structure(self, request: VixTermInput | Mapping[str, Any]) -> VixTermEnvelope:
        """VIX term snapshot over two econ-series closes (composition).

        Reads the near and far series and reports the far-minus-near spread
        with the curve regime (contango/inversion/flat). Warns and returns
        ``upstream_error`` when either leg errors or carries no closes.
        """
        parsed = self._validate_input(VixTermInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(VixTermEnvelope, parsed)
        if not self._enabled:
            return self._disabled(VixTermEnvelope)

        def produce() -> VixTermEnvelope:
            legs = (
                ("near", parsed.near_series),
                ("far", parsed.far_series),
            )
            closes: dict[str, tuple[str, float]] = {}
            warnings: list[str] = []
            for leg, series_id in legs:
                env = self.econ_series(
                    {"series_id": series_id, "limit": parsed.limit, "sort_order": "desc"}
                )
                warnings.extend(env.warnings)
                if isinstance(env.data, DigifetchError):
                    return VixTermEnvelope(
                        data=DigifetchError(
                            code="upstream_error",
                            message=f"econ series unavailable for {series_id}: {env.data.message}",
                            retryable=env.data.retryable,
                        ),
                        fetched_at=self._now(),
                        warnings=warnings,
                    )
                dated = [
                    (observation.date, observation.value)
                    for observation in env.data.observations
                    if observation.value is not None
                ]
                if not dated:
                    return VixTermEnvelope(
                        data=DigifetchError(
                            code="upstream_error",
                            message=f"econ series {series_id} carries no closes",
                            retryable=False,
                        ),
                        fetched_at=self._now(),
                        warnings=warnings,
                    )
                closes[leg] = dated[0]
            (near_date, near_close), (far_date, far_close) = closes["near"], closes["far"]
            spread = far_close - near_close
            regime: Literal["contango", "inversion", "flat"] = (
                "contango" if spread > 0.0 else ("inversion" if spread < 0.0 else "flat")
            )
            return VixTermEnvelope(
                data=VixTermResult(
                    near_series=parsed.near_series,
                    far_series=parsed.far_series,
                    near_close=near_close,
                    far_close=far_close,
                    near_date=near_date,
                    far_date=far_date,
                    spread=spread,
                    regime=regime,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("vix_term_structure", parsed, produce)

    # -- internals ---------------------------------------------------------

    def _validate_input(
        self, model: type[InputT], request: InputT | Mapping[str, Any]
    ) -> InputT | DigifetchError:
        if isinstance(request, model):
            return request
        try:
            return model.model_validate(request)
        except ValidationError as exc:
            return DigifetchError(
                code="invalid_input", message=_format_validation_error(exc), retryable=False
            )

    def _normalize(self, mapper: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        try:
            return mapper(*args, **kwargs)
        except ValidationError as exc:
            return DigifetchError(
                code="upstream_error",
                message=f"unexpected Gloomberb payload shape: {_format_validation_error(exc)}",
                retryable=False,
            )
        except ValueError as exc:
            # Normalizers also raise plain ValueError for malformed values
            # (e.g. an exchange-rate payload with no finite rate).
            return DigifetchError(
                code="upstream_error",
                message=f"unexpected Gloomberb payload: {exc}",
                retryable=False,
            )

    def _as_mapping(self, data: Any, what: str) -> Mapping[str, Any] | DigifetchError:
        if isinstance(data, Mapping):
            return data
        return DigifetchError(
            code="upstream_error", message=f"{what} returned an unexpected payload", retryable=False
        )

    def _disabled(self, envelope: type[EnvT]) -> EnvT:
        return self._error_envelope(
            envelope,
            DigifetchError(
                code="upstream_error",
                message=f"Gloomberb data family disabled by kill switch ({GLOOMBERB_ENABLED_ENV})",
                retryable=False,
            ),
        )

    def _error_envelope(self, envelope: type[EnvT], error: DigifetchError) -> EnvT:
        return envelope(data=error, fetched_at=self._now())

    def _freshness(
        self,
        raw: _RawResponse,
        payload: Mapping[str, Any] | None = None,
        *,
        extra_stale: bool = False,
    ) -> nz.Freshness:
        source = payload if isinstance(payload, Mapping) else {}
        # Payload-level `stale` is part of the §5.3 union: the quote/options/
        # exchange-rate payloads can carry it even when the response envelope
        # and providerMeta do not (spec §3.2).
        return nz.derive_freshness(
            stale=raw.stale or extra_stale or source.get("stale") is True,
            data_source=source.get("dataSource")
            if isinstance(source.get("dataSource"), str)
            else None,
            delay_minutes=nz.finite_number(source.get("delayMinutes")),
        )

    @staticmethod
    def _rows_stale(rows: Any) -> bool:
        """True when any row of a bare-array payload carries ``stale: true``."""
        return isinstance(rows, list) and any(
            isinstance(row, Mapping) and row.get("stale") is True for row in rows
        )

    def _evict_expired(self, now: float) -> None:
        """Drop expired entries; caller must hold ``_cache_lock``."""
        expired = [key for key, (expiry, _) in self._cache.items() if expiry <= now]
        for key in expired:
            del self._cache[key]

    def _enforce_cache_bound(self) -> None:
        """Trim to ``cache_max_entries``; caller must hold ``_cache_lock``."""
        while len(self._cache) > self._cache_max_entries:
            oldest = min(self._cache, key=lambda key: self._cache[key][0])
            del self._cache[oldest]

    @property
    def cache_size(self) -> int:
        """Number of live cached envelopes (diagnostics/tests)."""
        with self._cache_lock:
            return len(self._cache)

    def _cached(
        self,
        name: str,
        request: BaseModel,
        produce: Callable[[], EnvT],
        *,
        should_cache: Callable[[EnvT], bool] | None = None,
    ) -> EnvT:
        # Cache first: a warm enrichment read still serves during an upstream
        # outage, and the breaker only guards real requests. The key includes
        # the session fingerprint: responses are entitlement-sensitive, so a
        # cached preview/full report must never be served across sessions.
        key = (name, session_cache_fingerprint(self._session_cookie), request.model_dump_json())
        now = self._monotonic()
        with self._cache_lock:
            self._evict_expired(now)
            entry = self._cache.get(key)
            if entry is not None and entry[0] > now:
                return cast(EnvT, entry[1])
        # Produce outside the lock: the rate limiter paces upstream calls, and
        # holding the cache lock across a network request would serialize every
        # parallel node behind the slowest call. Duplicate produce() calls on a
        # concurrent same-key miss are deliberate — a per-key in-flight lock
        # would reintroduce that serialization, and both results are identical
        # envelopes (the rate limiter still paces the wire).
        envelope = produce()
        cacheable = not isinstance(envelope.data, DigifetchError) and (
            should_cache is None or should_cache(envelope)
        )
        if cacheable:
            with self._cache_lock:
                self._cache[key] = (now + self._cache_ttl, envelope)
                self._enforce_cache_bound()
        return envelope

    def _breaker_error(self) -> DigifetchError | None:
        with self._breaker_lock:
            opened_at = self._opened_at
            failures = self._consecutive_failures
        if opened_at is None:
            return None
        if self._monotonic() - opened_at >= self._circuit_reset_seconds:
            # Half-open window: probes are allowed again. There is deliberately
            # no single-probe marker — parallel nodes may probe concurrently,
            # and the next failure re-opens the breaker while a success resets
            # it (a marker would need extra state and still race the lock).
            return None
        return DigifetchError(
            code="upstream_error",
            message=f"Gloomberb circuit breaker open after {failures} consecutive failures",
            retryable=False,
        )

    def _record_failure(self) -> None:
        with self._breaker_lock:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._circuit_failure_threshold:
                self._opened_at = self._monotonic()

    def _record_success(self) -> None:
        with self._breaker_lock:
            self._consecutive_failures = 0
            self._opened_at = None

    def _session_cookies(self) -> dict[str, str] | None:
        raw = self._session_cookie
        if not raw:
            return None
        if "=" in raw:
            name, _, value = raw.partition("=")
            name, value = name.strip(), value.strip()
            if name and value:
                return {name: value}
        # A bare token is sent under every upstream session cookie name, the
        # same fallback the TS client uses when it has not observed a name.
        return {name: raw for name in SESSION_COOKIE_NAMES}

    def _map_http_error(
        self, exc: httpx.HTTPStatusError, *, label: str = "Gloomberb"
    ) -> DigifetchError:
        status = exc.response.status_code
        if label != "Gloomberb" and status in (401, 402, 403):
            # Anonymous venue reads carry no session: a gate here is an
            # upstream change, not missing auth — never name the session env.
            return DigifetchError(
                code="upstream_error",
                message=f"{label} returned HTTP {status} on an anonymous read",
                retryable=False,
            )
        if status == 402:
            # Payment required: a plan gate, not a malformed request. Kept
            # non-retryable and distinct from the generic 4xx mapping.
            return DigifetchError(
                code="auth_required",
                message=f"{label} returned HTTP 402 (payment required); this endpoint "
                "needs a paid plan or a valid session",
                retryable=False,
            )
        if status in (401, 403):
            return DigifetchError(
                code="auth_required",
                message=f"{label} returned HTTP {status}; this endpoint needs "
                f"{GLOOMBERB_SESSION_COOKIE_ENV}",
                retryable=False,
            )
        if status == 404:
            return DigifetchError(
                code="not_found", message=f"{label} returned HTTP 404", retryable=False
            )
        if status == 429:
            retry_after = _parse_retry_after(exc.response.headers.get("retry-after"))
            suffix = f"; Retry-After: {retry_after:g}s" if retry_after is not None else ""
            note = ""
            if retry_after is not None:
                # Bounded wait (spec §5.3: honor Retry-After); a larger value is
                # surfaced in the message but not slept on.
                if 0 < retry_after <= self._max_retry_after_seconds:
                    self._sleep(retry_after)
                    note = f"; waited {retry_after:g}s"
                elif retry_after > self._max_retry_after_seconds:
                    note = "; over the bounded wait, not slept"
            return DigifetchError(
                code="rate_limited",
                message=f"{label} rate limit reached (HTTP 429){suffix}{note}",
                retryable=False,
            )
        if status >= 500:
            return DigifetchError(
                code="upstream_error", message=f"{label} returned HTTP {status}", retryable=True
            )
        return DigifetchError(
            code="invalid_input",
            message=f"{label} rejected the request with HTTP {status}",
            retryable=False,
        )

    def _status_error(self, raw: _RawResponse, message: str) -> DigifetchError:
        reason = raw.reason_code or message
        if raw.status in ("empty", "unsupported"):
            return DigifetchError(code="not_found", message=reason, retryable=False)
        if raw.status == "retryable_error":
            self._record_failure()
            return DigifetchError(code="upstream_error", message=reason, retryable=True)
        self._record_failure()
        return DigifetchError(
            code="upstream_error",
            message=reason if raw.status == "fatal_error" else f"{reason} (status={raw.status!r})",
            retryable=False,
        )

    def _data_or_error(
        self, raw: _RawResponse, message: str
    ) -> tuple[Any, list[str]] | DigifetchError:
        if raw.status in ("success", "partial"):
            if raw.data is None:
                return DigifetchError(code="upstream_error", message=raw.reason_code or message)
            warnings = [raw.reason_code] if raw.status == "partial" and raw.reason_code else []
            return raw.data, warnings
        return self._status_error(raw, message)

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        gated: bool = False,
        allow_array: bool = False,
        pro_gated: bool = False,
        direct_payload: bool = False,
        retry_policy: RetryPolicy | None = None,
        base_url: str | None = None,
        label: str = "Gloomberb",
    ) -> _RawResponse | DigifetchError:
        if not self._enabled:
            return DigifetchError(
                code="upstream_error",
                message=f"Gloomberb data family disabled by kill switch ({GLOOMBERB_ENABLED_ENV})",
                retryable=False,
            )
        if gated and self._session_cookie is None:
            return DigifetchError(
                code="auth_required",
                message=f"{path} requires a verified Gloom session; "
                f"{GLOOMBERB_SESSION_COOKIE_ENV} is not set",
                retryable=False,
            )
        breaker = self._breaker_error()
        if breaker is not None:
            return breaker
        url = f"{base_url or self._base_url}{path}"
        cookies = self._session_cookies() if gated else None

        def attempt() -> FetchResult:
            self._rate_limiter.acquire()
            try:
                return self._fetcher.fetch(
                    url,
                    method=method,
                    params=params,
                    json=body,
                    cookies=cookies,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    proxy_status = _parse_proxy_status(exc.response.text)
                    if proxy_status is not None and 400 <= proxy_status < 500:
                        raise _ProxyStatusError(proxy_status) from exc
                    raise _UpstreamServerError(str(exc)) from exc
                raise

        try:
            result = with_retry(
                attempt,
                retry_policy or self._retry_policy,
                description=f"{label.lower()} {method} {path}",
            )
        except _ProxyStatusError as exc:
            # A proxied upstream 4xx is deterministic (bad input), so it is not
            # retried and must not trip the shared circuit breaker.
            return DigifetchError(
                code="invalid_input",
                message=(f"Gloomberb 13F rejected the request upstream (Forms13F {exc.status})"),
                retryable=False,
            )
        except httpx.HTTPStatusError as exc:
            # Plan-gated routes answer their gate with a body, not an auth code
            # (`/cloud/transcripts` says "Pro plan required"), so check the body
            # before the generic status mapping.
            plan_error = _plan_required_error(exc.response.text) if pro_gated else None
            if plan_error is not None:
                return plan_error
            error = self._map_http_error(exc, label=label)
            # Only upstream-health failures trip the breaker: a 401/404 (or any
            # other deterministic 4xx) is a caller/auth outcome, not service
            # degradation. A 429 counts (upstream overload).
            if error.retryable or error.code == "rate_limited":
                self._record_failure()
            return error
        except (httpx.TransportError, _UpstreamServerError) as exc:
            self._record_failure()
            return DigifetchError(
                code="upstream_error",
                message=f"{label} request failed: {exc}",
                retryable=True,
            )
        except SsrfBlockedError as exc:
            # Deterministic URL refusal; do not open the breaker on it.
            return DigifetchError(
                code="upstream_error",
                message=f"{label} request blocked by the SSRF guard: {exc}",
                retryable=False,
            )
        except httpx.HTTPError as exc:
            # e.g. httpx.TooManyRedirects, which is a RequestError but not a
            # TransportError, so it is not retried and would otherwise escape.
            self._record_failure()
            return DigifetchError(
                code="upstream_error",
                message=f"{label} request failed: {exc}",
                retryable=False,
            )
        try:
            payload = json.loads(result.text) if result.text else None
        except json.JSONDecodeError:
            plan_error = _plan_required_error(result.text) if pro_gated else None
            if plan_error is not None:
                return plan_error
            self._record_failure()
            return DigifetchError(
                code="upstream_error",
                message=f"{label} returned a non-JSON body for {path}",
                retryable=False,
            )
        self._record_success()
        if not isinstance(payload, Mapping):
            if allow_array and isinstance(payload, list):
                return _RawResponse(
                    status="success",
                    data=payload,
                    reason_code=None,
                    stale=False,
                    provider_meta={},
                    as_of=None,
                    currency=None,
                )
            return DigifetchError(
                code="upstream_error",
                message=f"{label} returned an unexpected non-object payload for {path}",
                retryable=False,
            )
        if pro_gated:
            # A JSON error body for a plan-gated route must not read as an
            # empty success: `{"error": "Pro plan required"}` and the screener's
            # `{"status": "unsupported", "reasonCode": "PRO_REQUIRED"}` both
            # need the typed plan error before the status mapping runs.
            for key in ("error", "message", "detail", "reasonCode"):
                value = payload.get(key)
                plan_error = _plan_required_error(value) if isinstance(value, str) else None
                if plan_error is not None:
                    return plan_error
        meta = payload.get("providerMeta")
        provider_meta: Mapping[str, Any] = meta if isinstance(meta, Mapping) else {}
        if direct_payload:
            # The route's own `status` field is payload data (`generating` /
            # `partial` / `complete`), not the CloudMarketResponse envelope
            # discriminator (`/research/equity-diagnostic`).
            return _RawResponse(
                status="success",
                data=payload,
                reason_code=None,
                stale=payload.get("stale") is True,
                provider_meta=provider_meta,
                as_of=None,
                currency=None,
            )
        if "status" not in payload:
            # /news and /cloud/sec/* answer direct payloads, not the shared
            # CloudMarketResponse envelope.
            return _RawResponse(
                status="success",
                data=payload,
                reason_code=None,
                stale=payload.get("stale") is True,
                provider_meta=provider_meta,
                as_of=None,
                currency=None,
            )
        status = str(payload.get("status") or "success")
        reason = payload.get("reasonCode")
        currency = payload.get("currency")
        return _RawResponse(
            status=status,
            data=payload.get("data"),
            reason_code=str(reason) if reason is not None else None,
            stale=payload.get("stale") is True or provider_meta.get("stale") is True,
            provider_meta=provider_meta,
            as_of=str(payload["asOf"]) if payload.get("asOf") is not None else None,
            currency=str(currency) if currency is not None else None,
        )
