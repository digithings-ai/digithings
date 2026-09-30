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
import statistics
import threading
import time
from collections.abc import Callable, Mapping
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal, NamedTuple, TypeVar, cast  # score:allow untyped any — wire JSON
from urllib.parse import quote
from zoneinfo import ZoneInfo

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

from digiquant.data.prices.fed_probabilities import fed_distribution_from_ladder

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
    AuctionRow,
    BondCalcEnvelope,
    BondCalcInput,
    BondCalcResult,
    CdsEnvelope,
    CdsInput,
    CdsResult,
    CdxBoard,
    CdxEnvelope,
    CdxInput,
    CdxResult,
    CentralBankRate,
    CentralBankRatesEnvelope,
    CentralBankRatesInput,
    CentralBankRatesResult,
    ComparePerfEnvelope,
    ComparePerfInput,
    ComparePerfResult,
    CongressTradesEnvelope,
    CongressTradesInput,
    CongressTradesResult,
    CorporateActionsEnvelope,
    CorporateActionsInput,
    CorporateActionsResult,
    CorrMatrixEnvelope,
    CorrMatrixInput,
    CorrMatrixResult,
    CotBoardResult,
    CotContractResult,
    CotEnvelope,
    CotInput,
    CotRow,
    CryptoCoin,
    CryptoMarketsEnvelope,
    CryptoMarketsInput,
    CryptoMarketsResult,
    CustomChartEnvelope,
    CustomChartInput,
    CustomChartResult,
    DebtMaturitiesEnvelope,
    DebtMaturitiesInput,
    DebtMaturitiesResult,
    DebtMaturityFiling,
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
    EconRatio,
    EconSeriesEnvelope,
    EconSeriesInput,
    EquityDiagnosticEnvelope,
    EquityDiagnosticInput,
    EquityDiagnosticResult,
    EstimateRevisionPeriod,
    EstimateRevisionsEnvelope,
    EstimateRevisionsInput,
    EstimateRevisionsResult,
    EstimateRevisionSurprise,
    ExchangeRateEnvelope,
    ExchangeRateInput,
    FearGreedComponent,
    FearGreedEnvelope,
    FearGreedInput,
    FearGreedPoint,
    FearGreedPrevious,
    FearGreedResult,
    FilingEventsEnvelope,
    FilingEventsInput,
    FlowEvent,
    FundGraphEnvelope,
    FundGraphInput,
    FundGraphPoint,
    FundGraphResult,
    Funds13FEnvelope,
    FxMatrixEnvelope,
    FxMatrixInput,
    FxMatrixResult,
    HackerNewsEnvelope,
    HackerNewsInput,
    HackerNewsResult,
    HackerNewsStory,
    HaltRow,
    HiringEnvelope,
    HiringInput,
    HiringMover,
    HiringResult,
    HoldersEnvelope,
    HoldersInput,
    HoldersResult,
    Holdings13FEnvelope,
    IpoCalendarEnvelope,
    IpoCalendarInput,
    IpoCalendarResult,
    IpoDeal,
    IvHistoryEnvelope,
    IvHistoryInput,
    IvHistoryResult,
    IvScreenEnvelope,
    IvScreenInput,
    IvScreenResult,
    IvScreenRow,
    IvSurfaceEnvelope,
    IvSurfaceInput,
    IvSurfaceResult,
    JobPosting,
    KellyEnvelope,
    KellyInput,
    KellyResult,
    MarketHaltsEnvelope,
    MarketHaltsInput,
    MarketHaltsResult,
    MarketValEnvelope,
    MarketValInput,
    MarketValResult,
    MoneyMarketsEnvelope,
    MoneyMarketsInput,
    MoneyMarketsResult,
    NewsEnvelope,
    NewsInput,
    NewsResult,
    OptionsCalcEnvelope,
    OptionsCalcInput,
    OptionsCalcResult,
    OptionsChainEnvelope,
    OptionsChainInput,
    OptionsChainResult,
    OptionsFlowEnvelope,
    OptionsFlowInput,
    OptionsFlowResult,
    PollAnswer,
    PollRow,
    PollsEnvelope,
    PollsInput,
    PollsResult,
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
    Quote,
    QuoteEnvelope,
    QuoteInput,
    QuoteRecapEnvelope,
    QuoteRecapInput,
    QuoteRecapResult,
    QuoteResult,
    QuotesBatchEnvelope,
    QuotesBatchInput,
    QuotesBatchResult,
    RateMeeting,
    RatePathEnvelope,
    RatePathInput,
    RatePathResult,
    RelGraphEnvelope,
    RelGraphInput,
    RelGraphResult,
    RelValEnvelope,
    RelValInput,
    RelValResult,
    RelValRow,
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
    SessionMover,
    SessionMoversEnvelope,
    SessionMoversInput,
    SessionMoversResult,
    ShillerEnvelope,
    ShillerInput,
    ShortInterestEnvelope,
    ShortInterestInput,
    ShortVolumeEnvelope,
    ShortVolumeInput,
    ShortVolumeResult,
    ShortVolumeRow,
    SovrEnvelope,
    SovrInput,
    SovrResult,
    SovrRow,
    StatementsEnvelope,
    StatementsInput,
    SubstackEnvelope,
    SubstackInput,
    SubstackPost,
    SubstackResult,
    TapeQuote,
    TapeTrade,
    ThirteenFFundsInput,
    ThirteenFHoldingsInput,
    TickerFinancialsEnvelope,
    TickerFinancialsInput,
    TickerFinancialsResult,
    TickerTweetsInput,
    TimeAndSalesEnvelope,
    TimeAndSalesInput,
    TimeAndSalesResult,
    TranscriptsEnvelope,
    TranscriptsInput,
    TranscriptsResult,
    TreasuryAuctionsEnvelope,
    TreasuryAuctionsInput,
    TreasuryAuctionsResult,
    TrendingEnvelope,
    TrendingInput,
    TrendingResult,
    TrendingRow,
    TweetSearchInput,
    TweetsEnvelope,
    ValGraphEnvelope,
    ValGraphInput,
    ValGraphResult,
    ValGraphRow,
    ValGraphSnapshot,
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
    "SUBSTACK_SESSION_COOKIE_ENV",
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
    # probe-backed tools (130-coverage Task 5): confirmed Cloud routes from
    # the Task 4 GO verdicts only. Venue-direct tools (trending, substack)
    # take no ENDPOINTS entry — their hosts live in the venue constants below.
    "tape": "/cloud/tape",
    "estimate_revisions": "/cloud/research/estimates",
    "short_volume": "/cloud/short-volume",
    "hiring": "/cloud/jobs",
    "central_bank_rates": "/cloud/econ/central-bank-rates",
    "cdx": "/cloud/credit/cdx",
    "sovr": "/cloud/credit/sovr",
    "flow_history": "/market/scanner/flow/history",
    "cot_board": "/cloud/cot/board",
    "cot_contracts": "/cloud/cot/contracts",
    "crypto_markets": "/cloud/crypto/markets",
    "iv_screen": "/cloud/iv/screen",
    "iv_history": "/cloud/iv/history",
    "iv_surface_dates": "/cloud/iv/surface-dates",
    "iv_surface": "/cloud/iv/surface",
    "debt_maturities": "/cloud/debt-maturities",
    "ipo_calendar": "/cloud/ipo/calendar",
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

# Probe-backed venue-direct tools (130-coverage Task 5). No Gloomberb Cloud
# route exists for these verdicts, so they read the venues directly through
# the shared digifetch transport (pacing, retry, breaker, SSRF guard):
#
# * trending — the builtin market-movers pane hydrates Yahoo's trending list
#   (``GET /v1/finance/trending/US``) with quotes; the tool mirrors that:
#   trend symbols from Yahoo, delayed quotes from the Cloud batch read.
# * substack — the plugin talks to substack.com directly with the reader's
#   own account (magic-link/OTP sign-in harvesting ``substack.sid``); the
#   tool attaches that cookie and fails soft to ``auth_required`` + login
#   instructions without it, never an exception-shaped failure.
YAHOO_TRENDING_BASE_URL = "https://query1.finance.yahoo.com"
YAHOO_TRENDING_PATH = "/v1/finance/trending/US"
YAHOO_QUOTE_URL = "https://finance.yahoo.com/quote/{symbol}"

SUBSTACK_ORIGIN = "https://substack.com"
SUBSTACK_SESSION_COOKIE_ENV = "SUBSTACK_SESSION_COOKIE"
SUBSTACK_COOKIE_NAMES: tuple[str, ...] = (
    "substack.sid",
    "substack.lli",
)

TRENDING_ATTRIBUTION = (
    "Trending symbols sourced directly from Yahoo Finance "
    "(query1.finance.yahoo.com), hydrated with delayed Cloud quotes. "
    "Enrichment only, never a pipeline primary."
)

SUBSTACK_ATTRIBUTION = (
    "Posts sourced directly from Substack with the reader's own account "
    "(own-account session cookie; unofficial, ToS grey area). "
    "Enrichment only, never a pipeline primary."
)

SUBSTACK_LOGIN_HELP = (
    "Substack sign-in required: open substack.com in a browser and sign in "
    "(magic email link or 6-digit OTP code), then set SUBSTACK_SESSION_COOKIE "
    "to the substack.sid cookie value (bare token or substack.sid=value). "
    "Without it this tool returns auth_required and makes no request."
)

# ToS/direct tools (130-coverage Task 6). No Gloomberb Cloud route exists for
# these panes, so they read the venues directly through the shared digifetch
# transport (pacing, retry, breaker, SSRF guard):
#
# * fear_greed — CNN's public Fear & Greed graphdata endpoint (unofficial,
#   ToS grey area): the index series plus the seven component series, with a
#   dated second read for the latest print. Each read fails soft into the
#   other; both failing is a typed upstream_error.
# * polls — VoteHub's public polls endpoint (CC BY 4.0): bare array or a
#   {"polls": [...]} wrapper, filtered to well-formed polls, sliced
#   client-side to limit with total_available/truncated.
# * treasury_auctions — Treasury Fiscal Data's public auction-query dataset
#   (sorted newest-first, paged client-side via page[size]).
# * market_halts — Nasdaq Trader's trade-halts RSS feed (XML, not JSON):
#   an empty channel is a quiet day (empty success); items nobody can parse
#   are a format error, never an empty success.
# * hacker_news — the public Firebase API: one id-list read plus one read
#   per item (sliced to limit first), each item failing soft on its own.
CNN_FEAR_GREED_BASE_URL = "https://production.dataviz.cnn.io"
CNN_FEAR_GREED_PATH = "/index/fearandgreed/graphdata"
CNN_FEAR_GREED_PAGE = "https://www.cnn.com/markets/fear-and-greed"
CNN_REFERER = "https://www.cnn.com/markets/fear-and-greed"
CNN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# CNN serves the endpoint only to something that looks like its own page, so
# the referer and user agent are not optional (same headers the plugin sends).
CNN_FEAR_GREED_HEADERS: dict[str, str] = {
    "Accept": "application/json,text/plain,*/*",
    "User-Agent": CNN_USER_AGENT,
    "Referer": CNN_REFERER,
}

VOTEHUB_BASE_URL = "https://api.votehub.com"
VOTEHUB_POLLS_PATH = "/polls"
VOTEHUB_CC_BY = "VoteHub data © VoteHub contributors, CC BY 4.0"

FISCALDATA_BASE_URL = "https://api.fiscaldata.treasury.gov"
FISCALDATA_AUCTIONS_PATH = "/services/api/fiscal_service/v1/accounting/od/auctions_query"
FISCALDATA_AUCTIONS_DOC_URL = (
    "https://fiscaldata.treasury.gov/datasets/auction-query/treasury-auctions-query"
)

NASDAQ_TRADER_BASE_URL = "https://www.nasdaqtrader.com"
NASDAQ_HALTS_PATH = "/rss.aspx"
NASDAQ_HALT_CODES_URL = "https://www.nasdaqtrader.com/trader.aspx?id=TradeHalt"

HN_BASE_URL = "https://hacker-news.firebaseio.com/v0"
HN_FEED_PATHS: dict[str, str] = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
    "show": "showstories",
    "ask": "askstories",
}
HN_DISCUSSION_URL = "https://news.ycombinator.com/item?id={story_id}"

# Venue honesty: result-level attribution for venue-sourced rows. These name
# the venues, never Gloomberb Cloud (there is no term.gloom.sh page for
# venue rows).
FEAR_GREED_ATTRIBUTION = (
    "CNN Fear & Greed sentiment gauge read directly from CNN's public endpoint "
    "(production.dataviz.cnn.io). Unofficial read; cross-check before citing. "
    "Enrichment only, never a pipeline primary."
)

POLLS_ATTRIBUTION = (
    "Polls sourced directly from VoteHub (api.votehub.com). "
    "VoteHub data © VoteHub contributors, CC BY 4.0. "
    "Enrichment only, never a pipeline primary."
)

AUCTIONS_ATTRIBUTION = (
    "Treasury auction results sourced directly from Treasury Fiscal Data "
    "(fiscaldata.treasury.gov), public. "
    "Enrichment only, never a pipeline primary."
)

HALTS_ATTRIBUTION = (
    "Trade halts sourced directly from Nasdaq Trader (nasdaqtrader.com), "
    "delayed. Enrichment only, never a pipeline primary."
)

HN_ATTRIBUTION = (
    "Stories sourced directly from Hacker News via the public API "
    "(hacker-news.firebaseio.com). "
    "Enrichment only, never a pipeline primary."
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


def _venue_str(value: Any) -> str | None:
    """A stripped venue string, or None when absent/blank."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _venue_number_or_str(value: Any) -> float | str | None:
    """A venue amount: finite numbers stay numeric, raw strings stay raw."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


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


def _yahoo_trending_symbols(payload: Any) -> list[str] | None:
    """Trend symbols from Yahoo's ``/v1/finance/trending`` payload, or None.

    ``None`` is an unexpected shape (typed ``upstream_error``); an empty list
    is a valid-but-empty venue answer (the caller maps it the same way —
    never an empty success).
    """
    if not isinstance(payload, Mapping):
        return None
    finance = payload.get("finance")
    if not isinstance(finance, Mapping):
        return None
    results = finance.get("result")
    if not isinstance(results, list) or not results:
        return []
    first = results[0]
    if not isinstance(first, Mapping):
        return None
    quotes = first.get("quotes")
    if not isinstance(quotes, list):
        return None
    symbols: list[str] = []
    for entry in quotes:
        if isinstance(entry, Mapping):
            symbol = entry.get("symbol")
            if isinstance(symbol, str) and symbol.strip() and symbol not in symbols:
                symbols.append(symbol.strip())
    return symbols


_FEAR_GREED_RATINGS: tuple[str, ...] = (
    "extreme fear",
    "fear",
    "neutral",
    "greed",
    "extreme greed",
)

#: The seven components behind the CNN index: id, title, primary series key,
#: secondary series key (or None), and value format.
_FEAR_GREED_COMPONENTS: tuple[tuple[str, str, str, str | None, str], ...] = (
    (
        "market-momentum",
        "Market Momentum",
        "market_momentum_sp500",
        "market_momentum_sp125",
        "number",
    ),
    ("stock-price-strength", "Stock Price Strength", "stock_price_strength", None, "percent"),
    ("stock-price-breadth", "Stock Price Breadth", "stock_price_breadth", None, "number"),
    ("put-call-options", "Put and Call Options", "put_call_options", None, "ratio"),
    (
        "market-volatility",
        "Market Volatility",
        "market_volatility_vix",
        "market_volatility_vix_50",
        "number",
    ),
    ("safe-haven-demand", "Safe Haven Demand", "safe_haven_demand", None, "percent"),
    ("junk-bond-demand", "Junk Bond Demand", "junk_bond_demand", None, "percent"),
)


def _fear_greed_rating(value: Any, score: float | None) -> str:
    """Normalize a CNN rating, falling back to the score bands."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _FEAR_GREED_RATINGS:
            return normalized
    if score is None:
        return "neutral"
    if score < 25:
        return "extreme fear"
    if score < 45:
        return "fear"
    if score <= 55:
        return "neutral"
    if score <= 75:
        return "greed"
    return "extreme greed"


def _cnn_number(value: Any) -> float | None:
    """A finite CNN number, or None (bools and numeric strings are not numbers)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _cnn_points(series: Any) -> list[tuple[int, float]]:
    """Sorted ``(epoch_ms, value)`` pairs from a CNN ``data`` list, or []."""
    if not isinstance(series, Mapping):
        return []
    data = series.get("data")
    if not isinstance(data, list):
        return []
    points: list[tuple[int, float]] = []
    for item in data:
        if not isinstance(item, Mapping):
            continue
        x = _cnn_number(item.get("x"))
        y = _cnn_number(item.get("y"))
        if x is None or y is None:
            continue
        points.append((int(x), y))
    return sorted(points)


def _cnn_timestamp(value: Any) -> str | None:
    """An ISO timestamp from a CNN timestamp (ISO string or epoch ms), or None."""
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.isoformat()
    millis = _cnn_number(value)
    if millis is None:
        return None
    try:
        return datetime.fromtimestamp(millis / 1000, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return None


def _votehub_polls(payload: Any) -> list[Mapping[str, Any]] | None:
    """VoteHub polls from a bare array or a ``{"polls": [...]}`` wrapper.

    ``None`` is an unexpected shape (typed ``upstream_error``); rows that are
    not well-formed polls are filtered, never fatal.
    """
    items: Any = payload
    if isinstance(payload, Mapping):
        if "polls" not in payload:
            return None
        items = payload.get("polls")
    if not isinstance(items, list):
        return None
    polls: list[Mapping[str, Any]] = []
    for entry in items:
        if not isinstance(entry, Mapping):
            continue
        if (
            isinstance(entry.get("id"), str)
            and isinstance(entry.get("pollster"), str)
            and isinstance(entry.get("subject"), str)
        ):
            polls.append(entry)
    return polls


def _poll_sample_size(value: Any) -> int | None:
    """A VoteHub sample size (number or comma-formatted string), or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value.replace(",", "").strip()))
        except ValueError:
            return None
    return None


def _poll_margin_of_error(sample_size: int | None) -> float | None:
    """95% MoE at 50/50 from sample size (0.98 / sqrt(n)), or None."""
    if sample_size is None or sample_size < 1:
        return None
    moe = (0.98 / math.sqrt(sample_size)) * 100
    return round(moe, 1) if math.isfinite(moe) else None


def _poll_result_summary(
    answers: list[PollAnswer],
) -> tuple[str, float | None, str | None]:
    """``"First 52 · Second 45"`` result line plus lead and leader, or blanks."""
    if not answers:
        return "—", None, None
    first = answers[0]
    if len(answers) < 2:
        return f"{first.choice} {first.pct:g}", first.pct, first.choice
    second = answers[1]
    lead = first.pct - second.pct
    return f"{first.choice} {first.pct:g} · {second.choice} {second.pct:g}", lead, first.choice


def _halt_field(item: str, tag: str) -> str:
    """One ``ndaq:`` namespaced field from a halt-feed ``<item>`` block."""
    match = re.search(rf"<ndaq:{tag}[^>]*>([\s\S]*?)</ndaq:{tag}>", item, re.IGNORECASE)
    return match.group(1).strip() if match else ""


#: Concise renderings of Nasdaq's trade halt codes
#: (nasdaqtrader.com/trader.aspx?id=TradeHaltCodes).
_HALT_REASONS: dict[str, str] = {
    "T1": "News pending",
    "T2": "News released",
    "T3": "News released, resumption times set",
    "T5": "Single-stock pause, 10% move",
    "T6": "Extraordinary market activity",
    "T7": "Quotation-only period",
    "T8": "ETF halt",
    "T12": "Additional info requested by Nasdaq",
    "H4": "Listing non-compliance",
    "H9": "Filings not current",
    "H10": "SEC trading suspension",
    "H11": "Regulatory concern",
    "O1": "Operations halt",
    "IPO1": "IPO not yet trading",
    "IPOQ": "IPO released for quotation",
    "IPOE": "IPO positioning window extended",
    "M": "Volatility pause, listed issue",
    "M1": "Corporate action",
    "M2": "Quotation not available",
    "LUDP": "Volatility pause",
    "LUDS": "Volatility pause, straddle",
    "MWC0": "Circuit breaker carried over",
    "MWC1": "Market-wide circuit breaker, level 1",
    "MWC2": "Market-wide circuit breaker, level 2",
    "MWC3": "Market-wide circuit breaker, level 3",
    "MWCQ": "Market-wide circuit breaker resumption",
    "R1": "New issue available",
    "R2": "Issue available",
    "R4": "Qualification issues resolved",
    "R9": "Filing requirements satisfied",
    "C3": "Issuer news not forthcoming",
    "C4": "Qualifications halt ended",
    "C9": "Qualifications halt concluded",
    "C11": "Halt concluded by other regulator",
    "D": "Security deleted from Nasdaq/CQS",
}


def _describe_halt_reason(code: str) -> str:
    """Plain-English expansion of a Nasdaq halt code (or the code itself)."""
    normalized = code.strip().upper()
    if not normalized:
        return "Reason not available"
    return _HALT_REASONS.get(normalized, f"Reason code {normalized}")


try:
    _ET_ZONE: ZoneInfo | None = ZoneInfo("America/New_York")
except Exception:
    # No tz database: ET wall-clock times stay strings and epochs stay null
    # rather than guessing an offset.
    _ET_ZONE = None


def _et_to_utc_ms(utc_date: str, utc_time: str) -> int | None:
    """Nasdaq's ``MM/DD/YYYY`` + ``HH:MM:SS[.mmm]`` ET pair to UTC epoch ms."""
    if _ET_ZONE is None:
        return None
    date_match = re.fullmatch(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})\s*", utc_date or "")
    time_match = re.fullmatch(
        r"\s*(\d{1,2}):(\d{2})(?::(\d{2}))?(?:\.(\d{1,3}))?\s*", utc_time or ""
    )
    if not date_match or not time_match:
        return None
    try:
        wall = datetime(
            int(date_match.group(3)),
            int(date_match.group(1)),
            int(date_match.group(2)),
            int(time_match.group(1)),
            int(time_match.group(2)),
            int(time_match.group(3) or 0),
            int((time_match.group(4) or "0").ljust(3, "0")) * 1000,
            tzinfo=_ET_ZONE,
        )
    except ValueError:
        return None
    return int(wall.timestamp() * 1000)


def _parse_halt_items(xml: str) -> tuple[list[dict[str, Any]], int]:
    """Halt records + ``<item>`` count from the Nasdaq RSS XML.

    Rows without a symbol or a parseable halt time are skipped (they carry no
    addressable halt); the caller turns items-nobody-can-parse into a format
    error so it never reads as a quiet day.
    """
    items = re.findall(r"<item>[\s\S]*?</item>", xml, re.IGNORECASE)
    records: list[dict[str, Any]] = []
    for item in items:
        symbol = _halt_field(item, "IssueSymbol").upper()
        halt_date = _halt_field(item, "HaltDate")
        halt_time = _halt_field(item, "HaltTime")
        halted_at = _et_to_utc_ms(halt_date, halt_time)
        if not symbol or halted_at is None:
            continue
        reason_code = _halt_field(item, "ReasonCode").upper()
        resumption_date = _halt_field(item, "ResumptionDate")
        records.append(
            {
                "symbol": symbol,
                "company": _halt_field(item, "IssueName") or None,
                "market": _halt_field(item, "Market") or None,
                "reason_code": reason_code,
                "reason": _describe_halt_reason(reason_code),
                "halt_date": halt_date or None,
                "halt_time": halt_time or None,
                "halted_at": halted_at,
                "quote_resume_at": _et_to_utc_ms(
                    resumption_date, _halt_field(item, "ResumptionQuoteTime")
                ),
                "trade_resume_at": _et_to_utc_ms(
                    resumption_date, _halt_field(item, "ResumptionTradeTime")
                ),
            }
        )
    return records, len(items)


def _hn_site(url: str) -> str | None:
    """Hostname minus a ``www.`` prefix, or None when unparseable."""
    from urllib.parse import urlparse

    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return None
    return host[4:] if host.startswith("www.") else host or None


def _hn_story(raw: Any) -> dict[str, Any] | None:
    """One normalized Hacker News story, or None when deleted/dead/malformed."""
    if not isinstance(raw, Mapping):
        return None
    if raw.get("deleted") is True or raw.get("dead") is True:
        return None
    story_id = raw.get("id")
    title = raw.get("title")
    if type(story_id) is not int or not isinstance(title, str) or not title:
        return None
    url = raw.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        url = None
    by = raw.get("by")
    time_value = raw.get("time")
    score = raw.get("score")
    comments = raw.get("descendants")
    return {
        "id": story_id,
        "title": title,
        "by": by if isinstance(by, str) else "unknown",
        "time": time_value if type(time_value) is int else 0,
        "score": score if type(score) is int else 0,
        "comments": comments if type(comments) is int else 0,
        "url": url,
        "site": _hn_site(url) if url else None,
        "source_url": url or HN_DISCUSSION_URL.format(story_id=story_id),
    }


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
        substack_cookie:  Optional own-account Substack cookie; ``None`` reads
                          ``SUBSTACK_SESSION_COOKIE``. Same bare-or-named form;
                          only the substack reader sends it, never the Cloud
                          routes. Never logged.
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
        substack_cookie: str | None = None,
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
        if substack_cookie is None:
            env_substack = os.environ.get(SUBSTACK_SESSION_COOKIE_ENV, "").strip()
            self._substack_cookie: str | None = env_substack or None
        else:
            self._substack_cookie = substack_cookie.strip() or None
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

    # -- probe-backed tools (130-coverage Task 5) -------------------------------
    #
    # One method per GO verdict in the Task 4 probe table. Every verdict
    # carries a ``Live: unverified`` marker (no operator approval for any
    # host), so payload models stay deliberately permissive — typed key
    # fields with the long tail preserved as extras — until a live probe
    # lands. NO-ROUTE verdicts (EE/INS/HVG/HVT/CRD/HILO) add no method here.

    def time_and_sales(
        self, request: TimeAndSalesInput | Mapping[str, Any]
    ) -> TimeAndSalesEnvelope:
        """Time and sales over the shared tape route (session-gated)."""
        parsed = self._validate_input(TimeAndSalesInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TimeAndSalesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TimeAndSalesEnvelope)

        def produce() -> TimeAndSalesEnvelope:
            path = f"{ENDPOINTS['tape']}/{quote(parsed.symbol, safe='')}"
            raw = self._request_json("GET", path, params={"exchange": parsed.exchange}, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TimeAndSalesEnvelope, raw)
            result = self._data_or_error(raw, f"Cloud tape is unavailable for {parsed.symbol}")
            if isinstance(result, DigifetchError):
                return self._error_envelope(TimeAndSalesEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "tape")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(TimeAndSalesEnvelope, payload)
            try:
                trades = [TapeTrade.model_validate(row) for row in payload.get("trades") or []]
                result_obj = TimeAndSalesResult(
                    symbol=parsed.symbol,
                    exchange=parsed.exchange,
                    trades=trades,
                    session_high=payload.get("sessionHigh"),
                    session_low=payload.get("sessionLow"),
                    capacity=payload.get("capacity"),
                    dropped=payload.get("dropped"),
                    cancelled=payload.get("cancelled"),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    TimeAndSalesEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected tape payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return TimeAndSalesEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("time_and_sales", parsed, produce)

    def quote_recap(self, request: QuoteRecapInput | Mapping[str, Any]) -> QuoteRecapEnvelope:
        """NBBO recap over the shared tape route (the quotes half of TAS)."""
        parsed = self._validate_input(QuoteRecapInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(QuoteRecapEnvelope, parsed)
        if not self._enabled:
            return self._disabled(QuoteRecapEnvelope)

        def produce() -> QuoteRecapEnvelope:
            path = f"{ENDPOINTS['tape']}/{quote(parsed.symbol, safe='')}"
            raw = self._request_json("GET", path, params={"exchange": parsed.exchange}, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(QuoteRecapEnvelope, raw)
            result = self._data_or_error(raw, f"Cloud tape is unavailable for {parsed.symbol}")
            if isinstance(result, DigifetchError):
                return self._error_envelope(QuoteRecapEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "tape")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(QuoteRecapEnvelope, payload)
            try:
                quotes = [TapeQuote.model_validate(row) for row in payload.get("quotes") or []]
                result_obj = QuoteRecapResult(
                    symbol=parsed.symbol, exchange=parsed.exchange, quotes=quotes
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    QuoteRecapEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected tape payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return QuoteRecapEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("quote_recap", parsed, produce)

    def estimate_revisions(
        self, request: EstimateRevisionsInput | Mapping[str, Any]
    ) -> EstimateRevisionsEnvelope:
        """Estimate revisions board (session-gated; pane shortcut EM)."""
        parsed = self._validate_input(EstimateRevisionsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(EstimateRevisionsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(EstimateRevisionsEnvelope)

        def produce() -> EstimateRevisionsEnvelope:
            path = f"{ENDPOINTS['estimate_revisions']}/{quote(parsed.symbol, safe='')}"
            params: dict[str, Any] = {}
            if parsed.exchange:
                params["exchange"] = parsed.exchange
            raw = self._request_json("GET", path, params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(EstimateRevisionsEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud estimate revisions are unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(EstimateRevisionsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "estimate revisions")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(EstimateRevisionsEnvelope, payload)
            try:
                result_obj = EstimateRevisionsResult(
                    symbol=parsed.symbol,
                    exchange=parsed.exchange,
                    periods=[
                        EstimateRevisionPeriod.model_validate(row)
                        for row in payload.get("periods") or []
                    ],
                    breadth_7d=payload.get("breadth7d") or {},
                    breadth_30d=payload.get("breadth30d") or {},
                    surprises=[
                        EstimateRevisionSurprise.model_validate(row)
                        for row in payload.get("surprises") or []
                    ],
                    guidance=payload.get("guidance"),
                    coverage=list(payload.get("coverage") or []),
                    gaps=list(payload.get("gaps") or []),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    EstimateRevisionsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected estimate-revisions payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return EstimateRevisionsEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("estimate_revisions", parsed, produce)

    def short_volume(self, request: ShortVolumeInput | Mapping[str, Any]) -> ShortVolumeEnvelope:
        """FINRA daily short volume, NMS or OTC scope (session-gated)."""
        parsed = self._validate_input(ShortVolumeInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ShortVolumeEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ShortVolumeEnvelope)

        def produce() -> ShortVolumeEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["short_volume"],
                params={"symbol": parsed.symbol, "scope": parsed.scope},
                gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(ShortVolumeEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud short volume is unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(ShortVolumeEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "short volume")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(ShortVolumeEnvelope, payload)
            try:
                result_obj = ShortVolumeResult(
                    symbol=parsed.symbol,
                    scope=parsed.scope,
                    rows=[ShortVolumeRow.model_validate(row) for row in payload.get("rows") or []],
                    latest=payload.get("latest") or {},
                    change=payload.get("change"),
                    percentile=payload.get("percentile"),
                    coverage_start=payload.get("coverageStart"),
                    coverage_end=payload.get("coverageEnd"),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    ShortVolumeEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected short-volume payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return ShortVolumeEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("short_volume", parsed, produce)

    def hiring(self, request: HiringInput | Mapping[str, Any]) -> HiringEnvelope:
        """Hiring summary / postings / market-wide movers (session-gated)."""
        parsed = self._validate_input(HiringInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(HiringEnvelope, parsed)
        if not self._enabled:
            return self._disabled(HiringEnvelope)

        def produce() -> HiringEnvelope:
            if parsed.mode == "movers":
                path: str = ENDPOINTS["hiring"]
                params: dict[str, Any] = {
                    "limit": str(parsed.limit),
                    "offset": str(parsed.offset),
                }
            elif parsed.mode == "postings":
                ticker = (parsed.ticker or "").strip()
                path = f"{ENDPOINTS['hiring']}/{quote(ticker, safe='')}/postings"
                params = {"limit": str(parsed.limit), "offset": str(parsed.offset)}
            else:
                ticker = (parsed.ticker or "").strip()
                path = f"{ENDPOINTS['hiring']}/{quote(ticker, safe='')}"
                params = {}
                if parsed.name:
                    params["name"] = parsed.name
            raw = self._request_json("GET", path, params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(HiringEnvelope, raw)
            result = self._data_or_error(raw, "Cloud hiring is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(HiringEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "hiring")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(HiringEnvelope, payload)
            try:
                result_obj = HiringResult(
                    mode=parsed.mode,
                    ticker=(parsed.ticker or "").strip() or None,
                    status=payload.get("status"),
                    summary={
                        key: value
                        for key, value in payload.items()
                        if key not in ("postings", "total", "asOf", "covered", "movers")
                    },
                    postings=[
                        JobPosting.model_validate(row) for row in payload.get("postings") or []
                    ],
                    total=payload.get("total"),
                    as_of=payload.get("asOf"),
                    covered=payload.get("covered"),
                    movers=[HiringMover.model_validate(row) for row in payload.get("movers") or []],
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    HiringEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected hiring payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return HiringEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("hiring", parsed, produce)

    def central_bank_rates(
        self, request: CentralBankRatesInput | Mapping[str, Any]
    ) -> CentralBankRatesEnvelope:
        """Policy-rate board (session-gated; FRED/BIS provenance per row)."""
        parsed = self._validate_input(CentralBankRatesInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CentralBankRatesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CentralBankRatesEnvelope)

        def produce() -> CentralBankRatesEnvelope:
            raw = self._request_json("GET", ENDPOINTS["central_bank_rates"], gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CentralBankRatesEnvelope, raw)
            result = self._data_or_error(raw, "Cloud central-bank rates are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(CentralBankRatesEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "central-bank rates")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(CentralBankRatesEnvelope, payload)
            try:
                result_obj = CentralBankRatesResult(
                    rows=[CentralBankRate.model_validate(row) for row in payload.get("rows") or []]
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    CentralBankRatesEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected central-bank-rates payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return CentralBankRatesEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("central_bank_rates", parsed, produce)

    def cdx(self, request: CdxInput | Mapping[str, Any]) -> CdxEnvelope:
        """Index-CDS board (session-gated; DTCC-built 5Y on-the-run)."""
        parsed = self._validate_input(CdxInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CdxEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CdxEnvelope)

        def produce() -> CdxEnvelope:
            params: dict[str, Any] = {}
            if parsed.days is not None:
                params["days"] = str(parsed.days)
            raw = self._request_json("GET", ENDPOINTS["cdx"], params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CdxEnvelope, raw)
            result = self._data_or_error(raw, "Cloud CDX board is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(CdxEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "CDX board")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(CdxEnvelope, payload)
            try:
                result_obj = CdxResult(
                    boards=[CdxBoard.model_validate(row) for row in payload.get("boards") or []],
                    points=list(payload.get("points") or []),
                    days=parsed.days,
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    CdxEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected CDX payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return CdxEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("cdx", parsed, produce)

    def sovereign_cds(self, request: SovrInput | Mapping[str, Any]) -> SovrEnvelope:
        """Sovereign-CDS board (session-gated; 5Y spreads in bp)."""
        parsed = self._validate_input(SovrInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SovrEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SovrEnvelope)

        def produce() -> SovrEnvelope:
            params: dict[str, Any] = {}
            if parsed.days is not None:
                params["days"] = str(parsed.days)
            raw = self._request_json("GET", ENDPOINTS["sovr"], params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(SovrEnvelope, raw)
            result = self._data_or_error(raw, "Cloud sovereign-CDS board is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(SovrEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "sovereign-CDS board")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(SovrEnvelope, payload)
            try:
                result_obj = SovrResult(
                    rows=[SovrRow.model_validate(row) for row in payload.get("rows") or []],
                    days=parsed.days,
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    SovrEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected sovereign-CDS payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return SovrEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("sovereign_cds", parsed, produce)

    def options_flow(self, request: OptionsFlowInput | Mapping[str, Any]) -> OptionsFlowEnvelope:
        """Recorded options-flow history (Pro; no delayed tier — fail closed).

        A denial (``auth_required`` / ``pro_required``) is surfaced, never an
        empty success: FLOW is the one scanner with no delayed tier.
        """
        parsed = self._validate_input(OptionsFlowInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(OptionsFlowEnvelope, parsed)
        if not self._enabled:
            return self._disabled(OptionsFlowEnvelope)

        def produce() -> OptionsFlowEnvelope:
            params: dict[str, Any] = {}
            if parsed.before:
                params["before"] = parsed.before
            if parsed.limit is not None:
                params["limit"] = str(parsed.limit)
            if parsed.min_premium is not None:
                params["minPremium"] = str(parsed.min_premium)
            if parsed.right:
                params["right"] = parsed.right
            if parsed.kind:
                params["kind"] = parsed.kind
            if parsed.min_vol_oi is not None:
                params["minVolOi"] = str(parsed.min_vol_oi)
            if parsed.max_expiry_days is not None:
                params["maxExpiryDays"] = str(parsed.max_expiry_days)
            if parsed.symbols:
                params["symbols"] = ",".join(parsed.symbols)
            raw = self._request_json(
                "GET", ENDPOINTS["flow_history"], params=params, gated=True, pro_gated=True
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(OptionsFlowEnvelope, raw)
            result = self._data_or_error(raw, "Recorded options flow is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(OptionsFlowEnvelope, result)
            data, warnings = result
            events: Any = data.get("events") if isinstance(data, Mapping) else data
            try:
                result_obj = OptionsFlowResult(
                    events=[FlowEvent.model_validate(row) for row in events or []],
                    has_more=bool(data.get("hasMore")) if isinstance(data, Mapping) else False,
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    OptionsFlowEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected options-flow payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, data if isinstance(data, Mapping) else None)
            return OptionsFlowEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("options_flow", parsed, produce)

    def cot(self, request: CotInput | Mapping[str, Any]) -> CotEnvelope:
        """CFTC positioning board, or one contract when code is given."""
        parsed = self._validate_input(CotInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CotEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CotEnvelope)

        def produce() -> CotEnvelope:
            if parsed.code:
                path = f"{ENDPOINTS['cot_contracts']}/{quote(parsed.code.strip(), safe='')}"
                params: dict[str, Any] = {"report": parsed.report}
            else:
                path = ENDPOINTS["cot_board"]
                params = {"report": parsed.report}
                if parsed.trader_class:
                    params["traderClass"] = parsed.trader_class
            raw = self._request_json("GET", path, params=params, gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CotEnvelope, raw)
            result = self._data_or_error(raw, "Cloud COT board is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(CotEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "COT board")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(CotEnvelope, payload)
            try:
                rows = [CotRow.model_validate(row) for row in payload.get("rows") or []]
                if parsed.code:
                    result_obj: CotBoardResult | CotContractResult = CotContractResult(
                        report=str(payload.get("report") or parsed.report),
                        code=str(payload.get("code") or parsed.code.strip()),
                        rows=rows,
                    )
                else:
                    result_obj = CotBoardResult(
                        report=str(payload.get("report") or parsed.report),
                        trader_class=payload.get("traderClass") or parsed.trader_class,
                        rows=rows,
                    )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    CotEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected COT payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return CotEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("cot", parsed, produce)

    def crypto_markets(
        self, request: CryptoMarketsInput | Mapping[str, Any]
    ) -> CryptoMarketsEnvelope:
        """Crypto board (session-gated; pane refreshes every 15s upstream)."""
        parsed = self._validate_input(CryptoMarketsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CryptoMarketsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CryptoMarketsEnvelope)

        def produce() -> CryptoMarketsEnvelope:
            raw = self._request_json("GET", ENDPOINTS["crypto_markets"], gated=True)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(CryptoMarketsEnvelope, raw)
            result = self._data_or_error(raw, "Cloud crypto markets are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(CryptoMarketsEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "crypto markets")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(CryptoMarketsEnvelope, payload)
            try:
                result_obj = CryptoMarketsResult(
                    coins=[CryptoCoin.model_validate(row) for row in payload.get("coins") or []],
                    source=payload.get("source") or {},
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    CryptoMarketsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected crypto-markets payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return CryptoMarketsEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("crypto_markets", parsed, produce)

    def iv_screen(self, request: IvScreenInput | Mapping[str, Any]) -> IvScreenEnvelope:
        """IV rich/cheap screen over stored daily history (session guess).

        No Pro-gate evidence in source, but the route is ``pro_gated``: a
        server denial surfaces verbatim, and a 402 plan body maps to the
        typed ``pro_required`` (a bare 402 keeps the generic mapping).
        """
        parsed = self._validate_input(IvScreenInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(IvScreenEnvelope, parsed)
        if not self._enabled:
            return self._disabled(IvScreenEnvelope)

        def produce() -> IvScreenEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["iv_screen"],
                params={"symbols": ",".join(parsed.symbols)},
                gated=True,
                pro_gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(IvScreenEnvelope, raw)
            result = self._data_or_error(raw, "Cloud IV screen is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(IvScreenEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "IV screen")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(IvScreenEnvelope, payload)
            try:
                result_obj = IvScreenResult(
                    rows=[IvScreenRow.model_validate(row) for row in payload.get("rows") or []]
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    IvScreenEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected IV-screen payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return IvScreenEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("iv_screen", parsed, produce)

    def iv_history(self, request: IvHistoryInput | Mapping[str, Any]) -> IvHistoryEnvelope:
        """Stored daily IV history with rank/percentile (session guess).

        Same denial contract as :meth:`iv_screen`: verbatim surfacing, ready
        for a Pro gate on 402.
        """
        parsed = self._validate_input(IvHistoryInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(IvHistoryEnvelope, parsed)
        if not self._enabled:
            return self._disabled(IvHistoryEnvelope)

        def produce() -> IvHistoryEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["iv_history"],
                params={"symbol": parsed.symbol, "days": str(parsed.days)},
                gated=True,
                pro_gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(IvHistoryEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud IV history is unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(IvHistoryEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "IV history")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(IvHistoryEnvelope, payload)
            try:
                result_obj = IvHistoryResult(
                    symbol=parsed.symbol,
                    days=parsed.days,
                    status=payload.get("status"),
                    points=list(payload.get("points") or []),
                    iv30_rank=payload.get("iv30Rank"),
                    iv30_percentile=payload.get("iv30Percentile"),
                    iv90_rank=payload.get("iv90Rank"),
                    iv90_percentile=payload.get("iv90Percentile"),
                    latest=payload.get("latest"),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    IvHistoryEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected IV-history payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return IvHistoryEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("iv_history", parsed, produce)

    def iv_surface(self, request: IvSurfaceInput | Mapping[str, Any]) -> IvSurfaceEnvelope:
        """Stored close surface: dates list, or the surface for a date.

        Same denial contract as :meth:`iv_screen`: verbatim surfacing, ready
        for a Pro gate on 402. A live surface composes over
        ``options_chain`` + ``yield_curve`` instead.
        """
        parsed = self._validate_input(IvSurfaceInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(IvSurfaceEnvelope, parsed)
        if not self._enabled:
            return self._disabled(IvSurfaceEnvelope)

        def produce() -> IvSurfaceEnvelope:
            if parsed.date:
                raw = self._request_json(
                    "GET",
                    ENDPOINTS["iv_surface"],
                    params={"symbol": parsed.symbol, "date": parsed.date},
                    gated=True,
                    pro_gated=True,
                )
            else:
                raw = self._request_json(
                    "GET",
                    ENDPOINTS["iv_surface_dates"],
                    params={"symbol": parsed.symbol},
                    gated=True,
                    pro_gated=True,
                )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(IvSurfaceEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud IV surface is unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(IvSurfaceEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "IV surface")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(IvSurfaceEnvelope, payload)
            try:
                result_obj = IvSurfaceResult(
                    symbol=parsed.symbol,
                    date=parsed.date or payload.get("date"),
                    dates=list(payload.get("dates") or []),
                    surface=payload.get("surface"),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    IvSurfaceEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected IV-surface payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return IvSurfaceEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("iv_surface", parsed, produce)

    def debt_maturities(
        self, request: DebtMaturitiesInput | Mapping[str, Any]
    ) -> DebtMaturitiesEnvelope:
        """US-GAAP debt maturities with filing provenance (session-gated)."""
        parsed = self._validate_input(DebtMaturitiesInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(DebtMaturitiesEnvelope, parsed)
        if not self._enabled:
            return self._disabled(DebtMaturitiesEnvelope)

        def produce() -> DebtMaturitiesEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["debt_maturities"],
                params={"symbol": parsed.symbol},
                gated=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(DebtMaturitiesEnvelope, raw)
            result = self._data_or_error(
                raw, f"Cloud debt maturities are unavailable for {parsed.symbol}"
            )
            if isinstance(result, DigifetchError):
                return self._error_envelope(DebtMaturitiesEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "debt maturities")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(DebtMaturitiesEnvelope, payload)
            try:
                result_obj = DebtMaturitiesResult(
                    symbol=parsed.symbol,
                    total_principal=payload.get("totalPrincipal"),
                    next_12m_share=payload.get("next12mShare"),
                    next_3y_share=payload.get("next3yShare"),
                    interest_expense=payload.get("interestExpense"),
                    borrowing_cost=payload.get("borrowingCost"),
                    filings=[
                        DebtMaturityFiling.model_validate(row)
                        for row in payload.get("filings") or []
                    ],
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    DebtMaturitiesEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected debt-maturities payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return DebtMaturitiesEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("debt_maturities", parsed, produce)

    def session_movers(
        self, request: SessionMoversInput | Mapping[str, Any]
    ) -> SessionMoversEnvelope:
        """Pre-market / after-hours / gaps movers (session guess).

        Same screener route, session categories only (gainers/losers/
        most-active stay on ``digifetch_screener``). ``pro_gated`` so a
        server plan denial surfaces verbatim either way.
        """
        parsed = self._validate_input(SessionMoversInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SessionMoversEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SessionMoversEnvelope)

        def produce() -> SessionMoversEnvelope:
            raw = self._request_json(
                "GET",
                ENDPOINTS["screener"],
                params={
                    "category": parsed.category,
                    "side": parsed.side,
                    "count": str(parsed.count),
                    "mode": parsed.mode,
                },
                gated=True,
                pro_gated=True,
                allow_array=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(SessionMoversEnvelope, raw)
            result = self._data_or_error(raw, "Cloud session movers are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(SessionMoversEnvelope, result)
            data, warnings = result
            rows: Any = data.get("movers") if isinstance(data, Mapping) else data
            if rows is None and isinstance(data, Mapping):
                rows = data.get("data")
            try:
                movers = [SessionMover.model_validate(row) for row in rows or []]
                first = movers[0] if movers else None
                result_obj = SessionMoversResult(
                    category=parsed.category,
                    side=parsed.side,
                    # Phase/as-of ride the envelope in one shape and per row
                    # in the other; prefer the envelope, fall back to the row.
                    phase=(data.get("phase") if isinstance(data, Mapping) else None)
                    or (first.phase if first else None),
                    as_of=(data.get("asOf") if isinstance(data, Mapping) else None)
                    or (first.as_of if first else None),
                    movers=movers,
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    SessionMoversEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected session-movers payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(
                raw, data if isinstance(data, Mapping) else None, extra_stale=self._rows_stale(rows)
            )
            return SessionMoversEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("session_movers", parsed, produce)

    def trending(
        self, request: TrendingInput | Mapping[str, Any] | None = None
    ) -> TrendingEnvelope:
        """Yahoo trending symbols, hydrated with delayed Cloud quotes.

        Venue-direct (the builtin pane hydrates the same way): trend symbols
        come from Yahoo's trending endpoint, quotes from the anonymous Cloud
        batch read. NOT attributed to Gloomberb; rows carry the Yahoo deep
        link. An empty trending list is a typed ``upstream_error``, never an
        empty success.
        """
        parsed = self._validate_input(TrendingInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TrendingEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TrendingEnvelope)

        def produce() -> TrendingEnvelope:
            warnings: list[str] = []
            raw = self._request_json(
                "GET",
                YAHOO_TRENDING_PATH,
                base_url=YAHOO_TRENDING_BASE_URL,
                label="Yahoo",
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TrendingEnvelope, raw)
            symbols = _yahoo_trending_symbols(raw.data)
            if symbols is None:
                return self._error_envelope(
                    TrendingEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Yahoo trending returned an unexpected payload shape",
                        retryable=False,
                    ),
                )
            symbols = symbols[: parsed.limit]
            if not symbols:
                return self._error_envelope(
                    TrendingEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Yahoo trending returned no symbols",
                        retryable=False,
                    ),
                )
            quotes: dict[str, Quote] = {}
            batch = self.quotes_batch({"symbols": symbols})
            if isinstance(batch.data, DigifetchError):
                warnings.append(f"delayed quotes unavailable: {batch.data.message}")
            else:
                for item in batch.data.quotes:
                    if item.quote is not None:
                        quotes[item.symbol.upper()] = item.quote
            rows: list[TrendingRow] = []
            for rank, symbol in enumerate(symbols, start=1):
                quote_data = quotes.get(symbol.upper())
                rows.append(
                    TrendingRow(
                        symbol=symbol,
                        rank=rank,
                        price=quote_data.price if quote_data else None,
                        change=quote_data.change if quote_data else None,
                        change_percent=quote_data.change_percent if quote_data else None,
                        volume=quote_data.volume if quote_data else None,
                        market_state=quote_data.market_state if quote_data else None,
                        venue_url=YAHOO_QUOTE_URL.format(symbol=symbol),
                    )
                )
            return TrendingEnvelope(
                data=TrendingResult(
                    rows=rows,
                    attribution=TRENDING_ATTRIBUTION,
                    as_of=self._now().isoformat(),
                ),
                fetched_at=self._now(),
                provider_id="yahoo-trending",
                warnings=warnings,
            )

        return self._cached("trending", parsed, produce)

    def substack(self, request: SubstackInput | Mapping[str, Any]) -> SubstackEnvelope:
        """Own-account Substack reader (venue-direct, fail-soft).

        No stored auth (``SUBSTACK_SESSION_COOKIE``) returns ``auth_required``
        with login instructions and makes no request — the unauthenticated
        pane renders the login view, never an error. An expired/rejected
        session maps to ``auth_required`` (re-sign-in), never an
        exception-shaped failure. NOT attributed to Gloomberb.
        """
        parsed = self._validate_input(SubstackInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(SubstackEnvelope, parsed)
        if not self._enabled:
            return self._disabled(SubstackEnvelope)

        def produce() -> SubstackEnvelope:
            if self._substack_cookie is None:
                return self._error_envelope(
                    SubstackEnvelope,
                    DigifetchError(
                        code="auth_required", message=SUBSTACK_LOGIN_HELP, retryable=False
                    ),
                )
            cookies = self._substack_cookies()
            host = f"{parsed.publication}.substack.com"
            base_url = f"https://{host}"
            if parsed.mode == "post":
                post_id = (parsed.post_id or "").strip()
                raw = self._request_json(
                    "GET",
                    f"/api/v1/posts/by-id/{quote(post_id, safe='')}",
                    base_url=base_url,
                    label="Substack",
                    cookies=cookies,
                )
            elif parsed.mode == "inbox":
                raw = self._request_json(
                    "GET",
                    "/api/v1/inbox/top",
                    params={
                        "inboxType": "inbox",
                        "surface": "inbox_all",
                        "limit": str(parsed.limit),
                    },
                    base_url=SUBSTACK_ORIGIN,
                    label="Substack",
                    cookies=cookies,
                )
            else:
                raw = self._request_json(
                    "GET",
                    "/api/v1/posts",
                    params={"limit": str(parsed.limit), "offset": str(parsed.offset)},
                    base_url=base_url,
                    label="Substack",
                    cookies=cookies,
                    allow_array=True,
                )
            if isinstance(raw, DigifetchError):
                # An expired/rejected own-account session drops back to the
                # login view: auth_required with re-sign-in help, never a
                # generic upstream error.
                if "HTTP 401" in raw.message or "HTTP 403" in raw.message:
                    return self._error_envelope(
                        SubstackEnvelope,
                        DigifetchError(
                            code="auth_required",
                            message=(
                                "Substack rejected the stored session (expired or "
                                f"revoked); {SUBSTACK_LOGIN_HELP}"
                            ),
                            retryable=False,
                        ),
                    )
                return self._error_envelope(SubstackEnvelope, raw)
            result = self._data_or_error(raw, "Substack reader is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(SubstackEnvelope, result)
            data, warnings = result
            try:
                if parsed.mode == "post":
                    post = data.get("post") if isinstance(data, Mapping) else None
                    if not isinstance(post, Mapping):
                        raise ValueError("post detail carries no post object")
                    result_obj = SubstackResult(
                        publication=parsed.publication,
                        mode=parsed.mode,
                        post_id=(parsed.post_id or "").strip(),
                        post=dict(post),
                        attribution=SUBSTACK_ATTRIBUTION,
                    )
                else:
                    items: Any = data
                    if isinstance(data, Mapping):
                        items = data.get("posts", data)
                    posts = [SubstackPost.model_validate(row) for row in items or []]
                    result_obj = SubstackResult(
                        publication=parsed.publication,
                        mode=parsed.mode,
                        posts=posts,
                        attribution=SUBSTACK_ATTRIBUTION,
                    )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    SubstackEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected Substack payload shape: {exc}",
                        retryable=False,
                    ),
                )
            return SubstackEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                provider_id="substack-venue",
                warnings=warnings,
            )

        return self._cached("substack", parsed, produce)

    def ipo_calendar(
        self, request: IpoCalendarInput | Mapping[str, Any] | None = None
    ) -> IpoCalendarEnvelope:
        """Worldwide IPO calendar (Cloud; public, works signed out)."""
        parsed = self._validate_input(IpoCalendarInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(IpoCalendarEnvelope, parsed)
        if not self._enabled:
            return self._disabled(IpoCalendarEnvelope)

        def produce() -> IpoCalendarEnvelope:
            params: dict[str, Any] = {"limit": str(parsed.limit)}
            if parsed.status:
                params["status"] = parsed.status
            if parsed.region:
                params["region"] = parsed.region
            if parsed.deal_type:
                params["type"] = parsed.deal_type
            if parsed.from_date:
                params["fromDate"] = parsed.from_date
            if parsed.to_date:
                params["toDate"] = parsed.to_date
            raw = self._request_json("GET", ENDPOINTS["ipo_calendar"], params=params)
            if isinstance(raw, DigifetchError):
                return self._error_envelope(IpoCalendarEnvelope, raw)
            result = self._data_or_error(raw, "Cloud IPO calendar is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(IpoCalendarEnvelope, result)
            data, warnings = result
            payload = self._as_mapping(data, "IPO calendar")
            if isinstance(payload, DigifetchError):
                return self._error_envelope(IpoCalendarEnvelope, payload)
            try:
                result_obj = IpoCalendarResult(
                    deals=[IpoDeal.model_validate(row) for row in payload.get("deals") or []],
                    status=parsed.status,
                    region=parsed.region,
                    deal_type=parsed.deal_type,
                )
            except (ValidationError, ValueError, TypeError) as exc:
                return self._error_envelope(
                    IpoCalendarEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"unexpected IPO-calendar payload shape: {exc}",
                        retryable=False,
                    ),
                )
            fresh = self._freshness(raw, payload)
            return IpoCalendarEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                stale=fresh.stale,
                delay_note=fresh.delay_note,
                warnings=warnings,
            )

        return self._cached("ipo_calendar", parsed, produce)

    # -- ToS/direct tools (130-coverage Task 6) ------------------------------
    #
    # Venue-direct reads (the prediction-markets precedent): free, unattributed
    # (attributed=False on both surfaces), per-row venue URLs, per-venue
    # fail-soft, no Gloomberb claims anywhere.

    def fear_greed(
        self, request: FearGreedInput | Mapping[str, Any] | None = None
    ) -> FearGreedEnvelope:
        """CNN Fear & Greed gauge + the seven components behind it.

        Venue-direct: the index/history/components come from CNN's public
        graphdata endpoint (unofficial, ToS grey area) with a dated second
        read for the latest print. Each read fails soft into the other; both
        failing is a typed ``upstream_error``. NOT attributed to Gloomberb;
        rows carry the CNN page link.
        """
        parsed = self._validate_input(FearGreedInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(FearGreedEnvelope, parsed)
        if not self._enabled:
            return self._disabled(FearGreedEnvelope)

        def produce() -> FearGreedEnvelope:
            today = self._now().date().isoformat()
            charts = self._request_json(
                "GET",
                CNN_FEAR_GREED_PATH,
                base_url=CNN_FEAR_GREED_BASE_URL,
                label="CNN Fear & Greed",
                headers=CNN_FEAR_GREED_HEADERS,
            )
            latest = self._request_json(
                "GET",
                f"{CNN_FEAR_GREED_PATH}/{today}",
                base_url=CNN_FEAR_GREED_BASE_URL,
                label="CNN Fear & Greed",
                headers=CNN_FEAR_GREED_HEADERS,
            )
            charts_data = charts.data if not isinstance(charts, DigifetchError) else None
            latest_data = latest.data if not isinstance(latest, DigifetchError) else None
            if charts_data is None and latest_data is None:
                first = charts if isinstance(charts, DigifetchError) else latest
                assert isinstance(first, DigifetchError)
                return self._error_envelope(FearGreedEnvelope, first)
            try:
                result_obj = self._normalize_fear_greed(charts_data, latest_data)
            except ValueError as exc:
                return self._error_envelope(
                    FearGreedEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=f"CNN Fear & Greed returned an unexpected shape: {exc}",
                        retryable=False,
                    ),
                )
            return FearGreedEnvelope(
                data=result_obj,
                fetched_at=self._now(),
                provider_id="cnn-fear-greed",
            )

        return self._cached("fear_greed", parsed, produce)

    @staticmethod
    def _normalize_fear_greed(charts: Any, latest: Any) -> FearGreedResult:
        """Index gauge + components from the CNN graphdata payloads."""
        charts_map = charts if isinstance(charts, Mapping) else {}
        latest_map = latest if isinstance(latest, Mapping) else {}
        overall = latest_map.get("fear_and_greed", charts_map.get("fear_and_greed"))
        history_series = charts_map.get("fear_and_greed_historical") or latest_map.get(
            "fear_and_greed_historical"
        )
        history_points = _cnn_points(history_series)
        score = _cnn_number(overall.get("score") if isinstance(overall, Mapping) else None)
        if score is None and isinstance(history_series, Mapping):
            score = _cnn_number(history_series.get("score"))
        if score is None and history_points:
            score = history_points[-1][1]
        if score is None:
            raise ValueError("response did not include an index score")
        rating = _fear_greed_rating(
            overall.get("rating") if isinstance(overall, Mapping) else None, score
        )
        updated_at = _cnn_timestamp(
            overall.get("timestamp") if isinstance(overall, Mapping) else None
        )
        previous = FearGreedPrevious()
        if isinstance(overall, Mapping):
            previous = FearGreedPrevious(
                close=_cnn_number(overall.get("previous_close")),
                week=_cnn_number(overall.get("previous_1_week")),
                month=_cnn_number(overall.get("previous_1_month")),
                year=_cnn_number(overall.get("previous_1_year")),
            )
            if updated_at is None:
                updated_at = _cnn_timestamp(history_series.get("timestamp"))
        history = [
            FearGreedPoint(
                date=datetime.fromtimestamp(x / 1000, tz=timezone.utc).isoformat(),
                score=y,
            )
            for x, y in history_points
        ]
        components: list[FearGreedComponent] = []
        for comp_id, title, primary_key, _secondary_key, value_format in _FEAR_GREED_COMPONENTS:
            series = charts_map.get(primary_key, latest_map.get(primary_key))
            if not isinstance(series, Mapping):
                continue
            points = _cnn_points(series)
            if not points:
                continue
            comp_score = _cnn_number(series.get("score"))
            components.append(
                FearGreedComponent(
                    id=comp_id,
                    title=title,
                    score=comp_score,
                    rating=_fear_greed_rating(series.get("rating"), comp_score),
                    value=points[-1][1],
                    value_format=value_format,
                    updated_at=_cnn_timestamp(series.get("timestamp"))
                    or (datetime.fromtimestamp(points[-1][0] / 1000, tz=timezone.utc).isoformat()),
                    source_url=CNN_FEAR_GREED_PAGE,
                )
            )
        return FearGreedResult(
            score=score,
            rating=rating,
            updated_at=updated_at,
            previous=previous,
            history=history,
            components=components,
            attribution=FEAR_GREED_ATTRIBUTION,
        )

    def polls(self, request: PollsInput | Mapping[str, Any]) -> PollsEnvelope:
        """VoteHub political polls (venue-direct, anonymous).

        The endpoint answers a bare array or a ``{"polls": [...]}`` wrapper;
        rows that are not well-formed polls are filtered, never fatal, and the
        list is sliced client-side to ``limit`` with ``total_available`` /
        ``truncated``. NOT attributed to Gloomberb; every row carries the
        VoteHub CC BY 4.0 marker plus its source link.
        """
        parsed = self._validate_input(PollsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(PollsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(PollsEnvelope)

        def produce() -> PollsEnvelope:
            params: dict[str, Any] = {}
            if parsed.poll_type:
                params["poll_type"] = parsed.poll_type
            if parsed.subject:
                params["subject"] = parsed.subject
            raw = self._request_json(
                "GET",
                VOTEHUB_POLLS_PATH,
                params=params or None,
                base_url=VOTEHUB_BASE_URL,
                label="VoteHub",
                allow_array=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(PollsEnvelope, raw)
            result = self._data_or_error(raw, "VoteHub polls are unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(PollsEnvelope, result)
            data, warnings = result
            items = _votehub_polls(data)
            if items is None:
                return self._error_envelope(
                    PollsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="VoteHub polls returned an unexpected payload shape",
                        retryable=False,
                    ),
                )
            rows: list[PollRow] = []
            for entry in items:
                try:
                    answers = [
                        PollAnswer(choice=str(a["choice"]), pct=float(a["pct"]))
                        for a in entry.get("answers") or []
                        if isinstance(a, Mapping)
                        and isinstance(a.get("choice"), str)
                        and _cnn_number(a.get("pct")) is not None
                    ]
                    answers.sort(key=lambda a: a.pct, reverse=True)
                    summary, lead, lead_choice = _poll_result_summary(answers)
                    sample_size = _poll_sample_size(entry.get("sample_size"))
                    rows.append(
                        PollRow(
                            id=entry["id"],
                            subject=entry["subject"],
                            poll_type=str(entry.get("poll_type") or ""),
                            pollster=entry["pollster"],
                            population=(
                                str(entry["population"])
                                if entry.get("population") is not None
                                else None
                            ),
                            sample_size=sample_size,
                            margin_of_error=_poll_margin_of_error(sample_size),
                            start_date=(
                                str(entry["start_date"])
                                if entry.get("start_date") is not None
                                else None
                            ),
                            end_date=(
                                str(entry["end_date"])
                                if entry.get("end_date") is not None
                                else None
                            ),
                            result=summary,
                            lead=lead,
                            lead_choice=lead_choice,
                            url=(str(entry["url"]) if isinstance(entry.get("url"), str) else None),
                            attribution=VOTEHUB_CC_BY,
                            answers=answers,
                        )
                    )
                except (ValidationError, ValueError, TypeError):
                    continue
            total_available = len(rows)
            sliced = rows[: parsed.limit]
            return PollsEnvelope(
                data=PollsResult(
                    rows=sliced,
                    total_available=total_available,
                    truncated=total_available > len(sliced),
                    attribution=POLLS_ATTRIBUTION,
                ),
                fetched_at=self._now(),
                provider_id="votehub-polls",
                warnings=warnings,
            )

        return self._cached("polls", parsed, produce)

    def treasury_auctions(
        self, request: TreasuryAuctionsInput | Mapping[str, Any]
    ) -> TreasuryAuctionsEnvelope:
        """US Treasury auction results (venue-direct, anonymous).

        Reads Treasury Fiscal Data's public auction-query dataset newest-first
        (``sort=-record_date``, ``page[size]=limit``) with optional
        security-type / record-date filters. Rows type the common fields and
        preserve the rest; each row carries the result-document link when the
        venue supplies one. NOT attributed to Gloomberb.
        """
        parsed = self._validate_input(TreasuryAuctionsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(TreasuryAuctionsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(TreasuryAuctionsEnvelope)

        def produce() -> TreasuryAuctionsEnvelope:
            params: dict[str, Any] = {
                "sort": "-record_date",
                "page[size]": str(parsed.limit),
            }
            filters: list[str] = []
            if parsed.from_date:
                filters.append(f"record_date:gte:{parsed.from_date}")
            if parsed.to_date:
                filters.append(f"record_date:lte:{parsed.to_date}")
            if parsed.security_type:
                filters.append(f"security_type:eq:{parsed.security_type}")
            if filters:
                params["filter"] = ",".join(filters)
            raw = self._request_json(
                "GET",
                FISCALDATA_AUCTIONS_PATH,
                params=params,
                base_url=FISCALDATA_BASE_URL,
                label="Treasury Fiscal Data",
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(TreasuryAuctionsEnvelope, raw)
            result = self._data_or_error(raw, "Treasury auction data is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(TreasuryAuctionsEnvelope, result)
            data, warnings = result
            items: Any = data.get("data") if isinstance(data, Mapping) else data
            if not isinstance(items, list):
                return self._error_envelope(
                    TreasuryAuctionsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Treasury auction data returned an unexpected payload shape",
                        retryable=False,
                    ),
                )
            rows: list[AuctionRow] = []
            for entry in items:
                if not isinstance(entry, Mapping):
                    continue
                try:
                    pdf_url = entry.get("pdf_url")
                    rows.append(
                        AuctionRow(
                            record_date=_venue_str(entry.get("record_date")),
                            cusip=_venue_str(entry.get("cusip")),
                            security_type=_venue_str(entry.get("security_type")),
                            auction_date=_venue_str(entry.get("auction_date")),
                            issue_date=_venue_str(entry.get("issue_date")),
                            maturity_date=_venue_str(entry.get("maturity_date")),
                            offering_amount=_venue_number_or_str(entry.get("offering_amount")),
                            total_accepted=_venue_number_or_str(
                                entry.get("total_accepted") or entry.get("total_accepted_amount")
                            ),
                            bid_to_cover_ratio=_venue_number_or_str(
                                entry.get("bid_to_cover_ratio")
                            ),
                            high_yield=_venue_number_or_str(
                                entry.get("high_yield") or entry.get("rate")
                            ),
                            price_per100=_venue_number_or_str(entry.get("price_per100")),
                            source_url=(
                                pdf_url
                                if isinstance(pdf_url, str) and pdf_url.startswith("http")
                                else FISCALDATA_AUCTIONS_DOC_URL
                            ),
                            **{
                                key: value
                                for key, value in entry.items()
                                if key
                                not in {
                                    "record_date",
                                    "cusip",
                                    "security_type",
                                    "auction_date",
                                    "issue_date",
                                    "maturity_date",
                                    "offering_amount",
                                    "total_accepted",
                                    "total_accepted_amount",
                                    "bid_to_cover_ratio",
                                    "high_yield",
                                    "rate",
                                    "price_per100",
                                    "pdf_url",
                                }
                            },
                        )
                    )
                except (ValidationError, ValueError, TypeError):
                    continue
            meta = data.get("meta") if isinstance(data, Mapping) else None
            meta_count = meta.get("count") if isinstance(meta, Mapping) else None
            total_available = meta_count if type(meta_count) is int else len(rows)
            sliced = rows[: parsed.limit]
            return TreasuryAuctionsEnvelope(
                data=TreasuryAuctionsResult(
                    rows=sliced,
                    total_available=total_available,
                    truncated=total_available > len(sliced),
                    attribution=AUCTIONS_ATTRIBUTION,
                ),
                fetched_at=self._now(),
                provider_id="treasury-fiscal-data",
                warnings=warnings,
            )

        return self._cached("treasury_auctions", parsed, produce)

    def market_halts(
        self, request: MarketHaltsInput | Mapping[str, Any] | None = None
    ) -> MarketHaltsEnvelope:
        """US equity trade halts (venue-direct, anonymous).

        Reads Nasdaq Trader's trade-halts RSS feed (XML): an empty channel is
        a quiet day (empty success), while items nobody can parse are a format
        error, never an empty success. Times are ET wall clock with UTC
        epochs; ``status`` resolves against now. NOT attributed to Gloomberb;
        rows carry the halt-codes link.
        """
        parsed = self._validate_input(MarketHaltsInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(MarketHaltsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(MarketHaltsEnvelope)

        def produce() -> MarketHaltsEnvelope:
            text = self._request_text(
                "GET",
                NASDAQ_HALTS_PATH,
                params={"feed": "tradehalts"},
                base_url=NASDAQ_TRADER_BASE_URL,
                label="Nasdaq Trader",
            )
            if isinstance(text, DigifetchError):
                return self._error_envelope(MarketHaltsEnvelope, text)
            if (
                re.search(r"<rss\b", text, re.IGNORECASE) is None
                or re.search(r"<channel\b", text, re.IGNORECASE) is None
                or re.search(r"xmlns:ndaq=", text, re.IGNORECASE) is None
            ):
                return self._error_envelope(
                    MarketHaltsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Nasdaq halt feed response was not RSS",
                        retryable=False,
                    ),
                )
            records, item_count = _parse_halt_items(text)
            if not records and item_count > 0:
                return self._error_envelope(
                    MarketHaltsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Nasdaq halt feed format was not recognized",
                        retryable=False,
                    ),
                )
            now_ms = int(self._now().timestamp() * 1000)
            wanted = (parsed.symbol or "").strip().upper()
            rows: list[HaltRow] = []
            for record in records:
                if wanted and record["symbol"] != wanted:
                    continue
                trade_resume = record["trade_resume_at"]
                quote_resume = record["quote_resume_at"]
                if isinstance(trade_resume, int) and now_ms >= trade_resume:
                    status = "resumed"
                elif isinstance(quote_resume, int) and now_ms >= quote_resume:
                    status = "quote"
                else:
                    status = "halted"
                rows.append(
                    HaltRow(
                        symbol=record["symbol"],
                        company=record["company"],
                        market=record["market"],
                        reason_code=record["reason_code"],
                        reason=record["reason"],
                        halt_date=record["halt_date"],
                        halt_time=record["halt_time"],
                        halted_at=record["halted_at"],
                        quote_resume_at=quote_resume,
                        trade_resume_at=trade_resume,
                        status=status,
                        source_url=NASDAQ_HALT_CODES_URL,
                    )
                )
            # Newest halt first: the reason anyone opens this pane.
            rows.sort(key=lambda row: row.halted_at or 0, reverse=True)
            return MarketHaltsEnvelope(
                data=MarketHaltsResult(
                    rows=rows[: parsed.limit],
                    attribution=HALTS_ATTRIBUTION,
                    as_of=self._now().isoformat(),
                ),
                fetched_at=self._now(),
                provider_id="nasdaq-trader-halts",
            )

        return self._cached("market_halts", parsed, produce)

    def hacker_news(
        self, request: HackerNewsInput | Mapping[str, Any] | None = None
    ) -> HackerNewsEnvelope:
        """Hacker News stories (venue-direct, anonymous).

        Reads the public API's id list for one feed, then one item read per
        story (sliced to ``limit`` first, so the fan-out stays bounded). One
        dead item never empties the feed: per-item failures skip that story.
        NOT attributed to Gloomberb; rows carry the article link, or the
        discussion link for self posts.
        """
        parsed = self._validate_input(HackerNewsInput, request or {})
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(HackerNewsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(HackerNewsEnvelope)

        def produce() -> HackerNewsEnvelope:
            feed_path = HN_FEED_PATHS.get(parsed.feed)
            if feed_path is None:
                return self._error_envelope(
                    HackerNewsEnvelope,
                    DigifetchError(
                        code="invalid_input",
                        message=f"unknown Hacker News feed {parsed.feed!r}",
                        retryable=False,
                    ),
                )
            raw = self._request_json(
                "GET",
                f"/{feed_path}.json",
                base_url=HN_BASE_URL,
                label="Hacker News",
                allow_array=True,
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(HackerNewsEnvelope, raw)
            result = self._data_or_error(raw, "Hacker News feed is unavailable")
            if isinstance(result, DigifetchError):
                return self._error_envelope(HackerNewsEnvelope, result)
            data, warnings = result
            if not isinstance(data, list):
                return self._error_envelope(
                    HackerNewsEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Hacker News feed returned an unexpected payload shape",
                        retryable=False,
                    ),
                )
            ids = [item for item in data if type(item) is int][: parsed.limit]
            rows: list[HackerNewsStory] = []
            for story_id in ids:
                item = self._request_json(
                    "GET",
                    f"/item/{story_id}.json",
                    base_url=HN_BASE_URL,
                    label="Hacker News",
                )
                if isinstance(item, DigifetchError):
                    continue
                item_result = self._data_or_error(item, "Hacker News item is unavailable")
                if isinstance(item_result, DigifetchError):
                    continue
                story, _item_warnings = item_result
                normalized = _hn_story(story)
                if normalized is None:
                    continue
                try:
                    rows.append(HackerNewsStory.model_validate(normalized))
                except (ValidationError, ValueError, TypeError):
                    continue
            return HackerNewsEnvelope(
                data=HackerNewsResult(
                    rows=rows,
                    feed=parsed.feed,
                    attribution=HN_ATTRIBUTION,
                ),
                fetched_at=self._now(),
                provider_id="hacker-news",
                warnings=warnings,
            )

        return self._cached("hacker_news", parsed, produce)

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

    # -- portfolio-math compositions (130-coverage Task 3) -------------------
    #
    # Ten compositions over existing reads. Every number is derived locally
    # (rebased returns, date-aligned inner joins, Pearson math, statement
    # multiples, CAPE zones, funding spreads, survival-ladder differences), so
    # all ten are unattributed: a derived number must not claim Cloud sourcing.

    def _aligned_closes(
        self, tickers: list[str], resolution: str, range: str | None
    ) -> tuple[list[str], dict[str, list[float]], list[str]] | DigifetchError:
        """Date-aligned inner join of daily closes, or a typed error.

        Each leg is one ``price_history`` read. A failed leg (or a leg with no
        bars) is an ``upstream_error`` naming the ticker; an empty date overlap
        is an ``invalid_input`` — the join is rejected, never clamped.
        """
        per_ticker: dict[str, dict[str, float]] = {}
        warnings: list[str] = []
        for ticker in tickers:
            env = self.price_history({"symbol": ticker, "resolution": resolution, "range": range})
            warnings.extend(env.warnings)
            if isinstance(env.data, DigifetchError):
                return DigifetchError(
                    code="upstream_error",
                    message=f"price history unavailable for {ticker}: {env.data.message}",
                    retryable=env.data.retryable,
                )
            closes = {
                bar.date: bar.close
                for bar in env.data.bars
                if bar.close is not None and bar.close > 0.0
            }
            if not closes:
                return DigifetchError(
                    code="upstream_error",
                    message=f"price history for {ticker} carries no closes",
                    retryable=False,
                )
            per_ticker[ticker] = closes
        dates = sorted(set.intersection(*(set(closes) for closes in per_ticker.values())))
        if not dates:
            return DigifetchError(
                code="invalid_input",
                message=(
                    f"empty date overlap for {', '.join(tickers)} "
                    "(the join is rejected, never clamped)"
                ),
                retryable=False,
            )
        aligned = {ticker: [per_ticker[ticker][day] for day in dates] for ticker in tickers}
        return dates, aligned, warnings

    @staticmethod
    def _simple_returns(closes: list[float]) -> list[float]:
        """Daily simple returns, skipping non-positive bases (noisy-row guard)."""
        returns: list[float] = []
        for prev, current in zip(closes, closes[1:], strict=False):
            if prev > 0.0:
                returns.append(current / prev - 1.0)
        return returns

    @staticmethod
    def _pearson(first: list[float], second: list[float]) -> float | None:
        """Pearson correlation, or None when either leg is flat (undefined)."""
        try:
            return statistics.correlation(first, second)
        except statistics.StatisticsError:
            return None

    @staticmethod
    def _history_zone(percentile: float) -> Literal["cheap", "fair", "expensive"]:
        """History thirds: cheap ≤1/3, fair ≤2/3, expensive above."""
        if percentile <= 1.0 / 3.0:
            return "cheap"
        if percentile <= 2.0 / 3.0:
            return "fair"
        return "expensive"

    def compare_performance(
        self, request: ComparePerfInput | Mapping[str, Any]
    ) -> ComparePerfEnvelope:
        """Rebased performance over two or more price histories (composition).

        Reads one ``price_history`` per ticker, inner-joins on trading dates,
        and rebases every leg to 100 at the first common date. Fewer than two
        tickers or an empty date overlap is ``invalid_input``.
        """
        parsed = self._validate_input(ComparePerfInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ComparePerfEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ComparePerfEnvelope)

        def produce() -> ComparePerfEnvelope:
            joined = self._aligned_closes(parsed.tickers, parsed.resolution, parsed.range)
            if isinstance(joined, DigifetchError):
                return self._error_envelope(ComparePerfEnvelope, joined)
            dates, aligned, warnings = joined
            series = {
                ticker: [close / closes[0] * 100.0 for close in closes]
                for ticker, closes in aligned.items()
            }
            total_returns = {
                ticker: closes[-1] / closes[0] - 1.0 for ticker, closes in aligned.items()
            }
            return ComparePerfEnvelope(
                data=ComparePerfResult(
                    tickers=list(parsed.tickers),
                    dates=dates,
                    base_date=dates[0],
                    series=series,
                    total_returns=total_returns,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("compare_performance", parsed, produce)

    def correlation_matrix(
        self, request: CorrMatrixInput | Mapping[str, Any]
    ) -> CorrMatrixEnvelope:
        """Pearson correlation matrix over date-aligned daily returns.

        Identical return paths correlate at 1.0; a flat leg correlates with
        nothing (None — undefined, never a clamped zero-fill claim).
        """
        parsed = self._validate_input(CorrMatrixInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CorrMatrixEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CorrMatrixEnvelope)

        def produce() -> CorrMatrixEnvelope:
            joined = self._aligned_closes(parsed.tickers, parsed.resolution, parsed.range)
            if isinstance(joined, DigifetchError):
                return self._error_envelope(CorrMatrixEnvelope, joined)
            dates, aligned, warnings = joined
            returns = {ticker: self._simple_returns(closes) for ticker, closes in aligned.items()}
            matrix = {
                base: {
                    quote: (
                        1.0
                        if base == quote and len(returns[base]) >= 2
                        else self._pearson(returns[base], returns[quote])
                    )
                    for quote in parsed.tickers
                }
                for base in parsed.tickers
            }
            return CorrMatrixEnvelope(
                data=CorrMatrixResult(
                    tickers=list(parsed.tickers),
                    matrix=matrix,
                    common_dates=dates,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("correlation_matrix", parsed, produce)

    def relationship_graph(self, request: RelGraphInput | Mapping[str, Any]) -> RelGraphEnvelope:
        """Pair relationship: indexed prices, ratio, rolling correlation, beta."""
        parsed = self._validate_input(RelGraphInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(RelGraphEnvelope, parsed)
        if not self._enabled:
            return self._disabled(RelGraphEnvelope)

        def produce() -> RelGraphEnvelope:
            joined = self._aligned_closes(
                [parsed.base, parsed.quote], parsed.resolution, parsed.range
            )
            if isinstance(joined, DigifetchError):
                return self._error_envelope(RelGraphEnvelope, joined)
            dates, aligned, warnings = joined
            base_closes, quote_closes = aligned[parsed.base], aligned[parsed.quote]
            indexed_base = [close / base_closes[0] * 100.0 for close in base_closes]
            indexed_quote = [close / quote_closes[0] * 100.0 for close in quote_closes]
            ratio = [
                base / quote if quote > 0.0 else 0.0
                for base, quote in zip(base_closes, quote_closes, strict=False)
            ]
            base_returns = self._simple_returns(base_closes)
            quote_returns = self._simple_returns(quote_closes)
            try:
                beta: float | None = statistics.covariance(
                    base_returns, quote_returns
                ) / statistics.variance(quote_returns)
            except (statistics.StatisticsError, ZeroDivisionError):
                beta = None
            rolling: list[float | None] = [None]
            for end in range(1, len(base_returns) + 1):
                window_base = base_returns[max(0, end - parsed.window) : end]
                window_quote = quote_returns[max(0, end - parsed.window) : end]
                rolling.append(
                    self._pearson(window_base, window_quote) if len(window_base) >= 2 else None
                )
            return RelGraphEnvelope(
                data=RelGraphResult(
                    base=parsed.base,
                    quote=parsed.quote,
                    dates=dates,
                    indexed_base=indexed_base,
                    indexed_quote=indexed_quote,
                    ratio=ratio,
                    beta=beta,
                    rolling_correlation=rolling,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("relationship_graph", parsed, produce)

    def relative_valuation(self, request: RelValInput | Mapping[str, Any]) -> RelValEnvelope:
        """Peer trailing-multiples table over ticker-financials reads."""
        parsed = self._validate_input(RelValInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(RelValEnvelope, parsed)
        if not self._enabled:
            return self._disabled(RelValEnvelope)

        def produce() -> RelValEnvelope:
            rows: list[RelValRow] = []
            warnings: list[str] = []
            for ticker in parsed.tickers:
                env = self.ticker_financials({"symbol": ticker})
                warnings.extend(env.warnings)
                if isinstance(env.data, DigifetchError):
                    return RelValEnvelope(
                        data=DigifetchError(
                            code="upstream_error",
                            message=f"financials unavailable for {ticker}: {env.data.message}",
                            retryable=env.data.retryable,
                        ),
                        fetched_at=self._now(),
                        warnings=warnings,
                    )
                financials = env.data.financials
                fundamentals = financials.fundamentals
                rows.append(
                    RelValRow(
                        symbol=ticker,
                        price=financials.quote.price if financials.quote else None,
                        trailing_pe=fundamentals.trailing_pe if fundamentals else None,
                        forward_pe=fundamentals.forward_pe if fundamentals else None,
                        peg_ratio=fundamentals.peg_ratio if fundamentals else None,
                        ev_to_revenue=fundamentals.enterprise_to_revenue if fundamentals else None,
                        dividend_yield=fundamentals.dividend_yield if fundamentals else None,
                    )
                )
            covered = [row.trailing_pe for row in rows if row.trailing_pe is not None]
            return RelValEnvelope(
                data=RelValResult(
                    rows=rows,
                    median_pe=statistics.median(covered) if covered else None,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("relative_valuation", parsed, produce)

    def _statement_frame(
        self, symbol: str, period: str
    ) -> tuple[Any, float | None, Any, list[str]] | DigifetchError:
        """Ticker-financials statement rows + price + fundamentals, or an error."""
        env = self.ticker_financials({"symbol": symbol})
        if isinstance(env.data, DigifetchError):
            return DigifetchError(
                code="upstream_error",
                message=f"financials unavailable for {symbol}: {env.data.message}",
                retryable=env.data.retryable,
            )
        financials = env.data.financials
        rows = sorted(
            (
                financials.annual_statements
                if period == "annual"
                else financials.quarterly_statements
            ),
            key=lambda row: row.date or "",
        )
        price = financials.quote.price if financials.quote else None
        return rows, price, financials.fundamentals, list(env.warnings)

    def fundamental_graph(self, request: FundGraphInput | Mapping[str, Any]) -> FundGraphEnvelope:
        """One statement field's per-period series for one symbol."""
        parsed = self._validate_input(FundGraphInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(FundGraphEnvelope, parsed)
        if not self._enabled:
            return self._disabled(FundGraphEnvelope)

        def produce() -> FundGraphEnvelope:
            frame = self._statement_frame(parsed.symbol, parsed.period)
            if isinstance(frame, DigifetchError):
                return self._error_envelope(FundGraphEnvelope, frame)
            rows, _price, _fundamentals, warnings = frame
            points = [
                FundGraphPoint(date=row.date or "", value=value)
                for row in rows
                if row.date
                for value in [getattr(row, parsed.field, None)]
                if isinstance(value, (int, float)) and math.isfinite(value)
            ]
            if not points:
                return self._error_envelope(
                    FundGraphEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=(
                            f"no {parsed.field} values in {parsed.period} statements "
                            f"for {parsed.symbol}"
                        ),
                        retryable=False,
                    ),
                )
            return FundGraphEnvelope(
                data=FundGraphResult(
                    symbol=parsed.symbol,
                    field=parsed.field,
                    period=parsed.period,
                    points=points,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("fundamental_graph", parsed, produce)

    def valuation_graph(self, request: ValGraphInput | Mapping[str, Any]) -> ValGraphEnvelope:
        """Per-period earnings scaffolding plus the latest multiples snapshot."""
        parsed = self._validate_input(ValGraphInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(ValGraphEnvelope, parsed)
        if not self._enabled:
            return self._disabled(ValGraphEnvelope)

        def produce() -> ValGraphEnvelope:
            frame = self._statement_frame(parsed.symbol, parsed.period)
            if isinstance(frame, DigifetchError):
                return self._error_envelope(ValGraphEnvelope, frame)
            rows, price, fundamentals, warnings = frame
            graph_rows = [
                ValGraphRow(
                    date=row.date or "",
                    eps=row.eps,
                    total_revenue=row.total_revenue,
                    net_income=row.net_income,
                )
                for row in rows
                if row.date
            ]
            if not graph_rows:
                return self._error_envelope(
                    ValGraphEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message=(f"no {parsed.period} statements for {parsed.symbol}"),
                        retryable=False,
                    ),
                )
            return ValGraphEnvelope(
                data=ValGraphResult(
                    symbol=parsed.symbol,
                    period=parsed.period,
                    rows=graph_rows,
                    snapshot=ValGraphSnapshot(
                        price=price,
                        trailing_pe=fundamentals.trailing_pe if fundamentals else None,
                        forward_pe=fundamentals.forward_pe if fundamentals else None,
                    ),
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("valuation_graph", parsed, produce)

    def custom_chart(self, request: CustomChartInput | Mapping[str, Any]) -> CustomChartEnvelope:
        """Explicit-series alignment onto one date union (no catalog search).

        ``price`` legs read closes, ``statement`` legs read one statement
        field, ``fred`` legs read econ-series values. A failed or empty leg is
        an ``upstream_error`` naming the leg.
        """
        parsed = self._validate_input(CustomChartInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(CustomChartEnvelope, parsed)
        if not self._enabled:
            return self._disabled(CustomChartEnvelope)

        def produce() -> CustomChartEnvelope:
            leg_values: dict[str, dict[str, float]] = {}
            warnings: list[str] = []
            for leg in parsed.series:
                key, values, leg_warnings, error = self._custom_chart_leg(leg)
                warnings.extend(leg_warnings)
                if error is not None:
                    return self._error_envelope(CustomChartEnvelope, error)
                assert values is not None
                leg_values[key] = values
            dates = sorted({day for values in leg_values.values() for day in values})
            columns = {
                key: [values.get(day) for day in dates] for key, values in leg_values.items()
            }
            return CustomChartEnvelope(
                data=CustomChartResult(dates=dates, columns=columns),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("custom_chart", parsed, produce)

    def _custom_chart_leg(
        self, leg: Any
    ) -> tuple[str, dict[str, float] | None, list[str], DigifetchError | None]:
        """One explicit leg's (key, date->value): error names the leg, never generic."""
        if leg.source == "price":
            key = leg.symbol or "price"
            env = self.price_history(
                {"symbol": leg.symbol, "resolution": leg.resolution, "range": leg.range}
            )
            if isinstance(env.data, DigifetchError):
                return (
                    key,
                    None,
                    list(env.warnings),
                    DigifetchError(
                        code="upstream_error",
                        message=f"price leg unavailable for {leg.symbol}: {env.data.message}",
                        retryable=env.data.retryable,
                    ),
                )
            values = {
                bar.date: bar.close
                for bar in env.data.bars
                if bar.close is not None and math.isfinite(bar.close)
            }
            if not values:
                return (
                    key,
                    None,
                    list(env.warnings),
                    DigifetchError(
                        code="upstream_error",
                        message=f"price leg for {leg.symbol} carries no closes",
                        retryable=False,
                    ),
                )
            return key, values, list(env.warnings), None
        if leg.source == "statement":
            key = f"{leg.symbol}:{leg.field}"
            frame = self._statement_frame(leg.symbol or "", "annual")
            if isinstance(frame, DigifetchError):
                return key, None, [], frame
            rows, _price, _fundamentals, frame_warnings = frame
            values = {
                row.date: value
                for row in rows
                if row.date
                for value in [getattr(row, leg.field, None)]
                if isinstance(value, (int, float)) and math.isfinite(value)
            }
            if not values:
                return (
                    key,
                    None,
                    frame_warnings,
                    DigifetchError(
                        code="upstream_error",
                        message=f"statement leg {key} carries no values",
                        retryable=False,
                    ),
                )
            return key, values, frame_warnings, None
        key = f"FRED:{leg.ref}"
        env = self.econ_series({"series_id": leg.ref or "", "limit": 100})
        if isinstance(env.data, DigifetchError):
            return (
                key,
                None,
                list(env.warnings),
                DigifetchError(
                    code="upstream_error",
                    message=f"fred leg unavailable for {leg.ref}: {env.data.message}",
                    retryable=env.data.retryable,
                ),
            )
        values = {
            observation.date: observation.value
            for observation in env.data.observations
            if observation.value is not None and math.isfinite(observation.value)
        }
        if not values:
            return (
                key,
                None,
                list(env.warnings),
                DigifetchError(
                    code="upstream_error",
                    message=f"fred leg {leg.ref} carries no values",
                    retryable=False,
                ),
            )
        return key, values, list(env.warnings), None

    def market_valuation(self, request: MarketValInput | Mapping[str, Any]) -> MarketValEnvelope:
        """Shiller CAPE plus optional econ ratios, each against history thirds."""
        parsed = self._validate_input(MarketValInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(MarketValEnvelope, parsed)
        if not self._enabled:
            return self._disabled(MarketValEnvelope)

        def produce() -> MarketValEnvelope:
            env = self.shiller({"limit": parsed.limit})
            warnings: list[str] = list(env.warnings)
            if isinstance(env.data, DigifetchError):
                return self._error_envelope(MarketValEnvelope, env.data)
            capes = [
                (observation.date, observation.cape)
                for observation in env.data.observations
                if observation.cape is not None and math.isfinite(observation.cape)
            ]
            if not capes:
                return self._error_envelope(
                    MarketValEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Shiller series carries no CAPE values",
                        retryable=False,
                    ),
                )
            cape_date, cape = capes[-1]
            ranked = sum(1 for _, value in capes if value <= cape) / len(capes)
            ratios: list[EconRatio] = []
            for series_id in parsed.econ_series_ids:
                leg = self.econ_series({"series_id": series_id, "limit": parsed.ratio_limit})
                warnings.extend(leg.warnings)
                if isinstance(leg.data, DigifetchError):
                    warnings.append(f"ratio {series_id} skipped: {leg.data.message}")
                    continue
                prints = [
                    (observation.date, observation.value)
                    for observation in leg.data.observations
                    if observation.value is not None and math.isfinite(observation.value)
                ]
                if not prints:
                    warnings.append(f"ratio {series_id} skipped: no prints")
                    continue
                ratio_date, ratio_value = prints[0]
                percentile = sum(1 for _, value in prints if value <= ratio_value) / len(prints)
                ratios.append(
                    EconRatio(
                        series_id=series_id,
                        value=ratio_value,
                        date=ratio_date,
                        percentile=percentile,
                        zone=self._history_zone(percentile),
                    )
                )
            return MarketValEnvelope(
                data=MarketValResult(
                    cape=cape,
                    cape_date=cape_date,
                    cape_percentile=ranked,
                    zone=self._history_zone(ranked),
                    n_observations=len(capes),
                    ratios=ratios,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("market_valuation", parsed, produce)

    def money_markets(self, request: MoneyMarketsInput | Mapping[str, Any]) -> MoneyMarketsEnvelope:
        """SOFR/EFFR/reserve prints over FRED econ-series reads (composition).

        Reports the latest prints plus the SOFR-minus-EFFR spread. A failed
        leg (or one with no prints) is an ``upstream_error`` naming the series.
        """
        parsed = self._validate_input(MoneyMarketsInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(MoneyMarketsEnvelope, parsed)
        if not self._enabled:
            return self._disabled(MoneyMarketsEnvelope)

        def produce() -> MoneyMarketsEnvelope:
            legs = (
                ("sofr", parsed.sofr_series),
                ("effr", parsed.effr_series),
                ("reserves", parsed.reserves_series),
            )
            prints: dict[str, tuple[str, float]] = {}
            warnings: list[str] = []
            for leg, series_id in legs:
                env = self.econ_series(
                    {"series_id": series_id, "limit": parsed.limit, "sort_order": "desc"}
                )
                warnings.extend(env.warnings)
                if isinstance(env.data, DigifetchError):
                    return MoneyMarketsEnvelope(
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
                    if observation.value is not None and math.isfinite(observation.value)
                ]
                if not dated:
                    return MoneyMarketsEnvelope(
                        data=DigifetchError(
                            code="upstream_error",
                            message=f"econ series {series_id} carries no prints",
                            retryable=False,
                        ),
                        fetched_at=self._now(),
                        warnings=warnings,
                    )
                prints[leg] = dated[0]
            (sofr_date, sofr), (effr_date, effr) = prints["sofr"], prints["effr"]
            reserves_date, reserves = prints["reserves"]
            return MoneyMarketsEnvelope(
                data=MoneyMarketsResult(
                    sofr=sofr,
                    effr=effr,
                    spread=sofr - effr,
                    reserves=reserves,
                    sofr_date=sofr_date,
                    effr_date=effr_date,
                    reserves_date=reserves_date,
                ),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("money_markets", parsed, produce)

    @staticmethod
    def _venue_prob(value: Any) -> float | None:
        """Kalshi wire price in probability units (dollar-or-cent wire values)."""
        prob = _venue_float(value)
        if prob is None or prob < 0.0:
            return None
        if prob > 1.0:
            prob = prob / 100.0
        return prob if 0.0 <= prob <= 1.0 else None

    @staticmethod
    def _meeting_day(value: Any) -> str | None:
        """Date part of a Kalshi ``close_time`` (the meeting-day anchor)."""
        if not isinstance(value, str) or len(value) < 10:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return value[:10] if value[:10].count("-") == 2 else None

    def rate_path(self, request: RatePathInput | Mapping[str, Any]) -> RatePathEnvelope:
        """US rate path over live Kalshi KXFED threshold markets (venue-direct).

        Reads one page of open KXFED markets through the venue path, groups by
        meeting day, and differences each survival ladder into a 25bp outcome
        distribution with the fed-prob ladder semantics. Anonymous, polled —
        enrichment only, never a pipeline primary.
        """
        parsed = self._validate_input(RatePathInput, request)
        if isinstance(parsed, DigifetchError):
            return self._error_envelope(RatePathEnvelope, parsed)
        if not self._enabled:
            return self._disabled(RatePathEnvelope)

        def produce() -> RatePathEnvelope:
            raw = self._request_json(
                "GET",
                "/markets",
                params={
                    "series_ticker": "KXFED",
                    "status": "open",
                    "limit": str(parsed.limit),
                },
                base_url=KALSHI_TRADE_BASE_URL,
                label="Kalshi",
            )
            if isinstance(raw, DigifetchError):
                return self._error_envelope(RatePathEnvelope, raw)
            payload = raw.data if isinstance(raw.data, Mapping) else {}
            markets = payload.get("markets")
            if not isinstance(markets, list):
                return self._error_envelope(
                    RatePathEnvelope,
                    DigifetchError(
                        code="upstream_error",
                        message="Kalshi KXFED read returned an unexpected payload",
                        retryable=False,
                    ),
                )
            ladders: dict[str, dict[float, float]] = {}
            for market in markets:
                if not isinstance(market, Mapping):
                    continue
                meeting = self._meeting_day(market.get("close_time"))
                strike_raw = market.get("floor_strike", market.get("strike"))
                if strike_raw is None:
                    strike_raw = market.get("floorStrike")
                try:
                    strike = float(strike_raw)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(strike):
                    continue
                bid = self._venue_prob(market.get("yes_bid_dollars", market.get("yes_bid")))
                ask = self._venue_prob(market.get("yes_ask_dollars", market.get("yes_ask")))
                if bid is not None and ask is not None:
                    prob: float | None = round((bid + ask) / 2.0, 4)
                else:
                    prob = self._venue_prob(
                        market.get("last_price_dollars", market.get("last_price"))
                    )
                if meeting is None or prob is None:
                    continue
                ladders.setdefault(meeting, {})[strike] = prob
            meetings: list[RateMeeting] = []
            warnings: list[str] = []
            for meeting in sorted(ladders):
                derived = fed_distribution_from_ladder(ladders[meeting])
                if not derived:
                    warnings.append(f"{meeting}: fewer than two strikes, skipped")
                    continue
                meetings.append(
                    RateMeeting(
                        meeting=meeting,
                        distribution=derived["distribution"],
                        most_likely=derived["most_likely"],
                        n_strikes=derived["n_strikes"],
                    )
                )
            if not meetings:
                return RatePathEnvelope(
                    data=DigifetchError(
                        code="upstream_error",
                        message="no KXFED meeting carries a usable strike ladder",
                        retryable=False,
                    ),
                    fetched_at=self._now(),
                    warnings=warnings,
                )
            return RatePathEnvelope(
                data=RatePathResult(meetings=meetings),
                fetched_at=self._now(),
                warnings=warnings,
            )

        return self._cached("rate_path", parsed, produce)

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
        # both session fingerprints: responses are entitlement-sensitive, so a
        # cached preview/full report must never be served across sessions —
        # and the Substack reader is account-sensitive under its own cookie.
        key = (
            name,
            session_cache_fingerprint(self._session_cookie),
            session_cache_fingerprint(self._substack_cookie),
            request.model_dump_json(),
        )
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

    def _substack_cookies(self) -> dict[str, str] | None:
        """Own-account Substack cookies (bare token fans out over both names).

        Only the Substack reader sends these; Cloud routes never see them.
        Mirrors :meth:`_session_cookies` (bare token or ``name=value``).
        """
        raw = self._substack_cookie
        if not raw:
            return None
        if "=" in raw:
            name, _, value = raw.partition("=")
            name, value = name.strip(), value.strip()
            if name and value:
                return {name: value}
        # A bare token is sent under every upstream Substack cookie name, the
        # same fallback the TS plugin uses when it has not observed a name.
        return {name: raw for name in SUBSTACK_COOKIE_NAMES}

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
        cookies: dict[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
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
        # An explicit cookie jar (the own-account Substack reader) wins; gated
        # Cloud routes attach the Gloom session cookie, ungated reads send none.
        if cookies is None:
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
                    headers=headers,
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

    def _request_text(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        retry_policy: RetryPolicy | None = None,
        base_url: str | None = None,
        label: str = "Gloomberb",
        headers: Mapping[str, str] | None = None,
    ) -> str | DigifetchError:
        """Raw-text read for non-JSON venues (the Nasdaq halt RSS feed).

        Mirrors :meth:`_request_json`'s transport contract (kill switch,
        breaker, retry, per-label HTTP mapping) without the JSON envelope
        parsing — the caller validates the body shape itself.
        """
        if not self._enabled:
            return DigifetchError(
                code="upstream_error",
                message=f"Gloomberb data family disabled by kill switch ({GLOOMBERB_ENABLED_ENV})",
                retryable=False,
            )
        breaker = self._breaker_error()
        if breaker is not None:
            return breaker
        url = f"{base_url or self._base_url}{path}"

        def attempt() -> FetchResult:
            self._rate_limiter.acquire()
            try:
                return self._fetcher.fetch(
                    url,
                    method=method,
                    params=params,
                    headers=headers,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    raise _UpstreamServerError(str(exc)) from exc
                raise

        try:
            result = with_retry(
                attempt,
                retry_policy or self._retry_policy,
                description=f"{label.lower()} {method} {path}",
            )
        except httpx.HTTPStatusError as exc:
            error = self._map_http_error(exc, label=label)
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
            return DigifetchError(
                code="upstream_error",
                message=f"{label} request blocked by the SSRF guard: {exc}",
                retryable=False,
            )
        except httpx.HTTPError as exc:
            self._record_failure()
            return DigifetchError(
                code="upstream_error",
                message=f"{label} request failed: {exc}",
                retryable=False,
            )
        self._record_success()
        return result.text
