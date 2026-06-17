"""Deterministic position sizer (Pillar 2).

The PM (Phase 7D) proposes a conviction-weighted candidate book; this module turns
per-ticker *conviction + direction* into the FINAL target weights — the deterministic
half of the direction/sizing split (FinPos pattern). Sizing, position/sector caps,
correlation de-dup, vol-targeting, and the drawdown-breaker scale are CODE, not LLM
judgement, so the book's risk profile is reproducible and auditable.

Pure-functional and dependency-light: inputs are plain mappings + an optional correlation
frame; output is a :class:`SizingResult`. No I/O — the caller (the phase7e enforcement
node) does the Supabase reads and passes vol / correlation / caps in. The covariance math
is plain Python (no numpy/pandas) since the holdings count is small.

Pipeline (each step records why a weight changed, into ``SizedPosition.notes`` /
``SizingResult.applied_scales``):

Every reduction step is **reduce-only / cash-first**: weight freed by a cap or a dropped
leg becomes CASH, never redistributed up to the survivors (a plain renormalize would
re-breach the cap it just enforced). The pipeline:

    select(conv ≥ min, stance buy/hold)
      → raw weights (conviction-∝ × inverse-vol, OR fractional-Kelly)
      → position caps (min floor / max cap; freed weight → cash)
      → sector caps (scale down any over-cap bucket; freed weight → cash)
      → correlation de-dup (drop the lower-conviction leg of a > threshold pair → cash)
      → vol-target scale (ex-ante √(wᵀΣw) → cash residual)
      → drawdown-breaker scale (only ever reduces gross)
      → round DOWN to the weight grid (remainder → cash) → cash = 100 − Σ
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class SizingCaps:
    """Risk-budget + cap configuration for one sizing pass."""

    min_position_pct: float = 5.0
    max_position_pct: float = 30.0
    max_sector_pct: float = 40.0
    weight_increment_pct: float = 5.0  # round-to grid; 0 disables rounding
    target_portfolio_vol: float = 12.0  # annualized % vol budget
    max_gross_pct: float = 100.0  # ≤ 100 (paper, long-only)
    corr_dedup_threshold: float = 0.80  # |corr| above which the lower-conviction leg is dropped
    kelly_fraction: float = 0.25  # fractional-Kelly shrink (sizing_mode="kelly")
    kelly_annual_premium: float = 0.08  # assumed edge at full (±5) conviction
    sizing_mode: str = "conviction_vol"  # "conviction_vol" | "kelly"
    min_conviction: float = 2.0  # effective-conviction bar to enter the book
    default_annual_vol: float = 20.0  # fallback per-ticker vol (annualized %) when unknown

    @classmethod
    def from_preferences(cls, prefs: Mapping[str, Any]) -> SizingCaps:
        """Build caps from the investor ``preferences`` / ``constraints`` dict.

        Reads the keys ``config/portfolio.json`` already defines
        (``max_single_etf_pct``, ``weight_increment_pct``) plus optional sizing keys
        (``max_sector_pct``, ``target_portfolio_vol``, ``sizing_mode``,
        ``min_position_pct``, ``min_conviction``); anything absent keeps the default.
        """

        def _num(key: str, default: float) -> float:
            try:
                val = prefs.get(key)
                return float(val) if val is not None else default
            except (TypeError, ValueError):
                return default

        # Only honour a recognised mode; anything else (None, typo, non-string) → default,
        # never the literal "None" that str(prefs.get(...)) would silently produce.
        mode = prefs.get("sizing_mode")
        sizing_mode = str(mode) if mode in ("conviction_vol", "kelly") else cls.sizing_mode

        return cls(
            min_position_pct=_num("min_position_pct", cls.min_position_pct),
            max_position_pct=_num("max_single_etf_pct", cls.max_position_pct),
            max_sector_pct=_num("max_sector_pct", cls.max_sector_pct),
            weight_increment_pct=_num("weight_increment_pct", cls.weight_increment_pct),
            target_portfolio_vol=_num("target_portfolio_vol", cls.target_portfolio_vol),
            corr_dedup_threshold=_num("corr_dedup_threshold", cls.corr_dedup_threshold),
            kelly_fraction=_num("kelly_fraction", cls.kelly_fraction),
            sizing_mode=sizing_mode,
            min_conviction=_num("min_conviction", cls.min_conviction),
        )


@dataclass(frozen=True)
class TickerRisk:
    """Per-ticker risk inputs (assembled by the caller from price_technicals/history)."""

    ticker: str
    hist_vol_21: float | None = None  # annualized %, from price_technicals.hist_vol_21
    atr_pct: float | None = None  # daily ATR % (fallback vol proxy)
    sector: str = "UNKNOWN"  # asset-class bucket (concentration control)


@dataclass(frozen=True)
class SizedPosition:
    ticker: str
    target_pct: float
    sector: str
    raw_conviction: float
    pre_cap_pct: float  # weight (%) before caps/scaling — audit trail
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SizingResult:
    positions: list[SizedPosition]
    cash_pct: float
    gross_pct: float
    realized_portfolio_vol: float | None  # ex-ante annualized vol % of the final book
    applied_scales: dict[str, float]
    explanation: str


_ANNUALIZE = 16.0  # ≈ sqrt(252) — daily → annual vol scaling for the ATR fallback


def _vol_fraction(risk: TickerRisk | None, caps: SizingCaps) -> float:
    """Annualized vol as a fraction (e.g. 0.20). Falls back atr_pct → default."""
    if risk is not None and risk.hist_vol_21 is not None and risk.hist_vol_21 > 0:
        return float(risk.hist_vol_21) / 100.0
    if risk is not None and risk.atr_pct is not None and risk.atr_pct > 0:
        return float(risk.atr_pct) / 100.0 * _ANNUALIZE
    return caps.default_annual_vol / 100.0


def _select(
    convictions: Mapping[str, float], stances: Mapping[str, str], min_conviction: float
) -> dict[str, float]:
    """Tickers with effective conviction ≥ bar AND a long-side stance (buy/hold)."""
    return {
        ticker: float(conv)
        for ticker, conv in convictions.items()
        if float(conv) >= min_conviction
        and str(stances.get(ticker, "hold")).lower() in ("buy", "hold")
    }


def _raw_weights(
    selected: Mapping[str, float], risk: Mapping[str, TickerRisk], caps: SizingCaps
) -> dict[str, float]:
    """Raw fractional weights (sum 1.0) before caps. Two modes:

    - ``conviction_vol``: w ∝ conviction / vol (conviction-weighted, inverse-vol tilt).
    - ``kelly``: w ∝ fractional-Kelly f = kelly_fraction · edge / vol² where edge scales
      with conviction.
    """
    scores: dict[str, float] = {}
    for ticker, conv in selected.items():
        vol = _vol_fraction(risk.get(ticker), caps)
        if caps.sizing_mode == "kelly":
            edge = (conv / 5.0) * caps.kelly_annual_premium
            scores[ticker] = max(0.0, caps.kelly_fraction * edge / (vol * vol)) if vol > 0 else 0.0
        else:
            scores[ticker] = (conv / vol) if vol > 0 else 0.0
    total = sum(scores.values())
    if total <= 0:
        # Degenerate (all-zero) → equal weight the selected set.
        n = len(selected)
        return {t: 1.0 / n for t in selected} if n else {}
    return {t: s / total for t, s in scores.items()}


def _apply_position_caps(
    weights: dict[str, float], caps: SizingCaps, notes: dict[str, list[str]]
) -> dict[str, float]:
    """Clamp each weight to [min, max] (as fractions), drop sub-min, renormalize."""
    lo, hi = caps.min_position_pct / 100.0, caps.max_position_pct / 100.0
    out: dict[str, float] = {}
    for ticker, w in weights.items():
        if w < lo:
            notes.setdefault(ticker, []).append(f"dropped (<{caps.min_position_pct:g}% min)")
            continue
        if w > hi:
            notes.setdefault(ticker, []).append(f"capped @{caps.max_position_pct:g}%")
            w = hi
        out[ticker] = w
    # Reduce-only: weight freed by capping/dropping becomes cash — never scale UP past
    # the caps (which a plain renormalize would do). Renormalize down only if over-allocated.
    total = sum(out.values())
    return {t: w / total for t, w in out.items()} if total > 1.0 else out


def _apply_sector_caps(
    weights: dict[str, float],
    risk: Mapping[str, TickerRisk],
    caps: SizingCaps,
    notes: dict[str, list[str]],
) -> dict[str, float]:
    """Scale down any sector bucket whose summed weight exceeds the cap, then renormalize."""
    cap = caps.max_sector_pct / 100.0
    by_sector: dict[str, float] = {}
    for ticker, w in weights.items():
        sector = risk.get(ticker).sector if risk.get(ticker) else "UNKNOWN"
        by_sector[sector] = by_sector.get(sector, 0.0) + w
    out = dict(weights)
    for sector, total in by_sector.items():
        if total > cap and total > 0:
            scale = cap / total
            for ticker in weights:
                t_sector = risk.get(ticker).sector if risk.get(ticker) else "UNKNOWN"
                if t_sector == sector:
                    out[ticker] *= scale
                    notes.setdefault(ticker, []).append(f"{sector} sector-capped")
    # Reduce-only (cash-first): sector scaling only ever lowers a weight, so the freed
    # weight becomes cash — never renormalize the under-cap buckets back up past the caps.
    grand = sum(out.values())
    return {t: w / grand for t, w in out.items()} if grand > 1.0 else out


def _corr_dedup(
    weights: dict[str, float],
    convictions: Mapping[str, float],
    corr: Any | None,
    caps: SizingCaps,
    notes: dict[str, list[str]],
) -> dict[str, float]:
    """Drop the lower-conviction leg of any pair with |corr| > threshold, then renormalize.

    ``corr`` is a long Polars frame with columns ``a``, ``b``, ``corr`` (or ``None``).
    """
    if corr is None or len(weights) < 2:
        return weights
    try:
        rows = corr.select(["a", "b", "corr"]).to_dicts()
    except Exception:  # noqa: BLE001 — bad/empty corr frame → skip de-dup (conservative)
        return weights
    held = set(weights)
    dropped: set[str] = set()
    for row in rows:
        a, b, c = row.get("a"), row.get("b"), row.get("corr")
        if a not in held or b not in held or a in dropped or b in dropped or c is None:
            continue
        if abs(float(c)) > caps.corr_dedup_threshold:
            ca, cb = float(convictions.get(a, 0)), float(convictions.get(b, 0))
            # Drop the lower-conviction leg; on a tie break deterministically by ticker
            # (lexicographically larger) so the result never depends on (a,b) vs (b,a) order.
            if ca != cb:
                loser = a if ca < cb else b
            else:
                loser = max(a, b)
            keeper = b if loser == a else a
            dropped.add(loser)
            notes.setdefault(loser, []).append(
                f"corr-dedup (>{caps.corr_dedup_threshold:g} with {keeper})"
            )
    # Reduce-only (cash-first): a dropped leg's weight becomes cash, not redistributed to
    # the surviving leg. Renormalize down only in the defensive over-allocation case.
    kept = {t: w for t, w in weights.items() if t not in dropped}
    total = sum(kept.values())
    return {t: w / total for t, w in kept.items()} if total > 1.0 else kept


def _portfolio_vol(
    weights: Mapping[str, float], risk: Mapping[str, TickerRisk], corr: Any | None, caps: SizingCaps
) -> float:
    """Ex-ante annualized portfolio vol (%) for fractional ``weights``: √(wᵀΣw) with
    Σᵢⱼ = σᵢ σⱼ ρᵢⱼ.

    Any correlation not supplied — ``corr`` is ``None``, the pair is absent, or the frame
    fails to parse — defaults to ρ = 1.0 (full correlation). For a long-only book that is
    the *conservative* assumption: it overstates vol, so vol-targeting raises cash rather
    than under-scaling a book whose true correlations are unknown. Pure Python (no numpy):
    the holdings count is small, so the O(n²) double sum is cheap and keeps this a
    dependency-light core module.
    """
    tickers = list(weights)
    if not tickers:
        return 0.0
    sig = {t: _vol_fraction(risk.get(t), caps) for t in tickers}
    lookup: dict[tuple[str, str], float] = {}
    if corr is not None:
        try:
            lookup = {
                (r["a"], r["b"]): float(r["corr"])
                for r in corr.select(["a", "b", "corr"]).to_dicts()
            }
        except Exception:  # noqa: BLE001 — bad corr frame → full-correlation default below
            lookup = {}
    var = 0.0
    for ti in tickers:
        for tj in tickers:
            if ti == tj:
                rho = 1.0
            else:
                c = lookup.get((ti, tj), lookup.get((tj, ti)))
                rho = float(c) if c is not None else 1.0  # unknown → conservatively correlated
            var += weights[ti] * weights[tj] * sig[ti] * sig[tj] * rho
    return (var if var > 0.0 else 0.0) ** 0.5 * 100.0


def _round_to_grid(weights_pct: dict[str, float], increment: float) -> dict[str, float]:
    """Round each weight (%) DOWN to the ``increment`` grid (0 disables).

    Always rounding *down* (never to nearest) keeps the reduce-only invariant: the
    remainder becomes cash, so grid-snapping can never lift gross above 100% or re-breach
    a cap that was just applied. The 1e-9 nudge absorbs float-representation noise (e.g.
    0.30 × 100 = 29.999…6) so an on-grid weight isn't spuriously knocked down a notch.
    """
    if increment <= 0:
        return weights_pct
    return {t: int(p / increment + 1e-9) * increment for t, p in weights_pct.items()}


def size_portfolio(
    *,
    convictions: Mapping[str, float],
    stances: Mapping[str, str],
    risk: Mapping[str, TickerRisk],
    corr: Any | None = None,
    caps: SizingCaps | None = None,
    breaker_scale: float = 1.0,
) -> SizingResult:
    """Turn per-ticker conviction + direction into final target weights (see module doc).

    Args:
        convictions: effective conviction per ticker (analyst + debate delta, −5..+5).
        stances: per-ticker stance (buy/hold/sell/watch); only buy/hold enter the book.
        risk: per-ticker :class:`TickerRisk` (vol + sector bucket).
        corr: optional long correlation frame (cols ``a``/``b``/``corr``); diagonal if None.
        caps: :class:`SizingCaps` (defaults if None).
        breaker_scale: ≤ 1.0 multiplier from the drawdown circuit breaker (raises cash).

    Returns:
        A :class:`SizingResult` — final positions (%), cash %, ex-ante vol, applied
        scales, and a human-readable explanation. An empty book (= 100% cash) is valid.
    """
    caps = caps or SizingCaps()
    breaker = max(0.0, min(1.0, float(breaker_scale)))

    selected = _select(convictions, stances, caps.min_conviction)
    if not selected:
        return SizingResult(
            positions=[],
            cash_pct=100.0,
            gross_pct=0.0,
            realized_portfolio_vol=0.0,
            applied_scales={"breaker_scale": round(breaker, 3)},
            explanation="No ticker cleared the conviction bar → 100% cash (defensive).",
        )

    notes: dict[str, list[str]] = {t: [] for t in selected}
    raw = _raw_weights(selected, risk, caps)
    pre_cap_pct = {t: round(w * 100.0, 4) for t, w in raw.items()}
    raw = _apply_position_caps(raw, caps, notes)
    raw = _apply_sector_caps(raw, risk, caps, notes)
    raw = _corr_dedup(raw, convictions, corr, caps, notes)

    if not raw:
        return SizingResult(
            positions=[],
            cash_pct=100.0,
            gross_pct=0.0,
            realized_portfolio_vol=0.0,
            applied_scales={"breaker_scale": round(breaker, 3)},
            explanation="All candidates dropped by caps/de-dup → 100% cash.",
        )

    port_vol = _portfolio_vol(raw, risk, corr, caps)
    vol_scale = min(1.0, caps.target_portfolio_vol / port_vol) if port_vol > 0 else 1.0
    gross_scale = min(caps.max_gross_pct / 100.0, vol_scale) * breaker

    sized_pct = _round_to_grid(
        {t: w * gross_scale * 100.0 for t, w in raw.items()}, caps.weight_increment_pct
    )

    positions = [
        SizedPosition(
            ticker=t,
            target_pct=round(p, 4),
            sector=(risk.get(t).sector if risk.get(t) else "UNKNOWN"),
            raw_conviction=float(convictions.get(t, 0.0)),
            pre_cap_pct=pre_cap_pct.get(t, 0.0),
            notes=notes.get(t, []),
        )
        for t, p in sized_pct.items()
        if p > 0
    ]
    gross = round(sum(p.target_pct for p in positions), 4)
    cash = max(0.0, round(100.0 - gross, 4))
    final_vol = _portfolio_vol(
        {p.ticker: p.target_pct / 100.0 for p in positions}, risk, corr, caps
    )

    explanation = (
        f"{len(positions)} holdings, {gross:g}% invested / {cash:g}% cash; "
        f"ex-ante vol ~{final_vol:.1f}% (target {caps.target_portfolio_vol:g}%); "
        f"vol_scale={vol_scale:.2f}, breaker={breaker:.2f}, mode={caps.sizing_mode}."
    )
    return SizingResult(
        positions=positions,
        cash_pct=cash,
        gross_pct=gross,
        realized_portfolio_vol=round(final_vol, 2),
        applied_scales={"vol_scale": round(vol_scale, 3), "breaker_scale": round(breaker, 3)},
        explanation=explanation,
    )


__all__ = ["SizedPosition", "SizingCaps", "SizingResult", "TickerRisk", "size_portfolio"]
