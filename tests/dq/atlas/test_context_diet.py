"""Unit tests for the shared-context diet (#935).

The ``_shared_context`` block was the #2 cost driver after model routing: the
whole ``data_layer`` (every ETF's technicals + every macro series) and the full
``last_snapshots`` history were dumped into every phase node's prompt. The diet
adds two knobs — a per-phase ``data_layer_scope`` allowlist and delta-aware
``slim_snapshots`` — that slim the block without changing what a phase reasons
about. These tests assert a byte/size budget and the per-phase allowlist shape.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: test fixture dicts

import pytest

from digiquant.olympus.atlas.phases._node_factory import (
    _scoped_data_layer,
    _shared_context,
)
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    DataLayerSnapshot,
    DeltaTriageDecision,
    DeltaTriageResult,
    PriorContext,
    SegmentPayload,
    SegmentSlot,
)

pytestmark = pytest.mark.unit

RUN_DATE = date(2026, 6, 19)
BASELINE_DATE = date(2026, 6, 15)

# A representative market_context: ~20 ETFs each with the 12 technical columns,
# plus ~12 macro series and the two compact regime signals. This is the block
# that dominates the per-call prompt cost — the diet trims it per phase.
_TECH_COLS = (
    "date",
    "sma_50",
    "sma_200",
    "pct_vs_sma50",
    "pct_vs_sma200",
    "rsi_14",
    "macd_hist",
    "roc_21",
    "adx_14",
    "atr_pct",
    "bb_pct_b",
    "zscore_200",
)
_ETFS = (
    "SPY",
    "QQQ",
    "IWM",
    "DIA",
    "TLT",
    "IEF",
    "GLD",
    "SLV",
    "USO",
    "UNG",
    "XLK",
    "XLF",
    "XLE",
    "XLV",
    "XLY",
    "XLP",
    "XLI",
    "XLU",
    "XLB",
    "XLRE",
)
_MACRO_SERIES = (
    "DGS10",
    "DGS2",
    "DFF",
    "VIXCLS",
    "T10Y2Y",
    "CPIAUCSL",
    "UNRATE",
    "DTWEXBGS",
    "DCOILWTICO",
    "M2SL",
    "FEDFUNDS",
    "PAYEMS",
)


def _market_context() -> dict[str, Any]:
    return {
        "as_of": RUN_DATE.isoformat(),
        "price_technicals": {
            etf: {col: (RUN_DATE.isoformat() if col == "date" else 1.23) for col in _TECH_COLS}
            for etf in _ETFS
        },
        "macro_series": {
            sid: {"date": RUN_DATE.isoformat(), "value": 4.21, "prev_value": 4.19, "unit": "%"}
            for sid in _MACRO_SERIES
        },
        "fed_odds": {"meeting": "2026-07", "cut_25bp": 0.62, "hold": 0.30},
        "onchain_positioning": {"overall_divergence": "bullish", "top": ["BTC", "ETH"]},
    }


def _data_layer() -> DataLayerSnapshot:
    return DataLayerSnapshot(
        price_technicals_latest=date(2026, 6, 18),
        price_technicals_ticker_count=len(_ETFS),
        macro_series_latest=date(2026, 6, 18),
        fallback_used="supabase",
        market_context=_market_context(),
    )


def _full_snapshot(d: str, run_type: str) -> dict[str, Any]:
    """A daily_snapshots read row with a fat ``snapshot`` payload — the bloat
    the delta diet drops from shared_context."""
    return {
        "date": d,
        "run_type": run_type,
        "baseline_date": BASELINE_DATE.isoformat(),
        "snapshot": {
            "date": d,
            "run_type": run_type,
            "macro_regime": "late-cycle expansion",
            "equity_bias": "constructive",
            "crypto_bias": "neutral",
            "bond_bias": "cautious",
            "commodity_bias": "neutral",
            "forex_bias": "usd-strong",
            "vix_level": 14.2,
            "fed_odds": {"cut_25bp": 0.62},
            "regime_label": "goldilocks",
            "market_regime_snapshot": "risk-on with a watchful eye on rates",
            # The fat fields a delta node does NOT need re-serialized every call:
            "segment_summaries": {f"seg-{i}": "x" * 400 for i in range(12)},
            "actionable_summary": [{"ticker": t, "note": "y" * 200} for t in _ETFS],
            "risk_radar": [{"risk": "z" * 300} for _ in range(8)],
        },
    }


def _prior_context() -> PriorContext:
    # 5-snapshot history — the historical worst case the delta diet collapses.
    snaps = [
        _full_snapshot("2026-06-18", "delta"),
        _full_snapshot("2026-06-17", "delta"),
        _full_snapshot("2026-06-16", "delta"),
        _full_snapshot("2026-06-15", "baseline"),
        _full_snapshot("2026-06-14", "delta"),
    ]
    segments = {
        key: {"date": "2026-06-18", "document_key": key, "doc_type": None, "payload": {"k": key}}
        for key in ("macro", "bonds", "equity", "sector-technology", "analyst/NVDA", "pm-rebalance")
    }
    return PriorContext(last_snapshots=snaps, latest_segments=segments)


def _today_slot(slug: str) -> SegmentSlot:
    return SegmentSlot(payload=SegmentPayload(segment=slug, body={"bias": "up"}, as_of=RUN_DATE))


def _delta_state() -> AtlasResearchState:
    """A representative DELTA run: fat market_context + 5-snapshot history +
    a triage result marking some segments regenerate, some carry."""
    return AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=BASELINE_DATE,
        prior_context=_prior_context(),
        data_layer=_data_layer(),
        phase4_outputs={"bonds": _today_slot("bonds"), "crypto": _today_slot("crypto")},
        triage=DeltaTriageResult(
            evaluated_at=RUN_DATE,
            baseline_date=BASELINE_DATE,
            decisions=[
                DeltaTriageDecision(
                    segment="bonds", decision="regenerate", reason="moved", tier="high"
                ),
                DeltaTriageDecision(
                    segment="commodities", decision="carry", reason="flat", tier="low"
                ),
            ],
        ),
    )


def _baseline_state() -> AtlasResearchState:
    """The equivalent BASELINE run: same data, but full context (no diet)."""
    return AtlasResearchState(
        run_type="baseline",
        run_date=RUN_DATE,
        baseline_date=BASELINE_DATE,
        prior_context=_prior_context(),
        data_layer=_data_layer(),
    )


def _size(context: dict[str, Any]) -> int:
    """Deterministic serialized size of a shared_context block — exactly how
    ``research_agent._format_scope_block`` measures it (sort_keys, default=str)."""
    return len(json.dumps(context, default=str, sort_keys=True))


# --- byte budget: delta diet is strictly smaller and ≥30% under baseline -----


def test_delta_context_is_strictly_smaller_than_baseline() -> None:
    # A representative full-context delta phase (cross-asset, data_layer_scope=full)
    # still slims the snapshot history on a delta run; compare to the baseline
    # build of the same phase, which keeps the full 5-snapshot history.
    delta = _shared_context(_delta_state(), context_keys=("bonds", "macro"))
    baseline = _shared_context(_baseline_state(), context_keys=("bonds", "macro"))
    assert _size(delta) < _size(baseline)


def test_delta_full_phase_hits_30pct_budget_vs_baseline() -> None:
    # The headline acceptance criterion: a delta phase's shared_context is ≥30%
    # smaller than the baseline phase's. Measured deterministically by serialized
    # byte length. The drop comes from collapsing the 5-snapshot history to a
    # slim bias row + changed segments.
    delta = _size(_shared_context(_delta_state(), context_keys=("bonds", "macro")))
    baseline = _size(_shared_context(_baseline_state(), context_keys=("bonds", "macro")))
    drop = (baseline - delta) / baseline
    assert drop >= 0.30, f"context diet only cut {drop:.1%}; expected >= 30%"


def test_analyst_ticker_scope_hits_30pct_budget_vs_baseline_full() -> None:
    # The analyst node (ticker scope) on a delta run is the cheapest phase: it
    # drops BOTH the per-ticker ETF dump and the bulk macro series AND slims the
    # snapshot history. Compare to a baseline full-context node.
    delta_analyst = _size(
        _shared_context(_delta_state(), context_keys=(), data_layer_scope="ticker")
    )
    baseline_full = _size(_shared_context(_baseline_state(), context_keys=("bonds", "macro")))
    drop = (baseline_full - delta_analyst) / baseline_full
    assert drop >= 0.30, f"analyst diet only cut {drop:.1%}; expected >= 30%"


def test_delta_snapshot_history_collapsed_to_bias_row() -> None:
    # Delta run: the full 5-snapshot ``last_snapshots`` list is gone, replaced by
    # a single compact bias row + the changed-segment slugs.
    shared = _shared_context(_delta_state())
    prior = shared["prior_context"]
    assert "last_snapshots" not in prior
    assert prior["bias_row"]["macro_regime"] == "late-cycle expansion"
    assert prior["bias_row"]["equity_bias"] == "constructive"
    # Fat fields never make it into the slim bias row.
    assert "segment_summaries" not in prior["bias_row"]
    assert "risk_radar" not in prior["bias_row"]
    # Changed segments come from the triage decisions (regenerate only).
    assert prior["changed_segments"] == ["bonds"]


def test_baseline_keeps_full_snapshot_history() -> None:
    # Baseline run: the diet is OFF — the full snapshot history is preserved so
    # the weekly baseline can review the whole prior week.
    shared = _shared_context(_baseline_state())
    prior = shared["prior_context"]
    assert "bias_row" not in prior
    assert len(prior["last_snapshots"]) == 5


def test_slim_snapshots_can_be_forced_off_on_delta() -> None:
    # The auto-on is overridable: a delta caller that genuinely needs the full
    # history (e.g. an evolution post-mortem) can force it back on.
    shared = _shared_context(_delta_state(), slim_snapshots=False)
    assert len(shared["prior_context"]["last_snapshots"]) == 5
    assert "bias_row" not in shared["prior_context"]


# --- per-phase data_layer allowlist ------------------------------------------


def test_full_scope_keeps_entire_market_context() -> None:
    shared = _shared_context(_baseline_state(), data_layer_scope="full")
    mc = shared["data_layer"]["market_context"]
    assert set(mc["price_technicals"]) == set(_ETFS)
    assert set(mc["macro_series"]) == set(_MACRO_SERIES)


def test_analyst_ticker_scope_drops_full_segment_dumps() -> None:
    # The analyst (ticker scope) must NOT receive the run-wide per-ticker ETF
    # dump or the bulk macro series — it fetches its own ticker's data via tools.
    # Only the compact regime signals remain.
    shared = _shared_context(_baseline_state(), data_layer_scope="ticker")
    mc = shared["data_layer"]["market_context"]
    assert "price_technicals" not in mc
    assert "macro_series" not in mc
    assert "fed_odds" in mc and "onchain_positioning" in mc
    # Freshness probes (scalars) are always preserved.
    assert shared["data_layer"]["price_technicals_ticker_count"] == len(_ETFS)
    assert shared["data_layer"]["fallback_used"] == "supabase"


def test_pm_portfolio_scope_keeps_macro_drops_ticker_dump() -> None:
    # The PM (portfolio scope) reads the book + prices via tools, so the per-ticker
    # ETF dump is dropped — but macro context + regime signals are retained for
    # the allocation decision.
    shared = _shared_context(_baseline_state(), data_layer_scope="portfolio")
    mc = shared["data_layer"]["market_context"]
    assert "price_technicals" not in mc
    assert set(mc["macro_series"]) == set(_MACRO_SERIES)
    assert "fed_odds" in mc


def test_none_scope_drops_market_context_entirely() -> None:
    shared = _shared_context(_baseline_state(), data_layer_scope="none")
    assert shared["data_layer"]["market_context"] == {}
    # Freshness scalars still present.
    assert shared["data_layer"]["price_technicals_ticker_count"] == len(_ETFS)


def test_scoped_data_layer_does_not_mutate_input() -> None:
    # _scoped_data_layer must be purely functional — the source dict (a fresh
    # model_dump) is reused across the run; mutation would corrupt later phases.
    src = _data_layer().model_dump(mode="json")
    before = json.dumps(src, default=str, sort_keys=True)
    _scoped_data_layer(src, "ticker")
    _scoped_data_layer(src, "portfolio")
    assert json.dumps(src, default=str, sort_keys=True) == before


def test_analyst_scope_strictly_smaller_than_full() -> None:
    full = _size(_shared_context(_baseline_state(), data_layer_scope="full"))
    ticker = _size(_shared_context(_baseline_state(), data_layer_scope="ticker"))
    portfolio = _size(_shared_context(_baseline_state(), data_layer_scope="portfolio"))
    assert ticker < portfolio < full


# --- source provenance & date injection (#949) --------------------------------


def _segment_with_sources(key: str) -> dict[str, Any]:
    """A segment row whose payload contains sources with title + url —
    the provenance the delta diet must preserve (#949)."""
    return {
        "date": "2026-06-18",
        "document_key": key,
        "doc_type": None,
        "payload": {
            "segment": key,
            "date": "2026-06-18",
            "bias": "neutral",
            "headline": "Test headline for " + key,
            "material_findings": [
                {
                    "summary": "Finding one",
                    "source_ids": ["src-1", "src-2"],
                },
            ],
            "sources": [
                {
                    "id": "src-1",
                    "title": "Reuters: Bond market update",
                    "url": "https://reuters.com/bonds",
                },
                {
                    "id": "src-2",
                    "title": "FRED: DGS10 series",
                    "url": "https://fred.stlouisfed.org/series/DGS10",
                },
                {"id": "src-3", "title": None, "url": None},  # edge case: already null
            ],
            "notes": "x" * 500,  # fat field the diet may trim
        },
    }


def _delta_state_with_sources() -> AtlasResearchState:
    """Delta state whose ``latest_segments`` payloads carry real sources."""
    snaps = [
        _full_snapshot("2026-06-18", "delta"),
        _full_snapshot("2026-06-17", "delta"),
    ]
    segments = {key: _segment_with_sources(key) for key in ("macro", "bonds", "equity")}
    return AtlasResearchState(
        run_type="delta",
        run_date=RUN_DATE,
        baseline_date=BASELINE_DATE,
        prior_context=PriorContext(last_snapshots=snaps, latest_segments=segments),
        data_layer=_data_layer(),
        triage=DeltaTriageResult(
            evaluated_at=RUN_DATE,
            baseline_date=BASELINE_DATE,
            decisions=[
                DeltaTriageDecision(
                    segment="bonds", decision="regenerate", reason="moved", tier="high"
                ),
            ],
        ),
    )


def test_delta_diet_preserves_source_titles() -> None:
    """After the delta diet, every source in ``latest_segments`` payloads must
    retain its ``title`` (and ``url`` where non-null). Regression test for #949:
    the #935 diet nulled source titles leaving only ``id``."""
    shared = _shared_context(_delta_state_with_sources(), context_keys=("bonds", "macro"))
    for key in ("bonds", "macro"):
        seg = shared["prior_context"]["latest_segments"][key]
        sources = seg["payload"]["sources"]
        for src in sources:
            # id is always present
            assert "id" in src, f"source in {key} missing id"
            # title must survive the diet (not be stripped to null)
            if src["id"] in ("src-1", "src-2"):
                assert src["title"] is not None, (
                    f"source {src['id']} in {key} lost title — "
                    f"diet must preserve source provenance (#949)"
                )
                assert src["url"] is not None, (
                    f"source {src['id']} in {key} lost url — "
                    f"diet must preserve source provenance (#949)"
                )


def test_delta_diet_preserves_source_urls() -> None:
    """Source ``url`` must survive the diet — not just ``id`` (#949)."""
    shared = _shared_context(_delta_state_with_sources(), context_keys=("bonds",))
    sources = shared["prior_context"]["latest_segments"]["bonds"]["payload"]["sources"]
    src_1 = next(s for s in sources if s["id"] == "src-1")
    assert src_1["url"] == "https://reuters.com/bonds"
    src_2 = next(s for s in sources if s["id"] == "src-2")
    assert src_2["url"] == "https://fred.stlouisfed.org/series/DGS10"


def test_delta_bias_row_date_is_prior_not_run_date() -> None:
    """The ``bias_row`` carries the *prior* snapshot's date, clearly labeled as
    ``prior_date`` — not bare ``date`` which the model confuses for the analysis
    date (#949). The top-level ``run_date`` is the authoritative analysis date."""
    shared = _shared_context(_delta_state_with_sources())
    bias = shared["prior_context"]["bias_row"]
    # The bias row must NOT carry a bare "date" key — that's what made the model
    # set payload.date to the prior day instead of run_date.
    assert "date" not in bias, (
        "bias_row must not carry bare 'date' — rename to 'prior_date' so the "
        "model does not confuse it for the analysis date (#949)"
    )
    # Instead, the prior snapshot's date is under ``prior_date``.
    assert bias.get("prior_date") == "2026-06-18"
    # The top-level run_date is the authoritative analysis date.
    assert shared["run_date"] == RUN_DATE.isoformat()


def test_shared_context_run_date_always_equals_state_run_date() -> None:
    """``shared_context.run_date`` must always equal ``state.run_date`` — the
    authoritative analysis date the model should use (#949)."""
    state = _delta_state_with_sources()
    shared = _shared_context(state)
    assert shared["run_date"] == state.run_date.isoformat()
