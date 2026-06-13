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
    # Phase 7C 4-axis specialists
    "SpecialistPayload": _specialist_body(),
    # Phase 7C-D bull/bear debate
    "DebateRoundContribution": _debate_round_body(),
    "DebateSummary": _debate_summary_body(),
    # Phase 7D risk debate
    "RiskCase": {"case": "synthetic risk case"},
    "RiskDebateSummary": {
        "aggressive_case": "synthetic aggressive",
        "conservative_case": "synthetic conservative",
        "key_tension": "synthetic tension",
    },
    # Phase 7D PM
    "RebalanceDecision": {
        "recommended_portfolio": [],
        "actions": [],
        "notes": "synthetic rebalance",
    },
    # Phase 9
    "Phase9Artifacts": _phase9_body(),
    # #432 reflector skill — separate from Phase 9 artifacts.
    "DecisionReflection": {"reflection": "synthetic reflection"},
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
) -> FakeSupabaseClient:
    """Return a ``FakeSupabaseClient`` with default seed rows.

    ``canned_extras`` is merged on top of the defaults — supply additional
    rows for the tables your test cares about. Replacing the seed entirely
    is intentional: build your own canned dict and pass it directly.
    """
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
    materialize_deps: Any = None

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
            materialize=self.materialize_deps,
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
        atlas_input.run_type,
        deps=atlas_deps_no_publish,
        watchlist=atlas_input.watchlist,
    )
    state = atlas_graph.invoke(state)
    if atlas_input.run_type == "monthly":
        return state

    from digiquant.olympus.hermes.graph import build_hermes_graph

    hermes_graph = build_hermes_graph(watchlist=list(atlas_input.watchlist), deps=chain_deps.hermes)
    state = hermes_graph.invoke(state)

    if chain_deps.publish is not None:
        publish_only = [build_publish_phase(chain_deps.publish)]
        publish_graph = build_pipeline(AtlasResearchState, publish_only)
        state = publish_graph.invoke(state)

    # Phase 9D materialization — keep this faithful to run_atlas_then_hermes (#700).
    if chain_deps.materialize is not None:
        from digiquant.olympus.hermes.portfolio_materialize import build_materialize_phase

        materialize_only = [build_materialize_phase(chain_deps.materialize)]
        state = build_pipeline(AtlasResearchState, materialize_only).invoke(state)
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
    materialize: bool = True,
    preferences: dict[str, Any] | None = None,
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
    publish, triage, phase9, preflight_reflect
        Whether to wire the optional dep slots. Default behavior matches a
        legacy graph (publish + triage on; phase9 + reflect off — those
        require migrations 026/027).
    preferences
        Merged into ``AtlasConfigBundle.preferences`` so tests can flip
        ``debate_rounds``, ``holding_days``, etc.
    """
    client = seed_supabase_client(canned_extras=canned_extras)
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
    from digiquant.olympus.hermes.graph import HermesGraphDeps

    hermes_deps = HermesGraphDeps(
        phase9=Phase9Deps(client=client) if phase9 else None,
    )
    publish_deps = PublishDeps(client=client) if publish else None
    from digiquant.olympus.hermes.portfolio_materialize import MaterializeDeps

    materialize_deps = MaterializeDeps(client=client) if materialize else None
    config_bundle = AtlasConfigBundle(
        watchlist=watchlist_list,
        preferences=preferences_dict,
    )

    fake_chat = simulate_chat_completion(overrides=overrides)

    with patch(
        "digigraph.graph.research_agent.completion_text",
        side_effect=fake_chat,
    ):
        yield SimulationRun(
            client=client,
            deps=deps,
            config_bundle=config_bundle,
            hermes_deps=hermes_deps,
            publish_deps=publish_deps,
            materialize_deps=materialize_deps,
        )
