"""Yahoo instrument metadata adapter for the canonical Olympus security master."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any  # noqa  # scored-lint suppression: provider jsonb payloads are heterogeneous

from digiquant.olympus.hermes.sector_map import asset_class, sector_bucket
from digiquant.olympus.instrument_metadata import InstrumentMetadata

InfoLoader = Callable[[str], Mapping[str, Any]]


@dataclass(frozen=True)
class InstrumentMetadataFetchResult:
    """Resolved provider records and per-symbol failures."""

    records: dict[str, InstrumentMetadata]
    errors: dict[str, str]


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _default_info_loader(ticker: str) -> Mapping[str, Any]:
    import yfinance as yf  # type: ignore[import-not-found]

    return yf.Ticker(ticker).get_info()


def metadata_from_yahoo_info(
    ticker: str,
    info: Mapping[str, Any],
    *,
    fetched_at: datetime | None = None,
) -> InstrumentMetadata:
    """Map one Yahoo quote-info payload into the strict canonical contract."""
    normalized = str(ticker).strip().upper()
    official_name = _text(info.get("longName")) or _text(info.get("shortName"))
    if official_name is None:
        raise ValueError("provider returned no longName or shortName")
    provider_metadata = {
        key: value
        for key, value in {
            "short_name": _text(info.get("shortName")),
            "market": _text(info.get("market")),
            "quote_source_name": _text(info.get("quoteSourceName")),
            "timezone": _text(info.get("exchangeTimezoneName")),
        }.items()
        if value is not None
    }
    return InstrumentMetadata(
        ticker=normalized,
        official_name=official_name,
        instrument_type=_text(info.get("quoteType")),
        asset_class=asset_class(normalized),
        category=sector_bucket(normalized),
        sector=_text(info.get("sector")),
        industry=_text(info.get("industry")),
        exchange=_text(info.get("fullExchangeName")) or _text(info.get("exchange")),
        currency=_text(info.get("currency")),
        country=_text(info.get("country")),
        provider="yahoo",
        provider_metadata=provider_metadata,
        source_updated_at=fetched_at or datetime.now(timezone.utc),
    )


def fetch_instrument_metadata(
    tickers: list[str],
    *,
    info_loader: InfoLoader | None = None,
    throttle_s: float = 0.2,
) -> InstrumentMetadataFetchResult:
    """Resolve distinct tickers individually; failed symbols are not destructive writes."""
    loader = info_loader or _default_info_loader
    normalized = list(dict.fromkeys(str(ticker).strip().upper() for ticker in tickers if ticker))
    records: dict[str, InstrumentMetadata] = {}
    errors: dict[str, str] = {}
    for index, ticker in enumerate(normalized):
        if ticker == "CASH":
            records[ticker] = InstrumentMetadata(
                ticker="CASH",
                official_name="Cash",
                instrument_type="CASH",
                asset_class="CASH",
                category="cash",
                provider="olympus",
                provider_metadata={"resolution": "canonical"},
                source_updated_at=datetime.now(timezone.utc),
            )
            continue
        try:
            records[ticker] = metadata_from_yahoo_info(ticker, loader(ticker))
        except Exception as exc:  # noqa: BLE001 — provider failures are isolated per symbol
            errors[ticker] = str(exc)
        if throttle_s > 0 and index + 1 < len(normalized):
            time.sleep(throttle_s)
    return InstrumentMetadataFetchResult(records=records, errors=errors)


__all__ = [
    "InfoLoader",
    "InstrumentMetadataFetchResult",
    "fetch_instrument_metadata",
    "metadata_from_yahoo_info",
]
