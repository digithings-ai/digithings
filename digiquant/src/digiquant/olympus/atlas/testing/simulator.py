"""Deterministic Atlas pipeline simulator (no live LLM, no live Supabase).

The simulator solves a concrete pain point: every full Atlas run hits LLM
endpoints 30+ times. Repeated end-to-end tests that exercise the
orchestration logic — phase wiring, state reducers, publish routing,
triage, delta carry-forward — should not pay that cost. They should
also not hit the real Supabase project.

What this module provides:

1. ``simulate_chat_completion(overrides=None)`` — a callable matching
   ``digigraph.graph.research_agent.completion_text``'s signature that
   inspects the prompt's ``OUTPUT_SCHEMA (name: <ClassName>)`` block,
   looks up the schema name in ``DEFAULT_RESPONSES``, and returns a
   minimum-valid JSON payload. Per-test ``overrides`` win over the
   defaults and accept either a dict (used for every call to that
   schema) or a callable taking ``(messages, kwargs)`` for dynamic
   responses.

2. ``seed_supabase_client(...)`` — returns a ``FakeSupabaseClient``
   pre-loaded with the minimum rows the pipeline reads on a routine
   run: ``daily_snapshots`` (one prior baseline), ``documents`` (one
   prior per-segment doc), ``price_technicals`` (recent freshness
   probe rows), ``price_history`` (D-1 / D-2 close pairs for the
   triage signal), and ``trading_calendar`` (a few NYSE entries). The
   seed surface is intentionally narrow — tests that need richer state
   pass extra rows via ``canned_extras``.

3. ``simulated_pipeline(...)`` — context manager that patches
   ``chat_completion`` for the duration, builds an
   ``AtlasGraphDeps`` with the fake client wired through every seam
   (preflight, triage, publish, phase 9, preflight-reflect), and
   yields a ``SimulationRun`` with helpers for invoking the compiled
   graph and inspecting both the final state and the captured Supabase
   writes.

Hard constraints honored:
- Imports nothing from the real ``supabase`` Python client.
- No file I/O, no network. ``ATLAS_MAX_ANALYSTS`` is honored when set
  (phase 7C / 7C-D / debate caps respect it as in production).
- Every default response is the smallest valid Pydantic body; tests
  that care about specific values supply ``overrides``.

Read the unit tests in ``tests/test_pipeline_simulation.py`` for the
canonical usage shape.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Iterator, TypedDict
from unittest.mock import patch

from digiquant.olympus.atlas.graph import (
    AtlasGraphDeps,
    AtlasInput,
    build_atlas_graph,
    initial_state,
)
from digiquant.olympus.hermes.phases.phase9_evolution import Phase9Deps
from digiquant.olympus.atlas.phases.preflight import PreflightDeps, PreflightReflectDeps
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Phase7DigestPayload,
    Phase9EvolutionPayload,
    RebalancePayload,
    RiskDebatePayload,
)

# Re-use the existing fake client + query implementation from the
# unit-test suite. Importing from a tests module is unusual, but the
# fake is the same shape every test in the project already depends on
# and duplicating it here would be drift-prone.
from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

# Gate thresholds (spec §12.2 / §16 test_quiet_day) — re-baseline when graph changes.
# 2026-06-20 re-baseline: mandatory δ DocumentPatches (3) + phase5 sector bypass
# (11× SectorReport until #929 triage wiring) + digest + Hermes thesis track + held H5.
QUIET_DAY_LLM_BUDGET = 22
QUIET_DAY_MIN_PATCH_RATIO = 0.10
PATCH_OUTPUT_SCHEMAS = frozenset({"DocumentPatch"})


@dataclass(frozen=True)
class LlmCallTelemetry:
    """Aggregated LLM call stats captured by ``simulated_pipeline``."""

    total_calls: int
    by_schema: dict[str, int]
    patch_calls: int

    @property
    def patch_ratio(self) -> float:
        if self.total_calls == 0:
            return 0.0
        return self.patch_calls / self.total_calls

    def assert_quiet_day_budget(self, *, max_calls: int = QUIET_DAY_LLM_BUDGET) -> None:
        if self.total_calls > max_calls:
            msg = (
                f"quiet-day LLM budget exceeded: {self.total_calls} > {max_calls}; "
                f"by_schema={self.by_schema}"
            )
            raise AssertionError(msg)


def llm_telemetry_from_calls(
    captured_calls: list[tuple[str, dict[str, Any]]],
) -> LlmCallTelemetry:
    """Summarize schema-keyed LLM invocations from ``SimulationRun.captured_calls``."""
    by_schema: dict[str, int] = {}
    for schema, _meta in captured_calls:
        by_schema[schema] = by_schema.get(schema, 0) + 1
    patch_calls = sum(by_schema.get(schema, 0) for schema in PATCH_OUTPUT_SCHEMAS)
    total = sum(by_schema.values())
    return LlmCallTelemetry(total_calls=total, by_schema=by_schema, patch_calls=patch_calls)


def client_store_to_canned_extras(client: FakeSupabaseClient) -> dict[str, list[Any]]:
    """Convert a fake client's published rows into ``canned_extras`` for the next run."""
    return {table: list(rows) for table, rows in client.store.items()}


class SegmentFixtureBody(TypedDict, total=False):
    """Minimum-valid segment report body for simulator defaults (SIMP-033)."""

    segment: str
    date: str
    bias: str
    headline: str
    material_findings: list[str]
    sources: list[str]
    notes: str
    growth: str
    inflation: str
    policy: str
    risk_appetite: str
    regime_label: str
    portfolio_implications: str


class DigestFixtureBody(SegmentFixtureBody, Phase7DigestPayload, total=False):
    """Minimum-valid digest payload for simulator defaults (SIMP-033)."""


class DebateRoundFixture(TypedDict, total=False):
    """Phase 7C-D ``DebateRoundContribution`` simulator body (SIMP-033)."""

    role: str
    ticker: str
    round_number: int
    argument: str


class DebateSummaryFixture(TypedDict, total=False):
    """Phase 7C-D ``DebateSummary`` simulator body (SIMP-033)."""

    ticker: str
    rounds: list[Any]
    bull_thesis: str
    bear_thesis: str
    net_stance: str
    conviction_delta: int


class RiskCaseFixture(TypedDict, total=False):
    """Phase 7D ``RiskCase`` simulator body (SIMP-033)."""

    case: str


class DecisionReflectionFixture(TypedDict, total=False):
    """Preflight reflector ``DecisionReflection`` simulator body (SIMP-033)."""

    reflection: str


class CannedSnapshotRow(TypedDict, total=False):
    """``daily_snapshots`` seed row for ``seed_supabase_client`` (SIMP-033)."""

    date: str
    run_type: str
    baseline_date: str | None
    snapshot: Phase7DigestPayload


class CannedPriceHistoryRow(TypedDict, total=False):
    """``price_history`` seed row for triage / alpha probes (SIMP-033)."""

    date: str
    ticker: str
    close: float


class CannedPriceTechnicalRow(TypedDict, total=False):
    """``price_technicals`` freshness seed row (SIMP-033)."""

    date: str
    ticker: str


class CannedTradingCalendarRow(TypedDict, total=False):
    """``trading_calendar`` seed row (SIMP-033)."""

    date: str
    venue: str
    is_trading_day: bool


class SpecialistFixtureBody(TypedDict, total=False):
    """Phase 7C ``SpecialistPayload`` simulator body (SIMP-033)."""

    axis: str
    ticker: str
    conviction_axis: float
    stance_axis: str
    rationale: str
    sources: list[str]


FixtureResponse = (
    SegmentFixtureBody
    | DigestFixtureBody
    | SpecialistFixtureBody
    | DebateRoundFixture
    | DebateSummaryFixture
    | RiskDebatePayload
    | RebalancePayload
    | Phase9EvolutionPayload
    | RiskCaseFixture
    | DecisionReflectionFixture
)


# ──────────────────────────────────────────────────────────────────────────
# 1. Default responses keyed by output schema name
# ──────────────────────────────────────────────────────────────────────────
# Phase 1-5 segment reports all extend SegmentReport, so a single
# ``_segment`` template covers the lot; specific schemas with required
# extra fields get their own builder below.

_TODAY = "2026-04-26"


def _segment(slug: str, headline: str = "synthetic finding") -> SegmentFixtureBody:
    """Minimum valid SegmentReport body for a given segment slug."""
    return {
        "segment": slug,
        "date": _TODAY,
        "bias": "neutral",
        "headline": headline,
        "material_findings": [],
        "sources": [],
        "notes": "",
    }


def _digest_body() -> DigestFixtureBody:
    """DigestSnapshot extends SegmentReport with required summary strings."""
    return {
        **_segment("master-digest", headline="synthetic regime"),
        "market_regime_snapshot": "synthetic",
        "alt_data_dashboard": "synthetic",
        "institutional_summary": "synthetic",
        "asset_classes_summary": "synthetic",
        "us_equities_summary": "synthetic",
        "thesis_tracker": "",
        "portfolio_recommendations": "",
        "actionable_summary": [],
        "risk_radar": [],
        "segment_freshness": {},
    }


def _phase9_body() -> Phase9EvolutionPayload:
    return {
        "sources": {"scored": [], "discoveries": []},
        "quality": {
            "predictions_checked": [],
            "rubric": {
                "accuracy": 3,
                "completeness": 3,
                "actionability": 3,
                "conciseness": 3,
                "source_quality": 3,
            },
        },
        "proposals": {"proposals": []},
    }


def _specialist_body(axis: str = "technical", ticker: str = "AAPL") -> SpecialistFixtureBody:
    return {
        "axis": axis,
        "ticker": ticker,
        "conviction_axis": 0.6,
        "stance_axis": "buy",
        "rationale": f"synthetic {axis} rationale for {ticker}",
        "sources": [],
    }


def _debate_round_body(role: str = "bull", ticker: str = "AAPL") -> DebateRoundFixture:
    return {
        "role": role,
        "ticker": ticker,
        "round_number": 1,
        "argument": f"synthetic {role} argument for {ticker}",
    }


def _debate_summary_body(ticker: str = "AAPL") -> DebateSummaryFixture:
    return {
        "ticker": ticker,
        "rounds": [],
        "bull_thesis": "synthetic bull synthesis",
        "bear_thesis": "synthetic bear synthesis",
        "net_stance": "neutral",
        "conviction_delta": 0,
    }


# Schemas that don't need per-call customization use a single canned dict.
# Callers who do need it (per-ticker specialists / debaters) supply
# ``overrides`` callables.
DEFAULT_RESPONSES: dict[str, FixtureResponse] = {
    # Phase 1
    "SentimentNewsReport": _segment("alt-sentiment-news"),
    "CtaPositioningReport": _segment("alt-cta-positioning"),
    "OptionsDerivativesReport": _segment("alt-options-derivatives"),
    "PoliticianSignalsReport": _segment("alt-politician-signals"),
    "AiPortfoliosReport": _segment("alt-ai-portfolios"),
    "OnchainCohortPositioningReport": _segment("alt-onchain-positioning"),
    # Phase 2
    "InstitutionalFlowsReport": _segment("inst-institutional-flows"),
    "HedgeFundIntelReport": _segment("inst-hedge-fund-intel"),
    # Phase 3 — narrow Literal fields per phase3_macro.py.
    "MacroRegimeReport": {
        **_segment("macro", headline="synthetic regime"),
        "growth": "slowing",
        "inflation": "cooling",
        "policy": "neutral",
        "risk_appetite": "mixed",
        "regime_label": "Synthetic / Mixed / Neutral / Mixed",
        "portfolio_implications": "",
    },
    # Phase 4 — every asset class shares the SegmentReport core; phase4
    # extras are all optional.
    "BondsReport": _segment("bonds"),
    "CommoditiesReport": _segment("commodities"),
    "ForexReport": _segment("forex"),
    "CryptoReport": _segment("crypto"),
    "InternationalReport": _segment("international"),
    # Phase 5
    "EquityOverviewReport": _segment("equity"),
    "SectorReport": _segment("sector"),
    # Phase 7
    "DigestSnapshot": _digest_body(),
    "MonthlyDigest": _digest_body(),
    # H5 unified analyst
    "AnalystPayload": {
        "ticker": "AAPL",
        "conviction_score": 2,
        "stance": "buy",
        "thesis": "synthetic unified thesis",
        "risks": "synthetic risks",
        "sources": [],
        "fundamentals": "",
        "technicals": "",
        "headwinds": [],
        "tailwinds": [],
        "bull_case": "synthetic bull",
        "bear_case": "synthetic bear",
        "price_targets": None,
        "expectations": "",
        "fingerprint_news_hash": "",
    },
    # H6 deliberation
    "DeliberationPmTurn": {
        "converged": True,
        "challenge": "",
        "accepts_analyst_position": True,
        "open_questions": [],
        "conclusion": "synthetic deliberation conclusion",
        "net_stance": "neutral",
        "conviction_delta": 0,
    },
    "DeliberationAnalystTurn": {
        "converged": True,
        "response": "synthetic analyst response",
        "revises_payload": False,
        "conclusion": "synthetic analyst conclusion",
        "net_stance": "neutral",
        "conviction_delta": 0,
    },
    # Legacy 7C-D fixtures (simulator compat for overrides)
    "SpecialistPayload": _specialist_body(),
    "DebateRoundContribution": _debate_round_body(),
    "DebateSummary": _debate_summary_body(),
    # Phase 7D risk debate
    "RiskCase": {"case": "synthetic risk case"},
    "RiskDebateSummary": {
        "aggressive_case": "synthetic aggressive",
        "conservative_case": "synthetic conservative",
        "key_tension": "synthetic tension",
    },
    # H7 PM direction (no weights)
    "PMDirectionMemo": {
        "schema_version": "1.0",
        "date": "2026-04-26",
        "roster": [{"ticker": "AAPL", "direction": "long", "conviction_rank": 1, "narrative": ""}],
        "memo": "synthetic direction memo",
    },
    "RebalanceDecision": {
        "recommended_portfolio": [],
        "actions": [],
        "notes": "synthetic rebalance",
    },
    # Phase 9
    "Phase9Artifacts": _phase9_body(),
    # #432 reflector skill — separate from Phase 9 artifacts.
    "DecisionReflection": {"reflection": "synthetic reflection"},
    # Edit-mode continuity (#930) — digest/segment patch calls in simulator.
    "DocumentPatch": {
        "schema_version": "1.0",
        "doc_type": "document_delta",
        "date": "2026-04-26",
        "prior_date": "2026-04-25",
        "target_document_key": "digest",
        "status": "skipped",
        "skip_reason": "simulator_default",
        "ops": [],
    },
    # Hermes thesis track (H1–H3)
    "ThesisReviewOutput": {
        "reviewed_theses": [],
        "new_candidate_theses": [],
        "notes": "synthetic thesis review",
    },
    "MarketThesisExplorationOutput": {
        "executive_digest_pointer": "digest",
        "deeper_dives": [],
        "theses": [],
    },
    "ThesisVehicleMapOutput": {
        "mappings": [],
    },
}


# Stable onchain injection for quiet-day triage carry (see test_triage_alt_nodes).
QUIET_ONCHAIN_INJECTION: dict[str, Any] = {
    "overall_divergence": 0.12,
    "smart_net_bias": 0.61,
    "crowd_net_bias": 0.49,
    "snapshot_ts": "2026-04-26T00:00:00Z",
    "total_traders": 1234,
    "top_divergent_markets": [
        {"market": "BTC", "divergence": 0.31, "smart_bias": 0.7, "crowd_bias": 0.39},
    ],
}


def _append_quiet_price_history(
    price_history: list[CannedPriceHistoryRow],
    *,
    ticker: str,
    prior_date: str,
    two_days_ago: str,
    run_date: str,
    base: float = 100.0,
) -> None:
    """Append D-2 / D-1 / D closes with sub-threshold moves for triage carry."""
    price_history.extend(
        [
            CannedPriceHistoryRow(date=two_days_ago, ticker=ticker, close=base),
            CannedPriceHistoryRow(date=prior_date, ticker=ticker, close=base * 1.001),
            CannedPriceHistoryRow(date=run_date, ticker=ticker, close=base * 1.002),
        ]
    )


def _quiet_bias_by_segment() -> dict[str, str]:
    from digiquant.olympus.atlas.sectors_config import load_sectors

    slugs = [
        "alt-sentiment-news",
        "alt-cta-positioning",
        "alt-options-derivatives",
        "alt-politician-signals",
        "alt-onchain-positioning",
        "alt-ai-portfolios",
        "inst-institutional-flows",
        "inst-hedge-fund-intel",
        "macro",
        "bonds",
        "commodities",
        "forex",
        "crypto",
        "international",
        "equity",
    ]
    for sector in load_sectors():
        slugs.append(sector.slug)
    return {slug: "neutral" for slug in slugs}


def build_quiet_day_canned_extras(
    *,
    run_date: date,
    watchlist: tuple[str, ...],
) -> dict[str, list[Any]]:
    """Seed prior artifacts for a quiet δ run (``refresh_scope=none``).

    Supplies neutral per-segment bias, quiet price history, held-book positions,
    and prior analyst rows so triage carries low-tier segments while mandatory
    segments resolve to ``edit`` (``DocumentPatch``) rather than ``full``.
    """
    prior_date = (run_date - timedelta(days=1)).isoformat()
    two_days_ago = (run_date - timedelta(days=2)).isoformat()
    bias_by_segment = _quiet_bias_by_segment()
    prior_snapshot: Phase7DigestPayload = {
        "bias": "neutral",
        "bias_by_segment": bias_by_segment,
        "market_regime_snapshot": "prior quiet",
        "onchain_positioning": QUIET_ONCHAIN_INJECTION,
    }

    documents: list[dict[str, Any]] = []
    for slug in bias_by_segment:
        body: dict[str, Any] = (
            dict(DEFAULT_RESPONSES["MacroRegimeReport"]) if slug == "macro" else _segment(slug)
        )
        documents.append(
            {
                "date": prior_date,
                "document_key": slug,
                "doc_type": "Segment",
                "payload": body,
            }
        )
    documents.append(
        {
            "date": prior_date,
            "document_key": "digest",
            "doc_type": "Daily Digest",
            "payload": _digest_body(),
        }
    )
    documents.append(
        {
            "date": prior_date,
            "document_key": "pm-direction-memo",
            "doc_type": "PM Direction",
            "payload": {"body": dict(DEFAULT_RESPONSES["PMDirectionMemo"])},
        }
    )
    for thesis_key, schema in (
        ("thesis-review", "ThesisReviewOutput"),
        ("market-exploration", "MarketThesisExplorationOutput"),
        ("thesis-vehicle-map", "ThesisVehicleMapOutput"),
    ):
        documents.append(
            {
                "date": prior_date,
                "document_key": thesis_key,
                "doc_type": "Thesis",
                "payload": {"body": dict(DEFAULT_RESPONSES[schema])},
            }
        )

    positions: list[dict[str, Any]] = []
    price_history: list[CannedPriceHistoryRow] = []
    price_technicals: list[CannedPriceTechnicalRow] = []
    for ticker in watchlist:
        documents.append(
            {
                "date": prior_date,
                "document_key": f"analyst/{ticker}",
                "doc_type": "asset_recommendation",
                "payload": {
                    "body": {
                        **DEFAULT_RESPONSES["AnalystPayload"],
                        "ticker": ticker,
                        "stance": "buy",
                        "fingerprint_news_hash": "",
                    }
                },
            }
        )
        documents.append(
            {
                "date": prior_date,
                "document_key": f"deliberation/{ticker}",
                "doc_type": "Deliberation",
                "payload": {
                    "ticker": ticker,
                    "conclusion": "prior deliberation carry",
                    "net_stance": "neutral",
                    "conviction_delta": 0,
                },
            }
        )
        positions.append({"date": prior_date, "ticker": ticker, "weight_pct": 50.0, "shares": 10})
        # Held names are quiet: prior_date close == two_days_ago close (0% delta).
        # query_price_deltas reads strictly before run_date (``.lt(date, run_date)``),
        # so the run_date 102.0 close is invisible to the staleness gate — it only
        # affects the NAV calc. Delta 0.0 < 0.5% threshold → gated out of H5 and
        # carried, not re-analyzed (Stage 1b held gate, #1030).
        price_history.extend(
            [
                CannedPriceHistoryRow(date=two_days_ago, ticker=ticker, close=100.0),
                CannedPriceHistoryRow(date=prior_date, ticker=ticker, close=100.0),
                CannedPriceHistoryRow(date=run_date.isoformat(), ticker=ticker, close=102.0),
            ]
        )
        price_technicals.append(CannedPriceTechnicalRow(date=prior_date, ticker=ticker))

    from digiquant.olympus.atlas.triage_signals import all_tracked_tickers

    seeded = {row["ticker"] for row in price_history}
    for ticker in all_tracked_tickers():
        if ticker in seeded:
            continue
        _append_quiet_price_history(
            price_history,
            ticker=ticker,
            prior_date=prior_date,
            two_days_ago=two_days_ago,
            run_date=run_date.isoformat(),
            base=50.0 + (hash(ticker) % 100),
        )

    for ticker in ("SPY",):
        if ticker not in seeded:
            _append_quiet_price_history(
                price_history,
                ticker=ticker,
                prior_date=prior_date,
                two_days_ago=two_days_ago,
                run_date=run_date.isoformat(),
                base=400.0,
            )

    return {
        "daily_snapshots": [
            CannedSnapshotRow(
                date=prior_date,
                run_type="delta",
                baseline_date=two_days_ago,
                snapshot=prior_snapshot,
            )
        ],
        "documents": documents,
        "positions": positions,
        "nav_history": [{"date": prior_date, "nav": 100_000.0, "cash_pct": 50, "invested_pct": 50}],
        "price_history": price_history,
        "price_technicals": price_technicals,
        "macro_series_observations": [{"obs_date": prior_date}],
        "trading_calendar": [
            CannedTradingCalendarRow(date=prior_date, venue="NYSE", is_trading_day=True),
            CannedTradingCalendarRow(date=run_date.isoformat(), venue="NYSE", is_trading_day=True),
        ],
    }


# ──────────────────────────────────────────────────────────────────────────
# 2. Prompt parsing + chat_completion mock
# ──────────────────────────────────────────────────────────────────────────


_SCHEMA_NAME_RE = re.compile(r"OUTPUT_SCHEMA \(name: (\w+)\)")
_PHASE_INPUTS_RE = re.compile(r"PHASE_INPUTS[^:]*:\s*(\{.*\})", re.DOTALL)


def parse_schema_name(messages: list[dict[str, Any]]) -> str | None:
    """Extract the output-schema name from a prompt's OUTPUT_SCHEMA chunk.

    Returns ``None`` if the chunk is missing — callers should treat that
    as a wiring bug (every Atlas LLM call goes through ``run_research_agent``
    which always includes the chunk).
    """
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text", "")
            m = _SCHEMA_NAME_RE.search(text)
            if m:
                return m.group(1)
    return None


def parse_phase_inputs(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract the parsed PHASE_INPUTS body from a prompt.

    Returns an empty dict if the chunk is missing or unparseable. Used
    by override callables that want to specialize the response based on
    e.g. the per-ticker ``ticker`` field.
    """
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            text = part.get("text", "")
            m = _PHASE_INPUTS_RE.search(text)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    return {}
    return {}


OverrideValue = FixtureResponse | Callable[[list[dict[str, Any]], dict[str, Any]], Any]


def simulate_chat_completion(
    overrides: dict[str, OverrideValue] | None = None,
    *,
    captured_calls: list[tuple[str, dict[str, Any]]] | None = None,
) -> Callable[..., str]:
    """Build a ``chat_completion``-shaped callable with deterministic outputs.

    The returned function dispatches on the ``OUTPUT_SCHEMA`` name in the
    prompt:

    1. If ``overrides[schema_name]`` is set, use it.
       - dict → returned verbatim (after JSON-encoding).
       - callable → invoked as ``fn(messages, kwargs)``; return value is
         the response. If the callable returns a dict, the simulator
         JSON-encodes it; if it returns a string, the simulator emits
         it raw.
    2. Otherwise look up ``DEFAULT_RESPONSES[schema_name]`` and JSON-encode.
    3. If the schema isn't in either table, raise ``KeyError`` so the
       test author sees a useful error instead of cryptic Pydantic
       validation failures downstream.

    The dispatcher also fills in per-call fields for schemas that need
    per-ticker / per-axis customization (e.g. SpecialistPayload picks up
    ``axis`` + ``ticker`` from PHASE_INPUTS so the ticker round-trips
    through the assertion).
    """
    overrides = overrides or {}

    def _emit(payload: Any) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload)

    def _per_call_default(schema: str, inputs: dict[str, Any]) -> FixtureResponse:
        """Per-call dynamic defaults — ticker / axis / role round-tripped."""
        if schema == "AnalystPayload":
            return {
                **DEFAULT_RESPONSES["AnalystPayload"],
                "ticker": str(inputs.get("ticker", "AAPL")),
            }
        if schema == "DeliberationPmTurn":
            return DEFAULT_RESPONSES["DeliberationPmTurn"]
        if schema == "DeliberationAnalystTurn":
            return DEFAULT_RESPONSES["DeliberationAnalystTurn"]
        if schema == "SpecialistPayload":
            return _specialist_body(
                axis=str(inputs.get("axis", "technical")),
                ticker=str(inputs.get("ticker", "AAPL")),
            )
        if schema == "DebateRoundContribution":
            return _debate_round_body(
                role=str(inputs.get("role", "bull")),
                ticker=str(inputs.get("ticker", "AAPL")),
            )
        if schema == "DebateSummary":
            return _debate_summary_body(ticker=str(inputs.get("ticker", "AAPL")))
        if schema == "PMDirectionMemo":
            roster = inputs.get("focus_roster") or ["AAPL"]
            return {
                **DEFAULT_RESPONSES["PMDirectionMemo"],
                "roster": [
                    {
                        "ticker": str(ticker),
                        "direction": "long",
                        "conviction_rank": idx + 1,
                        "narrative": "",
                    }
                    for idx, ticker in enumerate(roster)
                ],
            }
        return DEFAULT_RESPONSES[schema]

    def chat_completion(*args: Any, **kwargs: Any) -> str:
        # Signature: chat_completion(model, messages, **kwargs). Tolerate
        # both positional and keyword forms; the agent calls this many
        # different ways across phases.
        messages = kwargs.get("messages")
        if messages is None and len(args) >= 2:
            messages = args[1]
        messages = messages or []

        schema = parse_schema_name(messages)
        if schema is None:
            raise RuntimeError(
                "simulate_chat_completion: no OUTPUT_SCHEMA in prompt — "
                "is the caller bypassing run_research_agent?"
            )

        if captured_calls is not None:
            inputs = parse_phase_inputs(messages)
            captured_calls.append((schema, {"phase_inputs": inputs}))
        else:
            inputs = parse_phase_inputs(messages)

        if schema in overrides:
            override = overrides[schema]
            if callable(override):
                return _emit(override(messages, kwargs))
            return _emit(override)

        if schema not in DEFAULT_RESPONSES:
            raise KeyError(
                f"simulate_chat_completion: no default response for schema {schema!r}; "
                f"add it to DEFAULT_RESPONSES or pass an override."
            )

        return _emit(_per_call_default(schema, inputs))

    return chat_completion


# ──────────────────────────────────────────────────────────────────────────
# 3. Seeded fake Supabase client
# ──────────────────────────────────────────────────────────────────────────


def _default_canned() -> dict[str, list[Any]]:
    """Minimum prior state the pipeline reads on a routine baseline run."""
    today = date.fromisoformat(_TODAY)
    yesterday = (today - timedelta(days=1)).isoformat()
    two_days_ago = (today - timedelta(days=2)).isoformat()
    prior_snapshot: Phase7DigestPayload = {"market_regime_snapshot": "prior baseline"}

    return {
        "daily_snapshots": [
            CannedSnapshotRow(
                date=yesterday,
                run_type="baseline",
                baseline_date=None,
                snapshot=prior_snapshot,
            )
        ],
        "documents": [],
        "price_technicals": [
            CannedPriceTechnicalRow(date=yesterday, ticker="AAPL"),
            CannedPriceTechnicalRow(date=yesterday, ticker="MSFT"),
        ],
        "macro_series_observations": [{"obs_date": yesterday}],
        "price_history": [
            CannedPriceHistoryRow(date=two_days_ago, ticker="AAPL", close=100.0),
            CannedPriceHistoryRow(date=yesterday, ticker="AAPL", close=100.5),
            CannedPriceHistoryRow(date=two_days_ago, ticker="MSFT", close=200.0),
            CannedPriceHistoryRow(date=yesterday, ticker="MSFT", close=201.0),
            # Benchmark for #432 alpha computation.
            CannedPriceHistoryRow(date=two_days_ago, ticker="SPY", close=400.0),
            CannedPriceHistoryRow(date=yesterday, ticker="SPY", close=401.0),
        ],
        "trading_calendar": [
            CannedTradingCalendarRow(date=yesterday, venue="NYSE", is_trading_day=True),
            CannedTradingCalendarRow(date=today.isoformat(), venue="NYSE", is_trading_day=True),
        ],
        "decision_log": [],
    }


def seed_supabase_client(
    canned_extras: dict[str, list[Any]] | None = None,
    *,
    replace_defaults: bool = False,
) -> FakeSupabaseClient:
    """Return a ``FakeSupabaseClient`` with default seed rows.

    ``canned_extras`` is merged on top of the defaults — supply additional
    rows for the tables your test cares about. Replacing the seed entirely
    is intentional: build your own canned dict and pass it directly.

    Set ``replace_defaults=True`` when ``canned_extras`` is a complete
    fixture (e.g. :func:`build_quiet_day_canned_extras`) and must not be
    merged with :func:`_default_canned` rows.
    """
    if replace_defaults and canned_extras is not None:
        canned = dict(canned_extras)
    else:
        canned = _default_canned()
        if canned_extras:
            for table, extras in canned_extras.items():
                canned.setdefault(table, [])
                canned[table].extend(extras)
    return FakeSupabaseClient(canned_reads=canned)


# ──────────────────────────────────────────────────────────────────────────
# 4. End-to-end harness
# ──────────────────────────────────────────────────────────────────────────


@dataclass
class SimulationRun:
    """Handle returned from ``simulated_pipeline``.

    Test code typically calls ``invoke()`` once and then asserts against
    the resulting state and the captured Supabase writes (``client.store``).
    """

    client: FakeSupabaseClient
    deps: AtlasGraphDeps
    config_bundle: AtlasConfigBundle = field(default_factory=AtlasConfigBundle)
    captured_calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    # Hermes-side deps + chain publish — populated by ``simulated_pipeline``.
    hermes_deps: Any = None
    publish_deps: Any = None

    def llm_telemetry(self) -> LlmCallTelemetry:
        """Aggregate LLM call budget + patch-ratio telemetry for gate tests."""
        return llm_telemetry_from_calls(self.captured_calls)

    def invoke(self, atlas_input: AtlasInput) -> AtlasResearchState:
        """Run the full Atlas → Hermes chain to completion.

        Returns the final ``AtlasResearchState`` so tests can read every
        ``phaseN_*`` field directly. The fake client's ``store`` carries
        every write; the canned reads carry every prior-context probe.
        """
        from digiquant.olympus.hermes.chain import ChainDeps
        from digiquant.olympus.hermes.graph import HermesGraphDeps

        chain_deps = ChainDeps(
            atlas=self.deps,
            hermes=self.hermes_deps or HermesGraphDeps(),
            publish=self.publish_deps,
        )
        # Re-bind initial_state to thread the test's config_bundle.
        atlas_input_with_state = atlas_input
        result = _invoke_with_config(atlas_input_with_state, chain_deps, self.config_bundle)
        return AtlasResearchState.model_validate(result) if isinstance(result, dict) else result


def _invoke_with_config(
    atlas_input: AtlasInput,
    chain_deps: "ChainDeps",  # noqa: F821 — forward ref keeps simulator import-light
    config_bundle: AtlasConfigBundle,
) -> AtlasResearchState:
    """Invoke ``run_atlas_then_hermes`` while threading a non-default config bundle.

    The chain orchestrator builds state via :func:`initial_state` which
    only consumes ``AtlasInput.watchlist``; tests sometimes need a richer
    bundle (extra preferences, macro_series). Re-derive state here with
    the supplied ``config_bundle`` and run the chain pieces directly.
    """
    from digigraph.graph.pipeline_builder import build_pipeline

    from digiquant.olympus.atlas.graph import AtlasGraphDeps as _AGDeps
    from digiquant.olympus.atlas.phases.publish_phase import build_publish_phase

    atlas_deps_no_publish = _AGDeps(
        preflight=chain_deps.atlas.preflight,
        publish=None,
        triage=chain_deps.atlas.triage,
        preflight_reflect=chain_deps.atlas.preflight_reflect,
    )
    state = initial_state(atlas_input, config=config_bundle)
    atlas_graph = build_atlas_graph(
        deps=atlas_deps_no_publish,
        watchlist=atlas_input.watchlist,
    )
    state = atlas_graph.invoke(state)

    from digiquant.olympus.hermes.graph import build_hermes_graph

    hermes_graph = build_hermes_graph(watchlist=list(atlas_input.watchlist), deps=chain_deps.hermes)
    state = hermes_graph.invoke(state)

    if chain_deps.publish is not None:
        publish_only = [build_publish_phase(chain_deps.publish)]
        publish_graph = build_pipeline(AtlasResearchState, publish_only)
        state = publish_graph.invoke(state)
    return state


@contextmanager
def simulated_pipeline(
    *,
    watchlist: tuple[str, ...] = ("AAPL", "MSFT"),
    overrides: dict[str, OverrideValue] | None = None,
    canned_extras: dict[str, list[Any]] | None = None,
    publish: bool = True,
    triage: bool = True,
    phase9: bool = False,
    preflight_reflect: bool = False,
    commit_run: bool = True,
    preferences: dict[str, Any] | None = None,
    replace_canned_defaults: bool = False,
) -> Iterator[SimulationRun]:
    """Patch chat_completion + thread a fake client through every dep slot.

    Parameters
    ----------
    watchlist
        Tickers in scope. Drives Phase 7C / 7C-D / 7D fan-out width.
    overrides
        Per-schema response overrides (see ``simulate_chat_completion``).
    canned_extras
        Extra rows for the seeded fake client (merged on top of defaults).
    publish, triage, phase9, preflight_reflect, commit_run
        Whether to wire the optional dep slots. Default behavior: publish +
        triage + commit_run on (matches production non-monthly runs, #932);
        phase9 + reflect off (those require migrations 026/027). ``commit_run``
        wires H9 terminal portfolio booking (positions + NAV + brief).
    preferences
        Merged into ``AtlasConfigBundle.preferences`` so tests can flip
        ``debate_rounds``, ``holding_days``, etc.
    """
    client = seed_supabase_client(canned_extras, replace_defaults=replace_canned_defaults)
    watchlist_list = list(watchlist)
    preferences_dict = dict(preferences or {})

    deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(
                watchlist=watchlist_list,
                preferences=preferences_dict,
            ),
        ),
        publish=None,  # chain handles publish at the end via SimulationRun.publish_deps
        triage=TriageDeps(client=client) if triage else None,
        preflight_reflect=(PreflightReflectDeps(client=client) if preflight_reflect else None),
    )
    from digiquant.olympus.hermes.graph import HermesGraphDeps, ThesisGraphDeps
    from digiquant.olympus.hermes.phases.h9_commit_run import CommitRunDeps
    from digiquant.olympus.hermes.phases.phase7e_risk_sizing import RiskSizingDeps

    hermes_deps = HermesGraphDeps(
        phase9=Phase9Deps(client=client) if phase9 else None,
        thesis=ThesisGraphDeps(client=client),
        risk_sizing=RiskSizingDeps(client=client),
        commit_run=CommitRunDeps(client=client) if commit_run else None,
    )
    publish_deps = PublishDeps(client=client) if publish else None
    config_bundle = AtlasConfigBundle(
        watchlist=watchlist_list,
        preferences=preferences_dict,
    )

    run = SimulationRun(
        client=client,
        deps=deps,
        config_bundle=config_bundle,
        hermes_deps=hermes_deps,
        publish_deps=publish_deps,
    )
    fake_chat = simulate_chat_completion(overrides=overrides, captured_calls=run.captured_calls)

    def _simulator_load_skill_edit(slug: str) -> str:
        from digiquant.olympus.atlas.skills import SkillNotFoundError, load_skill_edit

        try:
            return load_skill_edit(slug)
        except SkillNotFoundError:
            return f"Simulator stub edit skill for {slug!r}. Return DocumentPatch JSON only."

    def _simulator_hermes_load_skill_edit(slug: str) -> str:
        from digiquant.olympus.hermes.skills import SkillNotFoundError, load_skill_edit

        try:
            return load_skill_edit(slug)
        except SkillNotFoundError:
            return f"Simulator stub edit skill for {slug!r}. Return DocumentPatch JSON only."

    with (
        patch("digigraph.graph.research_agent.completion_text", side_effect=fake_chat),
        patch(
            "digiquant.olympus.atlas.phases._node_factory.load_skill_edit",
            side_effect=_simulator_load_skill_edit,
        ),
        patch(
            "digiquant.olympus.atlas.phases.phase7_synthesis.load_skill_edit",
            side_effect=_simulator_load_skill_edit,
        ),
        patch(
            "digiquant.olympus.hermes.phases.portfolio_common.load_skill_edit",
            side_effect=_simulator_hermes_load_skill_edit,
        ),
        patch(
            "digiquant.olympus.hermes.phases.thesis_common.load_skill_edit",
            side_effect=_simulator_hermes_load_skill_edit,
        ),
    ):
        yield run
