"""Thin yfinance download helper with retries (Yahoo rate-limits without notice).

Baked into the digiquant sandbox image (#396). Prefer this over raw
``yfinance.download`` / ``Ticker.history`` in agent-written research code.
"""

from __future__ import annotations

import time
from typing import Any

import yfinance as yf


def download_with_retry(
    tickers: str | list[str],
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.5,
    **kwargs: Any,
) -> Any:
    """Call ``yfinance.download`` with exponential backoff on empty/failed pulls.

    Yahoo Finance rate-limits and intermittently returns empty frames. Retry a
    few times before raising so agent runs are less flaky.
    """
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            frame = yf.download(tickers, progress=False, **kwargs)
            if frame is not None and getattr(frame, "empty", False) is False:
                return frame
            last_err = RuntimeError(
                f"yfinance.download returned empty data for {tickers!r} "
                f"(attempt {attempt}/{max_attempts})"
            )
        except Exception as exc:  # noqa: BLE001 — surface after retries
            last_err = exc
        if attempt < max_attempts:
            time.sleep(base_delay_s * (2 ** (attempt - 1)))
    assert last_err is not None
    raise last_err


def history_with_retry(
    ticker: str,
    *,
    max_attempts: int = 4,
    base_delay_s: float = 1.5,
    **kwargs: Any,
) -> Any:
    """Call ``Ticker(ticker).history`` with the same backoff policy."""
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            frame = yf.Ticker(ticker).history(**kwargs)
            if frame is not None and getattr(frame, "empty", False) is False:
                return frame
            last_err = RuntimeError(
                f"Ticker({ticker!r}).history returned empty data "
                f"(attempt {attempt}/{max_attempts})"
            )
        except Exception as exc:  # noqa: BLE001 — surface after retries
            last_err = exc
        if attempt < max_attempts:
            time.sleep(base_delay_s * (2 ** (attempt - 1)))
    assert last_err is not None
    raise last_err
