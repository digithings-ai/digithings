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

Every **cap / de-dup** step is **reduce-only / cash-first**: weight freed by a cap or a
dropped leg becomes CASH, never redistributed up to the survivors (a plain renormalize
would re-breach the cap it just enforced). The **vol-target** step is the deliberate
exception — it may scale the surviving book UP to fill an unused vol budget, but still
never past the gross / position / sector caps (#943: without an up-scale a quiet book
drifts monotonically to cash). The pipeline:

    select(conv ≥ min, stance buy/hold)  [or calibrated_scores > 0 when cut over]
      → raw weights (calibrated μ/σ/reliability, OR conviction-∝ × inverse-vol, OR Kelly)
      → position caps (min floor / max cap; freed weight → cash)
      → sector caps (scale down any over-cap bucket; freed weight → cash)
      → correlation de-dup (drop the lower-conviction leg of a > threshold pair → cash)
      → vol-target scale (ex-ante √(wᵀΣw) → up to the budget or down if hot; capped)
      → drawdown-breaker scale (only ever reduces gross)
      → PM confidence scale (optional; reduce-only / cash-first)
      → round DOWN to the weight grid (remainder → cash) → cash = 100 − Σ

WP8.4 (#2734): when ``calibrated_scores`` is provided, raw weights come from those scores
(approved policy: reliability × max(0, μ) / σ_ε). Rank→conviction and fixed-premium Kelly
are not used on that path. Downstream controls are unchanged.

WP-H: optional ``confidence_scales`` (H7 ``confidence`` ∈ [0, 1] per long) haircut each
name **after** vol-target / breaker and **before** the 5% grid. That is reduce-only /
cash-first: leftover stays cash and is never renormalized into peers (vol-target must
not absorb the haircut). Rank remains display/order only on the calibrated path.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from digiquant.portfolio.sizing_events import SizingAdjustment, SizingAdjustmentType


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
    sector: str = "UNKNOWN"  # fine concentration bucket (GICS/sleeve slug)
    asset_class: str = "UNKNOWN"  # coarse class (EQUITY/FIXED_INCOME/…) for corr fallback


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
    # #2417: reason-coded, in-memory-only explanation of every material adjustment this
    # pass made (caps / de-dup / vol-scale / breaker / grid-rounding). Explanation-only —
    # never changes a weight, never persisted. Empty list is valid (nothing was adjusted).
    adjustments: list[SizingAdjustment] = field(default_factory=list)
    # H8's own pre-cap/pre-scale request for every selected ticker (the "requested"
    # side of a requested->approved delta), keyed by ticker, in percent. Distinct from
    # ``SizedPosition.pre_cap_pct`` in that it also covers tickers this pass dropped
    # entirely (min-floor, sector cap, corr-dedup) — those never make it into
    # ``positions`` at all, so a caller reconciling "what did H8 want" needs this map,
    # not just the survivors.
    requested_pct: dict[str, float] = field(default_factory=dict)
    # Set only on a fully-flat (100% cash) result, distinguishing WHY the book is
    # empty — never conflate an H7-driven flat decision with a sizing-side dropout.
    flat_reason: Literal["no_conviction_cleared_bar", "all_candidates_dropped"] | None = None


_ANNUALIZE = 16.0  # ≈ sqrt(252) — daily → annual vol scaling for the ATR fallback


def calibrated_raw_score(
    *,
    expected_gross_return: float,
    forecast_error_std: float,
    reliability_weight: float,
) -> float:
    """Approved WP8.4 raw-score policy: reliability × max(0, μ) / σ_ε.

    Negative or zero expected return contributes no long risk (no contrary short).
    Uncertainty must be strictly positive — never invent zero uncertainty.
    """
    if forecast_error_std <= 0:
        raise ValueError("forecast_error_std must be positive")
    reliability = max(0.0, float(reliability_weight))
    alpha = max(0.0, float(expected_gross_return))
    return reliability * alpha / float(forecast_error_std)


def _vol_fraction(risk: TickerRisk | None, caps: SizingCaps) -> float:
    """Annualized vol as a fraction (e.g. 0.20). Falls back atr_pct → default."""
    if risk is not None and risk.hist_vol_21 is not None and risk.hist_vol_21 > 0:
        return float(risk.hist_vol_21) / 100.0
    if risk is not None and risk.atr_pct is not None and risk.atr_pct > 0:
        return float(risk.atr_pct) / 100.0 * _ANNUALIZE
    return caps.default_annual_vol / 100.0


def _select(
    convictions: Mapping[str, float],
    stances: Mapping[str, str],
    min_conviction: float,
    *,
    calibrated_scores: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Tickers entering the book.

    Incumbent: effective conviction ≥ bar AND long-side stance (buy/hold).
    Calibrated cutover: positive calibrated score AND long-side stance — conviction
    magnitude is not used for membership.
    """
    if calibrated_scores is not None:
        return {
            ticker: float(score)
            for ticker, score in calibrated_scores.items()
            if float(score) > 0 and str(stances.get(ticker, "hold")).lower() in ("buy", "hold")
        }
    return {
        ticker: float(conv)
        for ticker, conv in convictions.items()
        if float(conv) >= min_conviction
        and str(stances.get(ticker, "hold")).lower() in ("buy", "hold")
    }


def _raw_weights(
    selected: Mapping[str, float],
    risk: Mapping[str, TickerRisk],
    caps: SizingCaps,
    *,
    calibrated_scores: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Raw fractional weights (sum 1.0) before caps.

    - Calibrated (WP8.4): w ∝ calibrated_scores (already reliability × max(0,μ) / σ_ε).
    - ``conviction_vol``: w ∝ conviction / vol (conviction-weighted, inverse-vol tilt).
    - ``kelly``: w ∝ fractional-Kelly f = kelly_fraction · edge / vol² where edge scales
      with conviction (incumbent fallback only — absent from live calibrated path).
    """
    scores: dict[str, float] = {}
    if calibrated_scores is not None:
        for ticker in selected:
            scores[ticker] = max(0.0, float(calibrated_scores.get(ticker, 0.0)))
    else:
        for ticker, conv in selected.items():
            vol = _vol_fraction(risk.get(ticker), caps)
            if caps.sizing_mode == "kelly":
                edge = (conv / 5.0) * caps.kelly_annual_premium
                scores[ticker] = (
                    max(0.0, caps.kelly_fraction * edge / (vol * vol)) if vol > 0 else 0.0
                )
            else:
                scores[ticker] = (conv / vol) if vol > 0 else 0.0
    total = sum(scores.values())
    if total <= 0:
        # Degenerate (all-zero) → equal weight the selected set.
        n = len(selected)
        return {t: 1.0 / n for t in selected} if n else {}
    return {t: s / total for t, s in scores.items()}


def _apply_position_caps(
    weights: dict[str, float],
    caps: SizingCaps,
    notes: dict[str, list[str]],
    events: list[SizingAdjustment] | None = None,
) -> dict[str, float]:
    """Clamp each weight to [min, max] (as fractions), drop sub-min, renormalize."""
    lo, hi = caps.min_position_pct / 100.0, caps.max_position_pct / 100.0
    out: dict[str, float] = {}
    for ticker, w in weights.items():
        if w < lo:
            reason = f"dropped (<{caps.min_position_pct:g}% min)"
            notes.setdefault(ticker, []).append(reason)
            if events is not None:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.SINGLE_NAME_CAP,
                        original_pct=round(w * 100.0, 4),
                        adjusted_pct=0.0,
                        reason=reason,
                    )
                )
            continue
        if w > hi:
            reason = f"capped @{caps.max_position_pct:g}%"
            notes.setdefault(ticker, []).append(reason)
            if events is not None:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.SINGLE_NAME_CAP,
                        original_pct=round(w * 100.0, 4),
                        adjusted_pct=round(hi * 100.0, 4),
                        reason=reason,
                    )
                )
            w = hi
        out[ticker] = w
    # Reduce-only: weight freed by capping/dropping becomes cash — never scale UP past
    # the caps (which a plain renormalize would do). Renormalize down only if over-allocated.
    total = sum(out.values())
    if total <= 1.0:
        return out
    scale = 1.0 / total
    if events is not None:
        for ticker, w in out.items():
            new_w = w * scale
            if abs(new_w - w) > 1e-9:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.SINGLE_NAME_CAP,
                        original_pct=round(w * 100.0, 4),
                        adjusted_pct=round(new_w * 100.0, 4),
                        reason=f"renormalized (post-cap total {total * 100.0:.2f}% > 100%)",
                    )
                )
    return {t: w * scale for t, w in out.items()}


def _apply_sector_caps(
    weights: dict[str, float],
    risk: Mapping[str, TickerRisk],
    caps: SizingCaps,
    notes: dict[str, list[str]],
    events: list[SizingAdjustment] | None = None,
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
                    reason = f"{sector} sector-capped"
                    out[ticker] *= scale
                    notes.setdefault(ticker, []).append(reason)
                    if events is not None:
                        # One event per affected ticker even though ``scale`` is shared
                        # portfolio-wide for the sector — do not collapse to a single
                        # portfolio-level event (#2417 spec §1 row 3). Read straight off
                        # the values already computed above — never re-derive.
                        events.append(
                            SizingAdjustment(
                                ticker=ticker,
                                adjustment_type=SizingAdjustmentType.SECTOR_CAP,
                                original_pct=round(weights[ticker] * 100.0, 4),
                                adjusted_pct=round(out[ticker] * 100.0, 4),
                                reason=reason,
                            )
                        )
    # Reduce-only (cash-first): sector scaling only ever lowers a weight, so the freed
    # weight becomes cash — never renormalize the under-cap buckets back up past the caps.
    grand = sum(out.values())
    if grand <= 1.0:
        return out
    scale = 1.0 / grand
    if events is not None:
        for ticker, w in out.items():
            new_w = w * scale
            if abs(new_w - w) > 1e-9:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.SECTOR_CAP,
                        original_pct=round(w * 100.0, 4),
                        adjusted_pct=round(new_w * 100.0, 4),
                        reason=f"renormalized (post-sector-cap total {grand * 100.0:.2f}% > 100%)",
                    )
                )
    return {t: w * scale for t, w in out.items()}


def _corr_dedup(
    weights: dict[str, float],
    convictions: Mapping[str, float],
    corr: Any | None,
    caps: SizingCaps,
    notes: dict[str, list[str]],
    events: list[SizingAdjustment] | None = None,
) -> dict[str, float]:
    """Drop the lower-conviction leg of any pair with |corr| > threshold, then renormalize.

    ``corr`` is a long Polars frame with columns ``a``, ``b``, ``corr`` (or ``None``).
    """
    if corr is None or len(weights) < 2:
        return weights
    try:
        rows = corr.select(["a", "b", "corr"]).to_dicts()
    except Exception:  # bad/empty corr frame → skip de-dup (conservative)
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
            reason = f"corr-dedup (>{caps.corr_dedup_threshold:g} with {keeper})"
            notes.setdefault(loser, []).append(reason)
            if events is not None:
                events.append(
                    SizingAdjustment(
                        ticker=loser,
                        adjustment_type=SizingAdjustmentType.CORRELATION_DEDUP,
                        original_pct=round(weights[loser] * 100.0, 4),
                        adjusted_pct=0.0,
                        reason=reason,
                    )
                )
    # Reduce-only (cash-first): a dropped leg's weight becomes cash, not redistributed to
    # the surviving leg. Renormalize down only in the defensive over-allocation case.
    kept = {t: w for t, w in weights.items() if t not in dropped}
    total = sum(kept.values())
    if total <= 1.0:
        return kept
    scale = 1.0 / total
    if events is not None:
        for ticker, w in kept.items():
            new_w = w * scale
            if abs(new_w - w) > 1e-9:
                events.append(
                    SizingAdjustment(
                        ticker=ticker,
                        adjustment_type=SizingAdjustmentType.CORRELATION_DEDUP,
                        original_pct=round(w * 100.0, 4),
                        adjusted_pct=round(new_w * 100.0, 4),
                        reason=f"renormalized (post-dedup total {total * 100.0:.2f}% > 100%)",
                    )
                )
    return {t: w * scale for t, w in kept.items()}


# Asset-class pairwise correlation defaults for pairs lacking an *estimated* rho
# (thin history). Carver "handcrafting" style — crude-but-stable coarse buckets beat a
# precise-but-noisy guess, and beat the prior ρ=1.0 default which over-stated portfolio
# vol and made vol-targeting systematically over-raise cash (#934).
_SAME_CLASS_CORR = {
    "EQUITY": 0.80,
    "INTERNATIONAL": 0.80,
    "FIXED_INCOME": 0.60,
    "COMMODITY": 0.30,
    "CRYPTO": 0.60,
    "FX": 0.30,
}
_CROSS_CLASS_CORR = {
    frozenset({"EQUITY", "INTERNATIONAL"}): 0.75,
    frozenset({"EQUITY", "FIXED_INCOME"}): 0.00,
    frozenset({"INTERNATIONAL", "FIXED_INCOME"}): 0.00,
    frozenset({"EQUITY", "COMMODITY"}): 0.10,
    frozenset({"INTERNATIONAL", "COMMODITY"}): 0.10,
    frozenset({"EQUITY", "CRYPTO"}): 0.40,
    frozenset({"FIXED_INCOME", "COMMODITY"}): 0.10,
}
_DEFAULT_CROSS_CORR = 0.25  # unrelated classes — mild positive default
_UNKNOWN_CORR = 1.0  # class unknown → conservative full-correlation (prior default preserved)


def _bucket_corr(class_a: str, class_b: str) -> float:
    """Fallback pairwise correlation from coarse asset classes (symmetric).

    Used by :func:`_portfolio_vol` when no estimated rho exists for a pair. CASH is
    uncorrelated; an UNKNOWN class stays conservatively full-correlated (1.0) so the
    diversification credit only applies to pairs whose classes we actually know;
    same-class and cross-class defaults come from the tables above.
    """
    a, b = (class_a or "UNKNOWN").upper(), (class_b or "UNKNOWN").upper()
    if a == "CASH" or b == "CASH":
        return 0.0
    if "UNKNOWN" in (a, b):
        return _UNKNOWN_CORR
    if a == b:
        return _SAME_CLASS_CORR.get(a, 0.60)
    return _CROSS_CLASS_CORR.get(frozenset({a, b}), _DEFAULT_CROSS_CORR)


def _portfolio_vol(
    weights: Mapping[str, float], risk: Mapping[str, TickerRisk], corr: Any | None, caps: SizingCaps
) -> float:
    """Ex-ante annualized portfolio vol (%) for fractional ``weights``: √(wᵀΣw) with
    Σᵢⱼ = σᵢ σⱼ ρᵢⱼ.

    Estimated correlations (``corr`` frame) are used when present. A pair with no estimate
    — ``corr`` is ``None``, the pair is absent, or the frame fails to parse — falls back to
    an **asset-class bucket** rho via :func:`_bucket_corr` (e.g. equity↔bond≈0, equity↔equity
    ≈0.8), NOT ρ=1.0. The old full-correlation default over-stated vol and made vol-targeting
    over-raise cash (#934); the bucket gives a diversified book its diversification credit
    while staying conservative on genuinely unknown pairs. Pure Python (no numpy): the
    holdings count is small, so the O(n²) double sum is cheap and dependency-light.
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
        except Exception:  # bad corr frame → full-correlation default below
            lookup = {}
    var = 0.0
    for ti in tickers:
        for tj in tickers:
            if ti == tj:
                rho = 1.0
            else:
                c = lookup.get((ti, tj), lookup.get((tj, ti)))
                if c is not None:
                    rho = float(c)
                else:  # no estimate → asset-class bucket fallback (not full-correlation)
                    ri, rj = risk.get(ti), risk.get(tj)
                    rho = _bucket_corr(
                        ri.asset_class if ri else "UNKNOWN",
                        rj.asset_class if rj else "UNKNOWN",
                    )
            var += weights[ti] * weights[tj] * sig[ti] * sig[tj] * rho
    return (var if var > 0.0 else 0.0) ** 0.5 * 100.0


def _apply_confidence_scales(
    weights_pct: dict[str, float],
    confidence_scales: Mapping[str, float] | None,
    events: list[SizingAdjustment],
) -> dict[str, float]:
    """Reduce-only per-name scale from H7 confidence. Leftover stays cash.

    Applied after vol-target / breaker so an unused vol budget cannot redistribute a
    haircut into other names. A ticker omitted from ``confidence_scales`` is left
    unchanged (callers that want the fail-soft default must fill the map).
    """
    if not confidence_scales:
        return weights_pct
    out: dict[str, float] = {}
    for ticker, weight_pct in weights_pct.items():
        if ticker not in confidence_scales:
            out[ticker] = weight_pct
            continue
        scale = max(0.0, min(1.0, float(confidence_scales[ticker])))
        scaled = weight_pct * scale
        if abs(scaled - weight_pct) > 1e-9:
            events.append(
                SizingAdjustment(
                    ticker=ticker,
                    adjustment_type=SizingAdjustmentType.FINAL_GROSS_SCALE,
                    original_pct=round(weight_pct, 4),
                    adjusted_pct=round(scaled, 4),
                    reason=f"PM confidence ×{scale:.2f} (cash-first; leftover stays cash)",
                )
            )
        out[ticker] = scaled
    return out


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
    calibrated_scores: Mapping[str, float] | None = None,
    confidence_scales: Mapping[str, float] | None = None,
) -> SizingResult:
    """Turn per-ticker conviction + direction into final target weights (see module doc).

    Args:
        convictions: effective conviction per ticker (analyst + debate delta, −5..+5).
            On the calibrated path used for corr-dedup priority only (not raw magnitude).
        stances: per-ticker stance (buy/hold/sell/watch); only buy/hold enter the book.
        risk: per-ticker :class:`TickerRisk` (vol + sector bucket).
        corr: optional long correlation frame (cols ``a``/``b``/``corr``); diagonal if None.
        caps: :class:`SizingCaps` (defaults if None).
        breaker_scale: ≤ 1.0 multiplier from the drawdown circuit breaker (raises cash).
        calibrated_scores: optional WP8.4 scores (reliability × max(0, μ) / σ_ε). When set,
            drives selection + raw weights; rank→conviction and Kelly premium are unused.
        confidence_scales: optional per-ticker H7 confidence in ``[0, 1]``. Applied
            after vol-target / breaker, cash-first (no renormalize). Omitted tickers
            are unchanged; callers fill missing values with the documented default.

    Returns:
        A :class:`SizingResult` — final positions (%), cash %, ex-ante vol, applied
        scales, and a human-readable explanation. An empty book (= 100% cash) is valid.
    """
    caps = caps or SizingCaps()
    breaker = max(0.0, min(1.0, float(breaker_scale)))
    # #2417: reason-coded, in-memory-only adjustment events accumulated across every
    # reduce-only step below. Explanation-only — never read back into the weight math.
    events: list[SizingAdjustment] = []

    selected = _select(
        convictions, stances, caps.min_conviction, calibrated_scores=calibrated_scores
    )
    if not selected:
        return SizingResult(
            positions=[],
            cash_pct=100.0,
            gross_pct=0.0,
            realized_portfolio_vol=0.0,
            applied_scales={"breaker_scale": round(breaker, 3)},
            explanation="No ticker cleared the conviction bar → 100% cash (defensive).",
            flat_reason="no_conviction_cleared_bar",
        )

    notes: dict[str, list[str]] = {t: [] for t in selected}
    raw = _raw_weights(selected, risk, caps, calibrated_scores=calibrated_scores)
    pre_cap_pct = {t: round(w * 100.0, 4) for t, w in raw.items()}
    raw = _apply_position_caps(raw, caps, notes, events=events)
    raw = _apply_sector_caps(raw, risk, caps, notes, events=events)
    # Corr-dedup: prefer calibrated score magnitude when present; else conviction.
    dedup_priority = (
        {t: float(calibrated_scores.get(t, 0.0)) for t in selected}
        if calibrated_scores is not None
        else convictions
    )
    raw = _corr_dedup(raw, dedup_priority, corr, caps, notes, events=events)

    if not raw:
        return SizingResult(
            positions=[],
            cash_pct=100.0,
            gross_pct=0.0,
            realized_portfolio_vol=0.0,
            applied_scales={"breaker_scale": round(breaker, 3)},
            explanation="All candidates dropped by caps/de-dup → 100% cash.",
            adjustments=list(events),
            requested_pct=dict(pre_cap_pct),
            flat_reason="all_candidates_dropped",
        )

    port_vol = _portfolio_vol(raw, risk, corr, caps)
    # Vol-target scale: the book may be scaled UP toward the budget, not only down. The
    # reduce-only steps above (caps / sector caps / corr-dedup) only ever free weight to
    # cash, so without an up-scale an under-risked book drifts monotonically cash-heavy
    # (the Jun-2026 over-cashing: a quiet book sat at ~0.1% vol vs a 12% budget; #943).
    # The up-scale is bounded so it can NEVER breach the gross cap, any per-position cap,
    # or any sector cap — those reduce-only ceilings still hold; only the unused vol budget
    # is filled. A hot book (port_vol > target) still scales down exactly as before.
    vol_scale = caps.target_portfolio_vol / port_vol if port_vol > 0 else 1.0
    gross_sum = sum(raw.values())
    max_weight = max(raw.values(), default=0.0)
    sector_sums: dict[str, float] = {}
    for _t, _w in raw.items():
        _sec = risk.get(_t).sector if risk.get(_t) else "UNKNOWN"
        sector_sums[_sec] = sector_sums.get(_sec, 0.0) + _w
    max_sector = max(sector_sums.values(), default=0.0)
    gross_cap_scale = (caps.max_gross_pct / 100.0) / gross_sum if gross_sum > 0 else 1.0
    pos_cap_scale = (caps.max_position_pct / 100.0) / max_weight if max_weight > 0 else 1.0
    sector_cap_scale = (caps.max_sector_pct / 100.0) / max_sector if max_sector > 0 else 1.0
    pre_breaker_scale = max(0.0, min(vol_scale, gross_cap_scale, pos_cap_scale, sector_cap_scale))
    gross_scale = pre_breaker_scale * breaker
    # Whichever of the four candidate scales is binding determines the adjustment reason:
    # vol → VOLATILITY_SCALE (this stage); gross/pos/sector binding → FINAL_GROSS_SCALE
    # (#2417 site (a)) — every material scale-down at this stage now gets exactly one event,
    # whichever candidate scale actually bound.
    binding_label = min(
        (vol_scale, "vol"),
        (gross_cap_scale, "gross"),
        (pos_cap_scale, "pos"),
        (sector_cap_scale, "sector"),
        key=lambda pair: pair[0],
    )[1]
    if abs(pre_breaker_scale - 1.0) > 1e-9:
        if binding_label == "vol":
            adj_type = SizingAdjustmentType.VOLATILITY_SCALE
            reason = (
                f"vol-target scale x{pre_breaker_scale:.3f} "
                f"(port_vol={port_vol:.2f}% vs target {caps.target_portfolio_vol:g}%)"
            )
        else:
            adj_type = SizingAdjustmentType.FINAL_GROSS_SCALE
            binding_desc = {
                "gross": f"gross cap {caps.max_gross_pct:g}%",
                "pos": f"position cap {caps.max_position_pct:g}%",
                "sector": f"sector cap {caps.max_sector_pct:g}%",
            }[binding_label]
            reason = f"scaled x{pre_breaker_scale:.3f} (binding: {binding_desc})"
        for t, w in raw.items():
            events.append(
                SizingAdjustment(
                    ticker=t,
                    adjustment_type=adj_type,
                    original_pct=round(w * 100.0, 4),
                    adjusted_pct=round(w * pre_breaker_scale * 100.0, 4),
                    reason=reason,
                )
            )
    if abs(breaker - 1.0) > 1e-9:
        for t, w in raw.items():
            pre_breaker_pct = w * pre_breaker_scale * 100.0
            events.append(
                SizingAdjustment(
                    ticker=t,
                    adjustment_type=SizingAdjustmentType.DRAWDOWN_BREAKER,
                    original_pct=round(pre_breaker_pct, 4),
                    adjusted_pct=round(pre_breaker_pct * breaker, 4),
                    reason=f"drawdown breaker x{breaker:.3f}",
                )
            )

    pre_round_pct = {t: w * gross_scale * 100.0 for t, w in raw.items()}
    pre_round_pct = _apply_confidence_scales(pre_round_pct, confidence_scales, events)
    sized_pct = _round_to_grid(pre_round_pct, caps.weight_increment_pct)
    for t, snapped in sized_pct.items():
        pre_p = pre_round_pct.get(t, 0.0)
        if abs(snapped - pre_p) > 1e-9:
            events.append(
                SizingAdjustment(
                    ticker=t,
                    adjustment_type=SizingAdjustmentType.GRID_ROUNDING,
                    original_pct=round(pre_p, 4),
                    adjusted_pct=round(snapped, 4),
                    reason=(
                        f"rounded to zero on the {caps.weight_increment_pct:g}% sizing grid"
                        if snapped <= 0
                        else f"grid-rounded down to {caps.weight_increment_pct:g}% increments"
                    ),
                )
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

    confidence_note = ""
    if confidence_scales and any(
        t in confidence_scales and float(confidence_scales[t]) < 1.0 - 1e-12 for t in sized_pct
    ):
        confidence_note = " PM confidence scaled size (cash-first)."
    explanation = (
        f"{len(positions)} holdings, {gross:g}% invested / {cash:g}% cash; "
        f"ex-ante vol ~{final_vol:.1f}% (target {caps.target_portfolio_vol:g}%); "
        f"vol_scale={vol_scale:.2f}, breaker={breaker:.2f}, "
        f"mode={'calibrated' if calibrated_scores is not None else caps.sizing_mode}."
        f"{confidence_note}"
    )
    return SizingResult(
        positions=positions,
        cash_pct=cash,
        gross_pct=gross,
        realized_portfolio_vol=round(final_vol, 2),
        applied_scales={"vol_scale": round(vol_scale, 3), "breaker_scale": round(breaker, 3)},
        explanation=explanation,
        adjustments=list(events),
        requested_pct=dict(pre_cap_pct),
    )


__all__ = [
    "SizedPosition",
    "SizingCaps",
    "SizingResult",
    "TickerRisk",
    "calibrated_raw_score",
    "size_portfolio",
]
