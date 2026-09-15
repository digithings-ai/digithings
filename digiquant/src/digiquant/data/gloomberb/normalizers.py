"""Normalizers ported from Gloomberb's client-side TS layer (§5.4).

The upstream TS client normalizes raw wire JSON before display; a raw-JSON
Python client must port or consciously drop each rule. Ported here:

* currency units - ``GBp``/``GBX`` -> ``GBP`` divisor 100 (also ``ILA``/``ZAc``)
  (``utils/currency-units.ts``);
* interval tokens - ``5m -> 5min``, ``1d -> 1day``, ``1wk -> 1week``
  (``normalizers.ts:253-274``);
* exchange-timezone date parsing for bar dates, which arrive as ISO datetimes
  but may also arrive as exchange-local wall times (``normalizers.ts:108-177``);
* malformed-intraday rejection for non-Yahoo upstreams
  (``time-series/history-quality.ts``);
* day-range reconciliation of quote low/high vs session data
  (``market-data/quotes/day-range.ts``);
* the §5.3 freshness union (wire ``stale`` vs ``dataSource``/``delayMinutes``).

Conscious narrowings vs upstream are documented at their functions
(``same_units`` skips price-basis; the exchange-timezone table is trimmed to the
venues the contract realistically touches).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .models import (
    INTRADAY_RESOLUTIONS,
    AnalystAction,
    AnalystPriceTarget,
    AnalystResearchResult,
    CompanyProfile,
    CorporateAction,
    ExchangeRateResult,
    FinancialStatement,
    Fundamentals,
    Holder,
    InstrumentSearchResult,
    NewsItem,
    OptionContract,
    OptionsChain,
    PriceBar,
    Quote,
    QuoteBatchItem,
    SecFiling,
    SecFilingDocument,
    StatementHistory,
    TickerFinancials,
)

__all__ = [
    "CurrencyUnit",
    "resolve_currency_unit",
    "normalize_price_value_by_divisor",
    "finite_number",
    "INTERVAL_TOKENS",
    "to_cloud_interval",
    "is_intraday_interval",
    "is_intraday_resolution",
    "EXCHANGE_TIME_ZONES",
    "resolve_exchange_timezone",
    "parse_cloud_price_point_date",
    "normalize_bars",
    "is_malformed_intraday_history",
    "consolidate_day_range",
    "has_likely_quote_unit_mismatch",
    "Freshness",
    "derive_freshness",
    "STALE_NOTE",
    "DELAYED_NOTE",
    "normalize_quote",
    "normalize_quotes_batch_items",
    "normalize_financials",
    "normalize_options_chain",
    "normalize_holders",
    "normalize_analyst_research",
    "normalize_corporate_actions",
    "normalize_news_item",
    "normalize_news_list",
    "normalize_search_results",
    "normalize_exchange_rate",
    "normalize_sec_filings",
    "normalize_sec_documents",
]

# ---------------------------------------------------------------------------
# Currency units (utils/currency-units.ts)
# ---------------------------------------------------------------------------

_SUB_UNIT_CURRENCIES: dict[str, tuple[str, int]] = {
    "GBp": ("GBP", 100),
    "GBX": ("GBP", 100),
    "ILA": ("ILS", 100),
    "ZAc": ("ZAR", 100),
}


@dataclass(frozen=True)
class CurrencyUnit:
    currency: str
    divisor: int


def resolve_currency_unit(currency: str | None) -> CurrencyUnit:
    """Resolve a wire currency code to its canonical unit and price divisor.

    Exact keys (``GBp``, ``GBX``, ...) select the subunit divisor; anything else
    is upper-cased with divisor 1, matching upstream's exact-match-then-uppercase
    behavior (so lowercase ``gbp`` is *not* treated as pence).
    """
    raw = (currency or "").strip()
    if not raw:
        return CurrencyUnit("", 1)
    known = _SUB_UNIT_CURRENCIES.get(raw)
    if known is not None:
        return CurrencyUnit(known[0], known[1])
    return CurrencyUnit(raw.upper(), 1)


def normalize_price_value_by_divisor(value: float | None, divisor: int) -> float | None:
    """Divide *value* by *divisor*, leaving nulls and divisor 1 untouched."""
    if value is None or not math.isfinite(value) or divisor == 1:
        return value
    return value / divisor


# ---------------------------------------------------------------------------
# Interval tokens (normalizers.ts:253-274)
# ---------------------------------------------------------------------------

INTERVAL_TOKENS: dict[str, str] = {
    "1m": "1min",
    "5m": "5min",
    "15m": "15min",
    "30m": "30min",
    "45m": "45min",
    "1d": "1day",
    "1wk": "1week",
    "1mo": "1month",
}

_INTRADAY_INTERVAL_RE = re.compile(r"^\d+(min|h)$", re.IGNORECASE)


def to_cloud_interval(interval: str) -> str:
    """Map a contract resolution token to the wire interval token."""
    return INTERVAL_TOKENS.get(interval, interval)


def is_intraday_interval(interval: str) -> bool:
    """True for intervals the upstream TS treats as intraday (``\\d+(min|h)``)."""
    return bool(_INTRADAY_INTERVAL_RE.match(interval.strip()))


def is_intraday_resolution(resolution: str) -> bool:
    """True for the intraday chart resolutions in the contract."""
    return resolution in INTRADAY_RESOLUTIONS


# ---------------------------------------------------------------------------
# Exchange timezones + date parsing (normalizers.ts:108-177)
# ---------------------------------------------------------------------------

# Trimmed subset of EXCHANGE_TIME_ZONES (utils/exchanges.ts). Unknown venues
# fall back to the wire value as-is, exactly like upstream's null timezone.
EXCHANGE_TIME_ZONES: dict[str, str] = {
    "NASDAQ": "America/New_York",
    "NYSE": "America/New_York",
    "ARCA": "America/New_York",
    "AMEX": "America/New_York",
    "BATS": "America/New_York",
    "TSX": "America/Toronto",
    "TSXV": "America/Toronto",
    "CSE": "America/Toronto",
    "BMV": "America/Mexico_City",
    "B3": "America/Sao_Paulo",
    "BYMA": "America/Argentina/Buenos_Aires",
    "LSE": "Europe/London",
    "EPA": "Europe/Paris",
    "AMS": "Europe/Amsterdam",
    "BRU": "Europe/Brussels",
    "LIS": "Europe/Lisbon",
    "BIT": "Europe/Rome",
    "HEL": "Europe/Helsinki",
    "CPH": "Europe/Copenhagen",
    "OSL": "Europe/Oslo",
    "ICEX": "Atlantic/Reykjavik",
    "WSE": "Europe/Warsaw",
    "PSE": "Europe/Prague",
    "VIE": "Europe/Vienna",
    "FWB": "Europe/Berlin",
    "FWB2": "Europe/Berlin",
    "XETRA": "Europe/Berlin",
    "SWX": "Europe/Zurich",
    "SFB": "Europe/Stockholm",
    "JSE": "Africa/Johannesburg",
    "TASE": "Asia/Jerusalem",
    "HKEX": "Asia/Hong_Kong",
    "JPX": "Asia/Tokyo",
    "TPEX": "Asia/Taipei",
    "TWSE": "Asia/Taipei",
    "NSE": "Asia/Kolkata",
    "BSE": "Asia/Kolkata",
    "SGX": "Asia/Singapore",
    "KRX": "Asia/Seoul",
    "KOSDAQ": "Asia/Seoul",
    "SSE": "Asia/Shanghai",
    "SZSE": "Asia/Shanghai",
    "ASX": "Australia/Sydney",
    "NZX": "Pacific/Auckland",
    "CCC": "UTC",
}

_LOCAL_DATE_TIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2})(?:\.\d{1,3})?)?)?$"
)
_EXPLICIT_TIME_ZONE_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)
_SESSION_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def resolve_exchange_timezone(exchange: str | None) -> str | None:
    """IANA timezone for a canonical exchange code, or None when unknown."""
    canonical = (exchange or "").strip().upper()
    return EXCHANGE_TIME_ZONES.get(canonical)


def _zone(name: str | None) -> ZoneInfo | None:
    if not name:
        return None
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def _to_utc(value: datetime, zone: ZoneInfo | None) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc)
    if zone is not None:
        return value.replace(tzinfo=zone).astimezone(timezone.utc)
    return value.replace(tzinfo=timezone.utc)


def parse_cloud_price_point_date(
    value: str | int | float | datetime | None,
    *,
    exchange: str = "",
    timezone_name: str | None = None,
) -> datetime:
    """Parse a wire bar date to an aware UTC datetime.

    Wire history dates are ISO datetimes (often with ``Z``). When a value
    arrives without an explicit offset and the exchange timezone is known, the
    wall time is interpreted in that zone and converted to UTC - the same rule
    as upstream's ``parseCloudPricePointDate``. A date-only value becomes
    midnight UTC. Raises :class:`ValueError` for an unparseable value.
    """
    zone = _zone(timezone_name or resolve_exchange_timezone(exchange))
    if isinstance(value, datetime):
        return _to_utc(value, zone)
    if isinstance(value, bool) or value is None:
        raise ValueError(f"unparseable bar date {value!r}")
    if isinstance(value, (int, float)):
        if not math.isfinite(value):
            raise ValueError(f"unparseable bar date {value!r}")
        return datetime.fromtimestamp(float(value) / 1000.0, tz=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"unparseable bar date {value!r}")
    text = value.strip()
    if _EXPLICIT_TIME_ZONE_RE.search(text):
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)
    match = _LOCAL_DATE_TIME_RE.match(text)
    if match is None:
        raise ValueError(f"unparseable bar date {value!r}")
    year, month, day = int(match[1]), int(match[2]), int(match[3])
    if match[4] is None:
        return datetime(year, month, day, tzinfo=timezone.utc)
    hour, minute, second = int(match[4]), int(match[5] or 0), int(match[6] or 0)
    local = datetime(year, month, day, hour, minute, second, tzinfo=zone or timezone.utc)
    return local.astimezone(timezone.utc)


def finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _format_bar_date(value: datetime, *, intraday: bool) -> str:
    if not intraday:
        return value.astimezone(timezone.utc).date().isoformat()
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_bars(
    raw_points: Sequence[Any] | None,
    *,
    resolution: str,
    exchange: str = "",
    divisor: int = 1,
    timezone_name: str | None = None,
) -> list[PriceBar]:
    """Map raw wire price points to :class:`PriceBar` (sorted, deduped).

    Ports upstream ``normalizePriceHistory``: unparseable dates and non-finite
    closes are dropped, out-of-order bars are sorted, and a series whose points
    all share one timestamp collapses to ``[]``. Intraday resolutions keep a
    full ISO datetime; daily/weekly/monthly resolutions keep the date only.
    """
    intraday = is_intraday_resolution(resolution)
    pairs: list[tuple[datetime, PriceBar]] = []
    for raw in raw_points or []:
        if not isinstance(raw, Mapping):
            continue
        try:
            parsed = parse_cloud_price_point_date(
                raw.get("date"), exchange=exchange, timezone_name=timezone_name
            )
        except (TypeError, ValueError):
            continue
        close = finite_number(raw.get("close"))
        if close is None:
            continue
        bar = PriceBar(
            date=_format_bar_date(parsed, intraday=intraday),
            open=normalize_price_value_by_divisor(finite_number(raw.get("open")), divisor),
            high=normalize_price_value_by_divisor(finite_number(raw.get("high")), divisor),
            low=normalize_price_value_by_divisor(finite_number(raw.get("low")), divisor),
            close=normalize_price_value_by_divisor(close, divisor) or close,
            volume=finite_number(raw.get("volume")),
        )
        pairs.append((parsed, bar))
    if not pairs:
        return []
    if len(pairs) == 1:
        return [pairs[0][1]]
    if all(stamp == pairs[0][0] for stamp, _ in pairs):
        return []
    pairs.sort(key=lambda pair: pair[0])
    return [bar for _, bar in pairs]


# ---------------------------------------------------------------------------
# Malformed intraday history (time-series/history-quality.ts)
# ---------------------------------------------------------------------------

_MAX_NEIGHBOR_GAP_SECONDS = 60.0 * 60.0
_STABLE_NEIGHBOR_CLOSE_RATIO = 0.01
_ISOLATED_OHLC_OUTLIER_RATIO = 0.04


def _relative_difference(value: float, reference: float) -> float:
    if reference == 0:
        return 0.0 if value == 0 else math.inf
    return abs(value - reference) / abs(reference)


def _bar_timestamp(bar: PriceBar) -> float | None:
    try:
        parsed = datetime.fromisoformat(bar.date.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def is_malformed_intraday_history(bars: Sequence[PriceBar]) -> bool:
    """True when an interior bar looks like an isolated OHLC outlier.

    An outlier is a bar whose neighbors are within one hour and roughly the same
    close (1%) while its own open/high/low is more than 4% from its close. This
    is the upstream ``hasMalformedIntradayHistory`` rule; the caller applies it
    only for non-Yahoo upstreams, as upstream does.
    """
    for index in range(1, len(bars) - 1):
        previous = bars[index - 1]
        point = bars[index]
        following = bars[index + 1]
        previous_ts = _bar_timestamp(previous)
        point_ts = _bar_timestamp(point)
        next_ts = _bar_timestamp(following)
        if previous_ts is None or point_ts is None or next_ts is None:
            continue
        previous_gap = point_ts - previous_ts
        next_gap = next_ts - point_ts
        if previous_gap <= 0 or next_gap <= 0:
            continue
        if previous_gap > _MAX_NEIGHBOR_GAP_SECONDS or next_gap > _MAX_NEIGHBOR_GAP_SECONDS:
            continue
        if _relative_difference(previous.close, point.close) > _STABLE_NEIGHBOR_CLOSE_RATIO:
            continue
        if _relative_difference(following.close, point.close) > _STABLE_NEIGHBOR_CLOSE_RATIO:
            continue
        for value in (point.open, point.high, point.low):
            if value is not None and _relative_difference(value, point.close) > (
                _ISOLATED_OHLC_OUTLIER_RATIO
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# Day-range reconciliation (market-data/quotes/day-range.ts)
# ---------------------------------------------------------------------------

_LIKELY_UNIT_MISMATCH_RATIOS: dict[str, tuple[float, ...]] = {
    "BHD": (1000.0,),
    "GBP": (100.0,),
    "ILS": (100.0,),
    "JOD": (1000.0,),
    "KWD": (1000.0,),
    "OMR": (1000.0,),
    "TND": (1000.0,),
    "ZAR": (100.0,),
}


def _unit_probe(value: Quote | Mapping[str, Any] | None) -> tuple[str, float] | None:
    if value is None:
        return None
    if isinstance(value, Quote):
        currency, price = value.currency, value.price
    elif isinstance(value, Mapping):
        currency, price = value.get("currency"), value.get("price")
    else:
        return None
    if not isinstance(currency, str):
        return None
    number = finite_number(price)
    return (currency, number) if number is not None else None


def has_likely_quote_unit_mismatch(
    left: Quote | Mapping[str, Any] | None,
    right: Quote | Mapping[str, Any] | None,
) -> bool:
    """True when two same-currency prices look like a subunit mismatch."""
    left_probe = _unit_probe(left)
    right_probe = _unit_probe(right)
    if left_probe is None or right_probe is None:
        return False
    left_unit = resolve_currency_unit(left_probe[0])
    right_unit = resolve_currency_unit(right_probe[0])
    if not left_unit.currency or left_unit.currency != right_unit.currency:
        return False
    left_price, right_price = left_probe[1], right_probe[1]
    if left_price <= 0 or right_price <= 0:
        return False

    def ratio_within(ratio: float, target: float, tolerance: float = 0.05) -> bool:
        return abs(ratio - target) / target < tolerance

    if left_unit.divisor != right_unit.divisor:
        left_canonical = left_price / left_unit.divisor
        right_canonical = right_price / right_unit.divisor
        normalized = left_canonical / right_canonical
        normalized = normalized if normalized >= 1 else 1 / normalized
        if ratio_within(normalized, 1.0):
            return True
    ratio = left_price / right_price
    ratio = ratio if ratio >= 1 else 1 / ratio
    targets = _LIKELY_UNIT_MISMATCH_RATIOS.get(left_unit.currency, (100.0,))
    return any(ratio_within(ratio, target) for target in targets)


def _positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def _session_date(quote: Quote) -> str | None:
    declared = quote.change_session_date
    declared_date = (
        declared if isinstance(declared, str) and _SESSION_DATE_RE.match(declared) else None
    )
    zone = _zone(resolve_exchange_timezone(quote.listing_exchange_name or quote.exchange_name))
    if zone is None:
        return declared_date
    if not _positive(quote.last_updated):
        return None
    observed = datetime.fromtimestamp(
        float(quote.last_updated) / 1000.0, tz=timezone.utc
    ).astimezone(zone)
    observed_date = observed.date().isoformat()
    if declared_date is not None and declared_date != observed_date:
        return None
    return observed_date


def _canonical_exchange(value: str | None) -> str:
    return (value or "").strip().upper()


def _same_units(left: Quote, right: Quote) -> bool:
    # Conscious narrowing vs upstream: price-basis (per-unit vs percent-of-par)
    # is not modeled on the Python Quote, so only currency-unit equality and the
    # likely-mismatch heuristic gate the merge.
    left_unit = resolve_currency_unit(left.currency)
    right_unit = resolve_currency_unit(right.currency)
    if not left_unit.currency or left_unit.currency != right_unit.currency:
        return False
    if left_unit.divisor != right_unit.divisor:
        return False
    return not has_likely_quote_unit_mismatch(left, right)


def consolidate_day_range(quote: Quote, previous: Quote | None = None) -> Quote:
    """Reconcile a quote's day high/low with the session data (§5.4).

    ``previous`` is optional in a single-observation client, but the full
    upstream same-session merge is ported so a future stream/previous-quote
    caller behaves identically.
    """
    compatible = previous is None or _same_units(previous, quote)
    next_date = _session_date(quote)
    high = quote.high
    low = quote.low
    if previous is not None and compatible:
        same_regular_session = (
            previous.market_state == "REGULAR"
            and quote.market_state == "REGULAR"
            and previous.symbol == quote.symbol
            and _canonical_exchange(previous.listing_exchange_name or previous.exchange_name)
            == _canonical_exchange(quote.listing_exchange_name or quote.exchange_name)
            and next_date is not None
            and _session_date(previous) == next_date
        )
        if same_regular_session:
            if _positive(previous.high):
                high = max(high, previous.high) if _positive(high) else previous.high
            if _positive(previous.low):
                low = min(low, previous.low) if _positive(low) else previous.low
        elif quote.market_state != "REGULAR":
            # Extended-hours trades are not part of the regular-session range.
            high = previous.high if high is None else high
            low = previous.low if low is None else low
    if (
        quote.market_state == "REGULAR"
        and quote.session_confidence != "unknown"
        and not quote.stale
        and _positive(quote.price)
        and next_date is not None
    ):
        # Do not fabricate a full-day range from a stream that supplies only last.
        if _positive(high) and not has_likely_quote_unit_mismatch(
            quote, {"currency": quote.currency, "price": high}
        ):
            high = max(high, quote.price)
        if _positive(low) and not has_likely_quote_unit_mismatch(
            quote, {"currency": quote.currency, "price": low}
        ):
            low = min(low, quote.price)
    return quote.model_copy(update={"high": high, "low": low})


# ---------------------------------------------------------------------------
# Freshness union (§5.3)
# ---------------------------------------------------------------------------

STALE_NOTE = "Upstream cache stale"
DELAYED_NOTE = "Free-tier data delayed up to 15 minutes"


@dataclass(frozen=True)
class Freshness:
    """The two distinct freshness signals kept separate in the envelope."""

    stale: bool
    delay_note: str | None


def derive_freshness(
    *,
    stale: bool = False,
    data_source: str | None = None,
    delay_minutes: float | None = None,
) -> Freshness:
    """Union of wire ``stale`` and the free-tier delay signals (§5.3).

    Wire ``stale: true`` (an expired cache being served) maps to
    :data:`STALE_NOTE` and ``stale=True``; ``dataSource == "delayed"`` or
    ``delayMinutes > 0`` maps to :data:`DELAYED_NOTE` and stays ``stale=False``.
    When both are present the stale note wins (the more severe signal) - both
    conditions are still reflected, since ``stale`` stays True.
    """
    if stale:
        return Freshness(stale=True, delay_note=STALE_NOTE)
    delayed = data_source == "delayed" or (delay_minutes is not None and delay_minutes > 0)
    if delayed:
        return Freshness(stale=False, delay_note=DELAYED_NOTE)
    return Freshness(stale=False, delay_note=None)


# ---------------------------------------------------------------------------
# Payload mappers
# ---------------------------------------------------------------------------

_DIVISOR_PRICE_FIELDS = (
    "price",
    "change",
    "previousClose",
    "regularClose",
    "high52w",
    "low52w",
    "bid",
    "ask",
    "open",
    "high",
    "low",
    "mark",
    "lastTradePrice",
    "preMarketPrice",
    "preMarketChange",
    "postMarketPrice",
    "postMarketChange",
)


def normalize_quote(raw: Mapping[str, Any]) -> Quote:
    """Resolve currency units, apply the divisor, then reconcile day range."""
    unit = resolve_currency_unit(raw.get("currency"))  # type: ignore[arg-type]
    data = dict(raw)
    for field in _DIVISOR_PRICE_FIELDS:
        if field in data:
            number = finite_number(data[field])
            if number is not None and unit.divisor != 1:
                data[field] = normalize_price_value_by_divisor(number, unit.divisor)
    if unit.currency:
        data["currency"] = unit.currency
    return consolidate_day_range(Quote.model_validate(data))


def normalize_quotes_batch_items(items: Sequence[Any] | None) -> list[QuoteBatchItem]:
    """Map wire batch items; stale items become a null quote with a reason."""
    out: list[QuoteBatchItem] = []
    for item in items or []:
        if not isinstance(item, Mapping):
            continue
        status = str(item.get("status") or "")
        stale = item.get("stale") is True
        data = item.get("data")
        quote: Quote | None = None
        reason = item.get("reasonCode")
        if status in ("success", "partial") and isinstance(data, Mapping) and not stale:
            quote = normalize_quote(data)
        elif stale:
            reason = reason or "stale"
        out.append(
            QuoteBatchItem(
                symbol=str(item.get("symbol") or ""),
                exchange=str(item.get("exchange") or ""),
                status=status,
                quote=quote,
                reason_code=str(reason) if reason is not None else None,
            )
        )
    return out


def _statement_list(value: Any) -> list[FinancialStatement]:
    if not isinstance(value, list):
        return []
    return [FinancialStatement.model_validate(row) for row in value if isinstance(row, Mapping)]


def _optional_model(model: type[Any], value: Any) -> Any:
    return model.model_validate(value) if isinstance(value, Mapping) else None


def normalize_financials(raw: Mapping[str, Any]) -> TickerFinancials:
    """Map a raw financials payload, reusing the quote divisor for price history."""
    quote_raw = raw.get("quote")
    quote = normalize_quote(quote_raw) if isinstance(quote_raw, Mapping) else None
    divisor = (
        resolve_currency_unit(quote_raw.get("currency")).divisor  # type: ignore[arg-type]
        if isinstance(quote_raw, Mapping)
        else 1
    )
    exchange = ""
    if quote is not None:
        exchange = quote.listing_exchange_name or quote.exchange_name or ""
    raw_points = raw.get("priceHistory")
    bars = (
        normalize_bars(raw_points, resolution="1d", exchange=exchange, divisor=divisor)
        if isinstance(raw_points, list)
        else []
    )
    return TickerFinancials(
        quote=quote,
        financial_currency=raw.get("financialCurrency"),
        statement_history=_optional_model(StatementHistory, raw.get("statementHistory")),
        profile=_optional_model(CompanyProfile, raw.get("profile")),
        fundamentals=_optional_model(Fundamentals, raw.get("fundamentals")),
        annual_statements=_statement_list(raw.get("annualStatements")),
        quarterly_statements=_statement_list(raw.get("quarterlyStatements")),
        price_history=bars,
    )


def normalize_options_chain(raw: Mapping[str, Any]) -> OptionsChain:
    """Map an options chain, normalizing the calls/puts arrays to ``side``."""
    data = dict(raw)
    data["calls"] = [
        dict(OptionContract.model_validate({**entry, "side": "call"}))
        for entry in raw.get("calls") or []
        if isinstance(entry, Mapping)
    ]
    data["puts"] = [
        dict(OptionContract.model_validate({**entry, "side": "put"}))
        for entry in raw.get("puts") or []
        if isinstance(entry, Mapping)
    ]
    return OptionsChain.model_validate(data)


def normalize_holders(raw: Mapping[str, Any], owner_type: str = "all") -> list[Holder]:
    """Map holders and apply the client-side ``owner_type`` filter."""
    holders: list[Holder] = []
    for entry in raw.get("holders") or []:
        if not isinstance(entry, Mapping):
            continue
        holder = Holder.model_validate(entry)
        if owner_type != "all" and holder.owner_type != owner_type:
            continue
        holders.append(holder)
    return holders


def normalize_analyst_research(raw: Mapping[str, Any], limit: int = 20) -> AnalystResearchResult:
    """Map analyst research; ``limit`` caps the client-side action list."""
    target = raw.get("priceTarget")
    actions = [
        AnalystAction.model_validate(entry)
        for entry in raw.get("ratings") or []
        if isinstance(entry, Mapping)
    ]
    return AnalystResearchResult(
        recommendation=finite_number(raw.get("recommendationRating")),
        price_target=(
            AnalystPriceTarget.model_validate(target) if isinstance(target, Mapping) else None
        ),
        actions=actions[:limit],
    )


def normalize_corporate_actions(raw: Mapping[str, Any]) -> list[CorporateAction]:
    """Flatten upstream dividends/splits/earnings arrays into ``kind`` records."""
    actions: list[CorporateAction] = []
    for entry in raw.get("dividends") or []:
        if not isinstance(entry, Mapping):
            continue
        actions.append(
            CorporateAction(
                kind="dividend",
                date=str(entry.get("exDate") or ""),
                amount=finite_number(entry.get("amount")),
            )
        )
    for entry in raw.get("splits") or []:
        if not isinstance(entry, Mapping):
            continue
        actions.append(
            CorporateAction(
                kind="split",
                date=str(entry.get("date") or ""),
                description=entry.get("description"),
                ratio=finite_number(entry.get("ratio")),
                from_factor=finite_number(entry.get("fromFactor")),
                to_factor=finite_number(entry.get("toFactor")),
            )
        )
    for entry in raw.get("earnings") or []:
        if not isinstance(entry, Mapping):
            continue
        actions.append(
            CorporateAction(
                kind="earnings",
                date=str(entry.get("date") or ""),
                date_type=entry.get("dateType"),
                currency=entry.get("currency"),
                time=entry.get("time"),
                eps_estimate=finite_number(entry.get("epsEstimate")),
                eps_actual=finite_number(entry.get("epsActual")),
                difference=finite_number(entry.get("difference")),
                surprise_percent=finite_number(entry.get("surprisePercent")),
            )
        )
    return actions


def normalize_news_item(raw: Mapping[str, Any]) -> NewsItem:
    """Map one news payload (list item or ``/news/{id}`` story)."""
    return NewsItem.model_validate(dict(raw))


def normalize_news_list(raw: Mapping[str, Any]) -> list[NewsItem]:
    """Map a ``/news`` list payload to items."""
    return [
        normalize_news_item(entry) for entry in raw.get("items") or [] if isinstance(entry, Mapping)
    ]


def normalize_search_results(raw: Any) -> list[InstrumentSearchResult]:
    """Map the search payload's list of listings."""
    if not isinstance(raw, list):
        return []
    return [
        InstrumentSearchResult.model_validate(entry) for entry in raw if isinstance(entry, Mapping)
    ]


def normalize_exchange_rate(
    raw: Mapping[str, Any],
    *,
    response_as_of: str | None = None,
    freshness: Freshness | None = None,
) -> ExchangeRateResult:
    """Map the exchange-rate snapshot, keeping asOf unknown when absent."""
    rate = finite_number(raw.get("rate"))
    if rate is None:
        raise ValueError("exchange-rate payload has no finite rate")
    fresh = freshness or derive_freshness(
        stale=raw.get("stale") is True,
        data_source=raw.get("dataSource") if isinstance(raw.get("dataSource"), str) else None,
        delay_minutes=finite_number(raw.get("delayMinutes")),
    )
    as_of = raw.get("asOf")
    return ExchangeRateResult(
        rate=rate,
        as_of=str(as_of if as_of is not None else response_as_of)
        if (as_of is not None or response_as_of is not None)
        else None,
        stale=fresh.stale or raw.get("stale") is True,
        delay_note=fresh.delay_note,
    )


def normalize_sec_filings(raw: Mapping[str, Any]) -> list[SecFiling]:
    """Map the ``/cloud/sec/filings`` payload."""
    return [
        SecFiling.model_validate(entry)
        for entry in raw.get("filings") or []
        if isinstance(entry, Mapping)
    ]


def normalize_sec_documents(raw: Mapping[str, Any]) -> list[SecFilingDocument]:
    """Map the ``/cloud/sec/filing/documents`` payload."""
    return [
        SecFilingDocument.model_validate(entry)
        for entry in raw.get("documents") or []
        if isinstance(entry, Mapping)
    ]
