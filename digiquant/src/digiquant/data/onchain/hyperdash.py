"""Hyperdash on-chain cohort-positioning provider — Polars-only, fail-soft (#801).

Scrapes Hyperliquid trader positioning segmented by *profitability cohort* from Hyperdash's
public GraphQL endpoint (no auth), and computes a **smart-money vs. rekt divergence** per market.

Why this is a signal: Hyperdash buckets every tracked trader into six profitability cohorts
(extremely-profitable 👑 … rekt 💀). When the consistently-profitable cohorts lean one way while
the consistently-unprofitable ones lean the other, that divergence is an early read on
distribution / investor-class divergence — validated on live data (the extremely-profitable
cohort net-short ETH while the rekt cohort piled long). It rides on Hyperliquid perps, which now
include **equity perps** (``xyz:SP500``, ``xyz:XYZ100``) alongside crypto, so the read spans both.

Boundaries (deliberate):
- The endpoint is undocumented/internal and may drift, so EVERY failure mode (network, HTTP
  error, GraphQL error, shape change) fails soft to an empty result — a Hyperdash outage must
  never block an Atlas run. The signal is an overlay that adjusts conviction/sizing; it never
  originates a trade.
- HTTP is split from computation: ``cohort_summary_to_positioning`` is a pure, HTTP-free parser +
  divergence calculator (unit-tested against a captured-shape fixture); ``HyperdashScraper.fetch``
  adds only the network + fail-soft. This mirrors ``data/prices/fed_probabilities.py``.
- Polars-only: the JSON boundary is converted to a Polars frame immediately; the divergence math
  is Polars expressions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Protocol  # noqa  # scored-lint: heterogeneous GraphQL/JSON payload shapes

import polars as pl

logger = logging.getLogger(__name__)

_HYPERDASH_GRAPHQL_URL = "https://api.hyperdash.com/graphql"
# Polite, identifiable UA for a low-volume (~1 call/day) read of a public endpoint.
_USER_AGENT = "digiquant-research/1.0 (+https://digiquant.io)"

# pnlCohort ``id``s grouped by profitability. "smart" = consistently profitable (the signal we
# trust); "crowd" = consistently unprofitable (the fade side). Mid cohorts are intentionally
# excluded — the divergence is sharpest at the tails. Matching is on the lower-cased id with an
# emoji/whitespace-tolerant fallback so a cosmetic label tweak upstream doesn't silently drop a
# cohort.
_SMART_COHORTS = ("extremely_profitable", "very_profitable", "profitable")
_CROWD_COHORTS = ("unprofitable", "very_unprofitable", "rekt")

# GraphQL query the cohorts page fires (no auth). topMarkets(limit:3) is the per-market breakdown
# used for the divergence; the cohort-level long/short give the aggregate net read.
_COHORT_SUMMARY_QUERY = """
query CohortSummary {
  analytics {
    cohortSummary {
      timestamp
      totalTraders
      pnlCohorts {
        id
        label
        emoji
        range
        totalTraders
        longNotional
        shortNotional
        topMarkets(limit: 3) {
          ticker
          longNotional
          shortNotional
        }
      }
    }
  }
}
""".strip()

_DIVERGENCE_COLUMNS = (
    "market",
    "smart_long",
    "smart_short",
    "crowd_long",
    "crowd_short",
    "smart_bias",
    "crowd_bias",
    "divergence",
)


def _f(value: Any) -> float:
    """Coerce a notional to float; non-numeric / missing → 0.0 (notionals are additive)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _classify_cohort(cohort_id: Any) -> str | None:
    """Map a pnlCohort id to ``"smart"`` / ``"crowd"`` / ``None`` (mid or unknown cohort)."""
    if not isinstance(cohort_id, str):
        return None
    key = cohort_id.strip().lower().replace(" ", "_").replace("-", "_")
    if key in _SMART_COHORTS:
        return "smart"
    if key in _CROWD_COHORTS:
        return "crowd"
    return None


def _bias_expr(long_col: str, short_col: str) -> pl.Expr:
    """long / (long+short) in [0,1]; null when the cohort has no notional on that market."""
    denom = pl.col(long_col) + pl.col(short_col)
    return pl.when(denom > 0).then(pl.col(long_col) / denom).otherwise(None)


def _empty_divergence_frame() -> pl.DataFrame:
    return pl.DataFrame(
        {
            c: pl.Series(c, [], dtype=pl.Utf8 if c == "market" else pl.Float64)
            for c in _DIVERGENCE_COLUMNS
        }
    )


def _round(value: Any, ndigits: int = 4) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), ndigits)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CohortPositioning:
    """Parsed Hyperdash cohort snapshot + the derived smart-vs-crowd divergence.

    ``market_divergence`` is one row per market (BTC/ETH/HYPE + equity perps) with the smart and
    crowd long/short notionals, each cohort group's directional bias, and ``divergence =
    smart_bias - crowd_bias`` (+1 = smart maximally long while crowd maximally short → smart-money
    confirm; -1 = smart short while crowd long → distribution/fade). ``overall`` carries the same
    read at the aggregate cohort level. ``error`` is set only on a transport/parse failure.
    """

    snapshot_ts: str | None
    total_traders: int | None
    market_divergence: pl.DataFrame
    overall: dict[str, float | None]
    error: str | None = None

    @classmethod
    def empty(cls, *, error: str | None = None) -> CohortPositioning:
        return cls(
            snapshot_ts=None,
            total_traders=None,
            market_divergence=_empty_divergence_frame(),
            overall={"smart_net_bias": None, "crowd_net_bias": None, "overall_divergence": None},
            error=error,
        )

    @property
    def has_data(self) -> bool:
        """True when at least one market produced a (smart, crowd) divergence pair."""
        if self.market_divergence.height == 0:
            return False
        return self.market_divergence.get_column("divergence").drop_nulls().len() > 0

    def top_divergent_markets(self, limit: int = 5) -> list[dict[str, Any]]:
        """Markets with the largest |divergence|, most extreme first."""
        if self.market_divergence.height == 0:
            return []
        ranked = (
            self.market_divergence.filter(pl.col("divergence").is_not_null())
            .with_columns(_absd=pl.col("divergence").abs())
            .sort("_absd", descending=True)
            .head(limit)
        )
        out: list[dict[str, Any]] = []
        for row in ranked.iter_rows(named=True):
            out.append(
                {
                    "market": row["market"],
                    "divergence": _round(row["divergence"]),
                    "smart_bias": _round(row["smart_bias"]),
                    "crowd_bias": _round(row["crowd_bias"]),
                }
            )
        return out

    def compact_summary(self) -> dict[str, Any]:
        """Small dict for ``market_context`` + the Phase 6 bias row (mirrors fed_odds compact)."""
        return {
            "snapshot_ts": self.snapshot_ts,
            "total_traders": self.total_traders,
            "smart_net_bias": _round(self.overall.get("smart_net_bias")),
            "crowd_net_bias": _round(self.overall.get("crowd_net_bias")),
            "overall_divergence": _round(self.overall.get("overall_divergence")),
            "top_divergent_markets": self.top_divergent_markets(),
            "source": "hyperdash",
        }

    def to_rows(self, date_str: str) -> list[dict[str, Any]]:
        """Per-market rows for the ``onchain_cohort_positioning`` table (history → backtest)."""
        rows: list[dict[str, Any]] = []
        for row in self.market_divergence.iter_rows(named=True):
            rows.append(
                {
                    "date": date_str,
                    "market": row["market"],
                    "smart_long_notional": _round(row["smart_long"], 2),
                    "smart_short_notional": _round(row["smart_short"], 2),
                    "crowd_long_notional": _round(row["crowd_long"], 2),
                    "crowd_short_notional": _round(row["crowd_short"], 2),
                    "smart_bias": _round(row["smart_bias"]),
                    "crowd_bias": _round(row["crowd_bias"]),
                    "divergence": _round(row["divergence"]),
                    "total_traders": self.total_traders,
                    "snapshot_ts": self.snapshot_ts,
                }
            )
        return rows


def cohort_summary_to_positioning(summary: dict[str, Any]) -> CohortPositioning:
    """Pure parser + divergence calculator over a ``cohortSummary`` payload (HTTP-free, tested).

    Accepts the ``data.analytics.cohortSummary`` object. An empty / unrecognized payload returns
    an empty (but error-free) result — "fetched, nothing to read" is distinct from a transport
    failure, which the caller flags via ``error``.
    """
    if not isinstance(summary, dict):
        return CohortPositioning.empty()
    cohorts = summary.get("pnlCohorts") or []
    if not isinstance(cohorts, list):
        return CohortPositioning.empty()

    # Per-market accumulator and aggregate cohort-level totals, both grouped smart/crowd.
    per_market: dict[str, dict[str, float]] = {}
    agg = {"smart_long": 0.0, "smart_short": 0.0, "crowd_long": 0.0, "crowd_short": 0.0}
    for cohort in cohorts:
        if not isinstance(cohort, dict):
            continue
        group = _classify_cohort(cohort.get("id"))
        if group is None:
            continue
        agg[f"{group}_long"] += _f(cohort.get("longNotional"))
        agg[f"{group}_short"] += _f(cohort.get("shortNotional"))
        for market in cohort.get("topMarkets") or []:
            if not isinstance(market, dict):
                continue
            ticker = market.get("ticker")
            if not isinstance(ticker, str) or not ticker:
                continue
            rec = per_market.setdefault(
                ticker,
                {"smart_long": 0.0, "smart_short": 0.0, "crowd_long": 0.0, "crowd_short": 0.0},
            )
            rec[f"{group}_long"] += _f(market.get("longNotional"))
            rec[f"{group}_short"] += _f(market.get("shortNotional"))

    if per_market:
        frame = (
            pl.DataFrame(
                [{"market": m, **rec} for m, rec in sorted(per_market.items())],
                schema={
                    "market": pl.Utf8,
                    "smart_long": pl.Float64,
                    "smart_short": pl.Float64,
                    "crowd_long": pl.Float64,
                    "crowd_short": pl.Float64,
                },
            )
            .with_columns(
                smart_bias=_bias_expr("smart_long", "smart_short"),
                crowd_bias=_bias_expr("crowd_long", "crowd_short"),
            )
            .with_columns(divergence=pl.col("smart_bias") - pl.col("crowd_bias"))
            .select(_DIVERGENCE_COLUMNS)
        )
    else:
        frame = _empty_divergence_frame()

    overall = {
        "smart_net_bias": _net_bias(agg["smart_long"], agg["smart_short"]),
        "crowd_net_bias": _net_bias(agg["crowd_long"], agg["crowd_short"]),
    }
    overall["overall_divergence"] = (
        overall["smart_net_bias"] - overall["crowd_net_bias"]
        if overall["smart_net_bias"] is not None and overall["crowd_net_bias"] is not None
        else None
    )

    ts = summary.get("timestamp")
    traders = summary.get("totalTraders")
    return CohortPositioning(
        snapshot_ts=str(ts) if ts is not None else None,
        total_traders=int(traders) if isinstance(traders, (int, float)) else None,
        market_divergence=frame,
        overall=overall,
    )


def _net_bias(long_notional: float, short_notional: float) -> float | None:
    denom = long_notional + short_notional
    return long_notional / denom if denom > 0 else None


def _post_graphql(
    endpoint: str, query: str, *, timeout: float, session: Any | None
) -> dict[str, Any]:
    """POST a GraphQL query and return the decoded body. Raises on transport/HTTP error."""
    import requests  # lazy — requests is the data-layer HTTP dep (see macro_ingest)

    caller = session if session is not None else requests
    resp = caller.post(
        endpoint,
        json={"query": query, "operationName": "CohortSummary"},
        headers={"User-Agent": _USER_AGENT, "Content-Type": "application/json"},
        timeout=timeout,
    )
    resp.raise_for_status()
    body = resp.json()
    return body if isinstance(body, dict) else {}


class CohortPositioningProvider(Protocol):
    """Swap-able source of cohort positioning (Hyperdash today; HyperTracker etc. tomorrow)."""

    def fetch(self) -> CohortPositioning: ...


@dataclass(frozen=True)
class HyperdashScraper:
    """Scrape Hyperdash's public cohort-summary GraphQL endpoint. Fail-soft."""

    endpoint: str = _HYPERDASH_GRAPHQL_URL
    timeout: float = 30.0
    session: Any | None = None  # inject a requests-like session in tests

    def fetch(self) -> CohortPositioning:
        try:
            body = _post_graphql(
                self.endpoint, _COHORT_SUMMARY_QUERY, timeout=self.timeout, session=self.session
            )
        except Exception as exc:  # noqa: BLE001 — any transport/HTTP flake → empty, never crash
            logger.warning("Hyperdash cohort fetch failed: %s", exc)
            return CohortPositioning.empty(error=str(exc))
        if body.get("errors"):
            logger.warning("Hyperdash GraphQL returned errors: %s", body.get("errors"))
            return CohortPositioning.empty(error="graphql_errors")
        summary = (((body.get("data") or {}).get("analytics") or {}).get("cohortSummary")) or {}
        return cohort_summary_to_positioning(summary)


def _onchain_enabled() -> bool:
    """Opt-in kill-switch for the LIVE Hyperdash scrape (env ATLAS_ONCHAIN_POSITIONING).

    Defaults OFF so unit tests never hit the network just by invoking preflight (the scrape is an
    external HTTP call, unlike the DB-backed fed_odds path). The Atlas workflows set it to "1" to
    enable the signal in CI/prod; the owner can flip it off instantly if the third-party endpoint
    becomes unavailable or its ToS changes — no code change. An injected ``provider`` bypasses the
    switch entirely (tests + alternative providers)."""
    import os

    return os.environ.get("ATLAS_ONCHAIN_POSITIONING", "0").strip().lower() in ("1", "true", "yes")


def get_onchain_cohort_positioning(
    *, provider: CohortPositioningProvider | None = None
) -> CohortPositioning:
    """Fetch + compute the on-chain cohort divergence. Always returns a value (empty on failure).

    With no ``provider`` the default Hyperdash scrape runs only when ``ATLAS_ONCHAIN_POSITIONING``
    is enabled (see :func:`_onchain_enabled`); otherwise it short-circuits to an empty result with
    no network call. An injected ``provider`` always runs (tests / alternative sources). Callers
    gate on ``result.error is None and result.has_data``.
    """
    if provider is not None:
        return provider.fetch()
    if not _onchain_enabled():
        return CohortPositioning.empty()
    return HyperdashScraper().fetch()


__all__ = [
    "CohortPositioning",
    "CohortPositioningProvider",
    "HyperdashScraper",
    "cohort_summary_to_positioning",
    "get_onchain_cohort_positioning",
]
