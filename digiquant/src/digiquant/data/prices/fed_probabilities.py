"""Fed rate-decision probabilities from FREE prediction markets (Atlas research, #778).

Markets pivot around FOMC decisions, so the analysts + PM need forward-looking hike/cut/hold
odds. CME FedWatch has no free API (licensed/paid), so we DON'T call it — we read the same
market-implied signal from prediction markets that publish free, no-auth JSON:

- **Kalshi** (``KXFED`` series, CFTC-regulated) — a per-meeting ladder of "upper bound of the
  fed funds rate > X%" threshold contracts. Differencing adjacent strikes gives a per-meeting
  probability distribution over 25bp target-rate levels. This is the structured source of truth.
- **Polymarket** (Gamma API, no key) — best-effort cross-check; its Fed events are coarser and
  their structure varies, so we parse defensively and fail soft.

Each fetcher returns ``macro_series_observations`` rows (the existing macro-ingest contract) so
the data flows through the same upsert + look-ahead-safe read path as every other macro series:

    series_id = "FEDPROB/{meeting_date}/upper_gt_{strike}"   # Kalshi survival ladder, value=P(>strike)
    series_id = "FEDPROB/{meeting_date}/pm/{outcome}"         # Polymarket outcome, value=probability

``obs_date`` is the run date (a point-in-time odds snapshot). The pure ``*_to_rows`` helpers are
HTTP-free for unit testing; the ``fetch_*`` wrappers add the network + fail-soft to ``[]``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, timezone
from typing import Any  # noqa  # scored-lint: heterogeneous prediction-market JSON

from digiquant.data.prices.macro_ingest import MacroObservation, retrying_session

logger = logging.getLogger(__name__)

_KALSHI_MARKETS_URL = "https://api.elections.kalshi.com/trade-api/v2/markets"
_KALSHI_SERIES = "KXFED"
_POLYMARKET_EVENTS_URL = "https://gamma-api.polymarket.com/events"
_POLYMARKET_TAG = "fed-rates"
_USER_AGENT = "digiquant-research/1.0 (+https://digiquant.io)"
_UNIT = "probability"


def _opt_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if 0.0 <= out <= 1.0 else None  # prediction-market prices are in [0, 1]


def _meeting_date_from_iso(value: Any) -> str | None:
    """Date part of an ISO timestamp (Kalshi ``close_time`` ~= the meeting day)."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return value[:10] if value[:10].count("-") == 2 else None


# ── Kalshi (structured per-meeting ladder) ──────────────────────────────────


def kalshi_markets_to_rows(markets: list[dict[str, Any]], *, as_of: date) -> list[MacroObservation]:
    """Turn Kalshi ``KXFED`` threshold markets into survival-ladder observation rows.

    Each market is a "upper bound > ``floor_strike``%" contract; the mid of yes_bid/yes_ask
    (falling back to last) is ``P(upper bound > strike)``. We store the raw survival ladder per
    meeting; the derived tool differences it into a distribution at read time.
    """
    rows: list[MacroObservation] = []
    for m in markets:
        if not isinstance(m, dict):
            continue
        strike = m.get("floor_strike")
        meeting = _meeting_date_from_iso(m.get("close_time"))
        if strike is None or meeting is None:
            continue
        bid = _opt_float(m.get("yes_bid_dollars"))
        ask = _opt_float(m.get("yes_ask_dollars"))
        if bid is not None and ask is not None:
            prob = round((bid + ask) / 2.0, 4)
        else:
            prob = _opt_float(m.get("last_price_dollars"))
        if prob is None:
            continue
        try:
            strike_f = float(strike)
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "source": "kalshi",
                "series_id": f"FEDPROB/{meeting}/upper_gt_{strike_f:g}",
                "obs_date": as_of.isoformat(),
                "value": prob,
                "unit": _UNIT,
                "meta": {
                    "classification": "fed_rate_probability",
                    "event_ticker": str(m.get("event_ticker") or ""),
                    "strike": strike_f,
                    "strike_type": str(m.get("strike_type") or "greater"),
                    "yes_bid": bid,
                    "yes_ask": ask,
                },
            }
        )
    return rows


def fetch_fed_prob_kalshi(
    *, as_of: date | None = None, session: Any | None = None
) -> list[MacroObservation]:
    """Fetch open ``KXFED`` markets (paginated, no auth) → survival-ladder rows. Fail-soft to []."""
    as_of = as_of or datetime.now(timezone.utc).date()
    s = session if session is not None else retrying_session()
    markets: list[dict[str, Any]] = []
    cursor = ""
    try:
        for _ in range(12):  # hard page cap (12 * 200 = 2400 markets) — never loop forever
            params: dict[str, Any] = {
                "series_ticker": _KALSHI_SERIES,
                "status": "open",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor
            r = s.get(
                _KALSHI_MARKETS_URL, params=params, headers={"User-Agent": _USER_AGENT}, timeout=30
            )
            r.raise_for_status()
            body = r.json()
            batch = body.get("markets") or []
            markets.extend(b for b in batch if isinstance(b, dict))
            cursor = body.get("cursor") or ""
            if not cursor or not batch:
                break
    except Exception as exc:  # noqa: BLE001 — a data-source flake must never break the macro job
        logger.warning("Kalshi KXFED fetch failed: %s", exc)
        return []
    return kalshi_markets_to_rows(markets, as_of=as_of)


# ── Polymarket (best-effort cross-check) ────────────────────────────────────


def _pm_series_id(anchor: str, slug: str) -> str:
    """Collision-safe Polymarket series_id. ``series_id`` is part of the (source, series_id,
    obs_date) PK, so we never blind-truncate (two long slugs could collide and overwrite); when
    over the cap we keep a readable prefix + a short hash of the FULL slug for uniqueness."""
    full = f"FEDPROB/{anchor}/pm/{slug}"
    if len(full) <= 200:
        return full
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:12]
    return f"FEDPROB/{anchor}/pm/{slug[:160]}-{digest}"


def _json_list(value: Any) -> list[Any]:
    """Polymarket ``outcomes``/``outcomePrices`` arrive as JSON-encoded strings."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def polymarket_events_to_rows(
    events: list[dict[str, Any]], *, as_of: date
) -> list[MacroObservation]:
    """Best-effort: map Polymarket Fed events' Yes prices to outcome-probability rows.

    Polymarket Fed markets are coarser and their slugs/structure vary per event, so this is a
    cross-check, not the source of truth. We key rows by the event end-date (a meeting/period
    anchor) and the market slug, storing the ``Yes`` probability.
    """
    rows: list[MacroObservation] = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        anchor = _meeting_date_from_iso(ev.get("endDate")) or as_of.isoformat()
        for m in ev.get("markets") or []:
            if not isinstance(m, dict) or m.get("closed"):
                continue
            outcomes = [str(o).lower() for o in _json_list(m.get("outcomes"))]
            prices = _json_list(m.get("outcomePrices"))
            yes_prob: float | None = None
            if "yes" in outcomes and len(prices) == len(outcomes):
                yes_prob = _opt_float(prices[outcomes.index("yes")])
            if yes_prob is None:
                yes_prob = _opt_float(m.get("lastTradePrice"))
            slug = str(m.get("slug") or m.get("question") or "").strip()
            if yes_prob is None or not slug:
                continue
            rows.append(
                {
                    "source": "polymarket",
                    "series_id": _pm_series_id(anchor, slug),
                    "obs_date": as_of.isoformat(),
                    "value": round(yes_prob, 4),
                    "unit": _UNIT,
                    "meta": {
                        "classification": "fed_rate_probability",
                        "question": str(m.get("question") or ""),
                        "group_item_threshold": str(m.get("groupItemThreshold") or ""),
                    },
                }
            )
    return rows


def fetch_fed_prob_polymarket(
    *, as_of: date | None = None, session: Any | None = None
) -> list[MacroObservation]:
    """Fetch open Polymarket ``fed-rates`` events → outcome rows. Best-effort, fail-soft to []."""
    as_of = as_of or datetime.now(timezone.utc).date()
    s = session if session is not None else retrying_session()
    try:
        r = s.get(
            _POLYMARKET_EVENTS_URL,
            params={"closed": "false", "tag_slug": _POLYMARKET_TAG, "limit": 30},
            headers={"User-Agent": _USER_AGENT},
            timeout=30,
        )
        r.raise_for_status()
        events = r.json()
        if not isinstance(events, list):
            return []
    except Exception as exc:  # noqa: BLE001 — cross-check source; degrade silently
        logger.warning("Polymarket fed-rates fetch failed: %s", exc)
        return []
    return polymarket_events_to_rows(events, as_of=as_of)


# ── Derivation: survival ladder → per-meeting 25bp distribution (read side) ──


def fed_distribution_from_ladder(ladder: dict[float, float]) -> dict[str, Any]:
    """Convert a Kalshi survival ladder ``{strike: P(upper bound > strike)}`` into a normalized
    probability distribution over 25bp fed-funds upper-bound outcomes.

    On a 25bp grid, ``P(upper == s) = surv(prev) - surv(s)`` for interior strikes, with tail
    buckets ``"<=min"`` and ``">max"``. Negatives (from noisy bid/ask) are clamped to 0 and the
    result is normalized to sum 1. Returns ``{}`` for fewer than 2 strikes.
    """
    strikes = sorted(ladder)
    if len(strikes) < 2:
        return {}
    dist: dict[str, float] = {}
    lo = strikes[0]
    dist[f"<={lo:g}"] = max(0.0, 1.0 - ladder[lo])
    for prev, cur in zip(strikes, strikes[1:], strict=False):
        dist[f"{cur:g}"] = max(0.0, ladder[prev] - ladder[cur])
    hi = strikes[-1]
    dist[f">{hi:g}"] = max(0.0, ladder[hi])
    total = sum(dist.values())
    if total <= 0:
        return {}
    dist = {k: round(v / total, 4) for k, v in dist.items()}
    most_likely = max(dist, key=lambda k: dist[k])
    return {"distribution": dist, "most_likely": most_likely, "n_strikes": len(strikes)}


__all__ = [
    "fed_distribution_from_ladder",
    "fetch_fed_prob_kalshi",
    "fetch_fed_prob_polymarket",
    "kalshi_markets_to_rows",
    "polymarket_events_to_rows",
]
