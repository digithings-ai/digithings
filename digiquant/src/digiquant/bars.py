"""Keyless OHLCV bars for dashboard charts (issue #4880; unblocks #4879 Vela wiring).

Read-only display path over the **anonymous** Gloomberb ``price_history``
tool — no session cookie, no API keys, no order paths. Free-tier data may be
delayed up to 15 minutes (surfaced on ``BarsResponse.delay_note``) and must
never feed the validate → backtest → optimize → export pipeline: this module
imports no backtest/optimize/broker code and returns no Sharpe, PnL, or
drawdown.

Stdlib + Pydantic only (no pandas — nothing here crosses the Nautilus
``BarDataWrangler`` boundary).
"""

from __future__ import annotations

from typing import Any, Literal

from digiquant.data.gloomberb.agent_tools import (
    build_gloomberb_client as _build_gloomberb_client,
)
from digiquant.data.gloomberb.models import DigifetchError
from digiquant.models import BarsBar, BarsResponse

Timeframe = Literal["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"]
"""Dashboard ``timeframe`` vocabulary — exactly the Gloomberb resolutions."""

TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo")

DEFAULT_LIMIT = 120
MAX_LIMIT = 500

DEFAULT_RANGE_BY_TIMEFRAME: dict[str, str] = {
    "1m": "1W",
    "5m": "1W",
    "15m": "1M",
    "30m": "6M",
    "1h": "3M",
    "1d": "1Y",
    "1wk": "5Y",
    "1mo": "ALL",
}
"""Contract-safe upstream range per timeframe (each within its §5.2 cap).

The caller asks for at most ``limit`` bars; this range only bounds the
upstream read, which is tail-sliced to ``limit``. Intraday timeframes need an
explicit range (the client never clamps and rejects a missing one outside
``1d``), so every timeframe carries one here.
"""


class BarsError(Exception):
    """Typed ``GET /bars`` failure carrying its HTTP status code."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


_ERROR_STATUS: dict[str, int] = {
    "invalid_input": 422,
    "not_found": 404,
    "rate_limited": 429,
}


def _error_status(code: str) -> int:
    """Map a §5.3 error code to HTTP. Anything non-client is a 502."""
    return _ERROR_STATUS.get(code, 502)


def fetch_bars(
    symbol: str,
    timeframe: str = "1d",
    limit: int = DEFAULT_LIMIT,
    *,
    client: Any | None = None,
) -> BarsResponse:
    """Fetch up to ``limit`` newest-last OHLCV bars for ``symbol``/``timeframe``.

    Raises :class:`BarsError` (never the raw envelope) on validation or
    upstream failures. ``client`` is an injected ``GloomberbClient`` (tests
    pass a ``MockTransport``-backed one); omitted, the shared env-keyed
    client is built — the anonymous price-history path attaches no cookie.
    """
    cleaned = (symbol or "").strip().upper()
    if not cleaned:
        raise BarsError(422, "invalid_input", "symbol is required")
    if timeframe not in TIMEFRAMES:
        raise BarsError(
            422,
            "invalid_input",
            f"timeframe must be one of {', '.join(TIMEFRAMES)} (got {timeframe!r})",
        )
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_LIMIT:
        raise BarsError(422, "invalid_input", f"limit must be 1..{MAX_LIMIT} (got {limit!r})")

    active = client if client is not None else _build_gloomberb_client()
    try:
        envelope = active.price_history(
            {
                "symbol": cleaned,
                "resolution": timeframe,
                "range": DEFAULT_RANGE_BY_TIMEFRAME[timeframe],
            }
        )
    except Exception as exc:
        raise BarsError(502, "upstream_error", f"bars transport failed: {exc}") from exc

    data = envelope.data
    if isinstance(data, DigifetchError):
        raise BarsError(_error_status(data.code), data.code, data.message)

    tail = list(data.bars)[-limit:]
    return BarsResponse(
        symbol=data.metadata.symbol,
        timeframe=timeframe,
        limit=limit,
        count=len(tail),
        bars=[
            BarsBar(
                timestamp=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in tail
        ],
        source="gloomberb",
        stale=envelope.stale,
        delay_note=envelope.delay_note,
    )
