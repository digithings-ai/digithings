"""Factory for segment phase nodes (shared_context → skill → research agent → slot).

Seams: ``inputs_builder`` (phase_inputs), ``write_adapter`` (state update),
optional ``triage_gate`` / ``state.triage`` carry-forward.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Callable  # noqa: F401 — used for heterogeneous node-update dict shape

from pydantic import BaseModel

from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase

from digiquant.olympus.atlas.phases.fail_soft import run_segment_fail_soft
from digiquant.olympus.atlas.skills import load_skill
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Carried,
    SegmentSlot,
)

logger = logging.getLogger(__name__)


def _data_tools_enabled() -> bool:
    """Master kill-switch for tool grounding (env ATLAS_DATA_TOOLS, default on)."""
    return os.environ.get("ATLAS_DATA_TOOLS", "1").strip().lower() not in ("0", "false", "")


@lru_cache(maxsize=1)
def _atlas_data_client() -> Any:
    """Memoized Supabase client for the data tools.

    Segment nodes don't carry a client, so build one from env the same way the
    MCP tools and preflight do, and cache it so it isn't rebuilt per node.
    """
    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    return build_client(SupabaseConfig.from_env())


def get_data_client() -> Any:
    """Public accessor for the memoized Supabase data client.

    Hermes analyst nodes reuse the same cached client as Atlas segment nodes
    (#713) to pre-fetch per-ticker data, rather than reaching into the private
    ``_atlas_data_client`` directly.
    """
    return _atlas_data_client()


_MACRO_STALE_DAYS_DEFAULT = 7
"""Max age of the freshest ingested FRED observation before we treat the layer
as stale and fire the paid fallback. The freshest series are daily (VIXCLS, DFF,
DGS10), so a healthy daily cron keeps the max obs_date within a normal market
close gap (≤ a long holiday weekend); only a genuinely broken ingestion exceeds
a week. Override via ``ATLAS_MACRO_STALE_DAYS``."""


def _macro_stale_days() -> int:
    raw = os.environ.get("ATLAS_MACRO_STALE_DAYS", "").strip()
    if raw:
        try:
            return max(0, int(raw))
        except ValueError:
            logger.warning(
                "invalid ATLAS_MACRO_STALE_DAYS=%r; using default %d",
                raw,
                _MACRO_STALE_DAYS_DEFAULT,
            )
    return _MACRO_STALE_DAYS_DEFAULT


def _ingested_macro_stale(run_date: Any) -> bool:
    """Is the ingested FRED macro layer stale → should a fallback segment fire paid search?

    Returns ``True`` (→ use the paid fallback) unless the layer is *confirmed
    fresh*: the latest ``macro_series_observations.obs_date`` is within
    ``ATLAS_MACRO_STALE_DAYS`` of ``run_date``. Every failure mode — kill-switch
    off, no client, query error, empty table, unparseable/exotic ``run_date`` —
    fail-soft to ``True`` so a ``live_search_is_fallback`` segment never silently
    loses its grounding (Phase D capability guarantee). Only the confirmed-fresh
    path returns ``False``, which is what lets the paid call be skipped on the
    hot path.
    """
    if not _data_tools_enabled():
        return True
    try:
        client = _atlas_data_client()
    except Exception as exc:  # noqa: BLE001 — any client failure → paid fallback, never crash
        logger.warning("macro freshness probe: client unavailable (%s); paid fallback", exc)
        return True
    try:
        from digiquant.olympus.atlas.supabase_io import query_macro_series_freshness

        latest = query_macro_series_freshness(client=client)
    except Exception as exc:  # noqa: BLE001 — any probe failure → paid fallback
        logger.warning("macro freshness probe failed (%s); paid fallback", exc)
        return True
    if latest is None:
        return True
    # query_macro_series_freshness may hand back a datetime (datetime subclasses
    # date, so supabase_io._parse_date returns it unchanged) — normalize BOTH
    # sides to a pure date, else `date - datetime` would raise here (outside the
    # try blocks) and defeat the fail-soft guarantee.
    if isinstance(latest, datetime):
        latest = latest.date()
    run_d = run_date.date() if isinstance(run_date, datetime) else run_date
    if not isinstance(run_d, date) or not isinstance(latest, date):
        return True
    age = (run_d - latest).days
    stale = age > _macro_stale_days()
    logger.info("macro ingested layer: latest=%s age=%dd stale=%s", latest, age, stale)
    return stale


def build_grounding(
    *,
    use_data_tools: bool,
    live_search: bool,
    run_date: Any,
    model: str | None = None,
    segment: str = "",
    scope: str = "",
    ai_portfolios: bool = False,
    live_search_is_fallback: bool = False,
    data_tool_tables: frozenset[str] | None = None,
) -> tuple[list[dict[str, Any]] | None, Callable[[str, dict[str, Any]], str] | None, dict | None]:
    """Resolve ``(tools, execute_tool, web_grounding)`` for one research call.

    - ``tools`` / ``execute_tool``: the Supabase data tools (function calling).
    - ``web_grounding``: a cited grounding-summary dict to inject into ``phase_inputs`` —
      either an xAI ``web_search`` pre-pass (``live_search``) or an ``x_search`` read of
      the tracked AI-portfolio accounts (``ai_portfolios``). ``None`` if unavailable.

    When ``live_search_is_fallback`` is set, the ``web_search`` pre-pass is treated
    as a *paid fallback*: it fires only when the ingested FRED macro layer is stale
    (see ``_ingested_macro_stale``). On a normal run with fresh ingested data the
    paid call is skipped entirely — the segment grounds on its in-process data
    tools — which is the Phase D cost cut. A stale/broken ingested layer still
    falls through to the paid call, so grounding is never silently dropped.

    Honors the ``ATLAS_DATA_TOOLS`` kill-switch. Shared by ``build_segment_node``
    and the bespoke phase nodes (equity / sectors) so the gating + wiring live in
    one place.
    """
    tools: list[dict[str, Any]] | None = None
    execute_tool: Callable[[str, dict[str, Any]], str] | None = None
    web_grounding: dict | None = None
    if not _data_tools_enabled():
        return tools, execute_tool, web_grounding
    if use_data_tools:
        try:
            from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher

            # Anchor "as of" reads to the run's logical date (not wall-clock) so tool
            # outputs are reproducible + look-ahead-safe for backfills/delta runs.
            execute_tool = build_data_tool_dispatcher(
                _atlas_data_client(), run_date=run_date, allowed_tables=data_tool_tables
            )
            tools = DATA_TOOLS
        except Exception as exc:  # noqa: BLE001 — degrade to tool-less rather than crash the phase
            logger.warning("data tools unavailable (%s); proceeding without them", exc)
            tools = None
            execute_tool = None
    if ai_portfolios and model:
        from digiquant.olympus.atlas.data.ai_portfolios import fetch_ai_portfolio_grounding

        web_grounding = fetch_ai_portfolio_grounding(model=model, run_date=run_date)
    elif live_search and model:
        if live_search_is_fallback and not _ingested_macro_stale(run_date):
            logger.info(
                "%s: ingested macro layer fresh — skipping paid fallback web_search",
                segment or "macro",
            )
        else:
            from digiquant.olympus.atlas.data.web_grounding import fetch_web_grounding

            web_grounding = fetch_web_grounding(
                model=model, segment=segment or "research", run_date=run_date, scope=scope
            )
    return tools, execute_tool, web_grounding


@dataclass(frozen=True)
class SegmentNodeSpec:
    """Config for one segment-running node."""

    segment_slug: str
    """Stable slug written into SegmentPayload.segment and the output dict key."""

    skill_slug: str
    """Path in ``digiquant/src/digiquant/olympus/atlas/skills/<slug>/SKILL.md`` — the 'what to research'."""

    output_model: type[BaseModel]
    """Pydantic class the LLM output must validate against."""

    phase_outputs_field: str
    """AtlasResearchState attribute this node updates (e.g. 'phase1_outputs')."""

    use_data_tools: bool = False
    """Equip the research agent with the Supabase price/macro data tools."""

    live_search: bool = False
    """Enable the web_search grounding pre-pass (curated domains) for this segment."""

    live_search_is_fallback: bool = False
    """Treat ``live_search`` as a paid *fallback* fired only when the ingested
    FRED macro layer is stale (Phase D #711). With fresh ingested data the paid
    web_search is skipped and the segment grounds on its data tools; a stale or
    broken ingested layer still falls through to the paid call. No effect unless
    ``live_search`` is also set."""

    ai_portfolios: bool = False
    """Enable the x_search AI-portfolio-accounts grounding pre-pass for this segment."""

    extra_context_keys: tuple[str, ...] = ()
    """Prior-document keys (beyond this segment's own) to keep in shared context.

    Segment nodes receive ``prior_context.latest_segments`` filtered to their
    own slug plus these keys (#696) — e.g. asset-class nodes declare
    ``("macro",)``. The full latest-per-key dump is synthesis-only context.
    """


# Type aliases for the two factory seams.
InputsBuilder = Callable[[AtlasResearchState, SegmentNodeSpec], dict[str, Any]]
WriteAdapter = Callable[[SegmentNodeSpec, SegmentSlot], dict[str, Any]]


def _shared_context(
    state: AtlasResearchState, *, context_keys: tuple[str, ...] | None = None
) -> dict[str, Any]:
    """Assemble the stable, run-wide context block passed to every phase node.

    Serialized with sorted keys inside run_research_agent's formatter, so
    identical inputs produce identical cache keys across phase calls.

    ``context_keys`` filters ``prior_context.latest_segments`` to the prior
    documents the node actually consumes (#696). The unfiltered latest-per-key
    dump (every segment + ``analyst/*`` + ``pm-rebalance`` + digests) is noise
    for a single segment node and a direct token multiplier across the run;
    ``None`` keeps the full block (synthesis-level callers).
    """
    prior = state.prior_context.model_dump(mode="json")
    if context_keys is not None:
        wanted = set(context_keys)
        prior["latest_segments"] = {
            key: row for key, row in (prior.get("latest_segments") or {}).items() if key in wanted
        }
    return {
        "run_type": state.run_type,
        "run_date": state.run_date.isoformat(),
        "baseline_date": state.baseline_date.isoformat() if state.baseline_date else None,
        "config": state.config.model_dump(mode="json"),
        "prior_context": prior,
        "data_layer": state.data_layer.model_dump(mode="json"),
    }


def default_inputs_builder(_state: AtlasResearchState, spec: SegmentNodeSpec) -> dict[str, Any]:
    """Volatile per-segment inputs — minimal default.

    Phase 1 and Phase 2 nodes use this as-is; later phases supply their own
    builder that pulls upstream phase outputs into phase_inputs (see
    ``phase4_assetclass.py``'s macro-regime injection).
    """
    return {"segment": spec.segment_slug}


def dict_slot_write_adapter(spec: SegmentNodeSpec, slot: SegmentSlot) -> dict[str, Any]:
    """Default write: update ``state.<phase_outputs_field>[segment_slug] = slot``."""
    return {spec.phase_outputs_field: {spec.segment_slug: slot}}


def scalar_slot_write_adapter(spec: SegmentNodeSpec, slot: SegmentSlot) -> dict[str, Any]:
    """Scalar write: ``state.<phase_outputs_field> = slot`` (used by single-slot
    phases like macro where ``phase_outputs_field`` names a scalar field, not a
    dict)."""
    return {spec.phase_outputs_field: slot}


def build_segment_node(
    spec: SegmentNodeSpec,
    *,
    inputs_builder: InputsBuilder = default_inputs_builder,
    write_adapter: WriteAdapter = dict_slot_write_adapter,
    triage_gate: Callable[[AtlasResearchState, str], Carried | None] | None = None,
    model: str | None = None,
) -> Callable[[AtlasResearchState], dict[str, Any]]:
    """Return a LangGraph node for one segment (optional triage carry / model override)."""

    def _node(state: AtlasResearchState) -> dict[str, Any]:
        carried: Carried | None = None
        if triage_gate is not None:
            carried = triage_gate(state, spec.segment_slug)
        elif state.triage is not None:
            decision = next(
                (d for d in state.triage.decisions if d.segment == spec.segment_slug),
                None,
            )
            if decision is not None and decision.decision == "carry":
                carried = Carried(
                    baseline_date=state.baseline_date or state.run_date,
                    reason=decision.reason,
                )
        if carried is not None:
            return write_adapter(spec, SegmentSlot(payload=carried))

        skill_text = load_skill(spec.skill_slug)
        shared = _shared_context(state, context_keys=(spec.segment_slug, *spec.extra_context_keys))
        inputs = inputs_builder(state, spec)

        eff_model = model or get_model_for_phase(spec.segment_slug) or get_model_for_mode()
        tools, execute_tool, web_grounding = build_grounding(
            use_data_tools=spec.use_data_tools,
            live_search=spec.live_search,
            run_date=state.run_date,
            model=eff_model,
            segment=spec.segment_slug,
            ai_portfolios=spec.ai_portfolios,
            live_search_is_fallback=spec.live_search_is_fallback,
        )
        if web_grounding:
            inputs = {**inputs, "web_grounding": web_grounding}

        # Fail-soft: an empty/invalid LLM body or transient provider error degrades
        # this one segment to a Carried slot + a PhaseError instead of aborting the
        # whole run. Only the LLM call is wrapped; the input prep above stays outside
        # the thunk so genuine wiring bugs still fail loud.
        slot, errors = run_segment_fail_soft(
            run_fn=lambda: run_research_agent(
                skill_text=skill_text,
                phase_inputs=inputs,
                shared_context=shared,
                output_model=spec.output_model,
                model=model,
                phase_slug=spec.segment_slug,
                tools=tools,
                execute_tool=execute_tool,
            ),
            segment_slug=spec.segment_slug,
            phase=spec.phase_outputs_field,
            run_date=state.run_date,
            baseline_date=state.baseline_date,
        )
        update = write_adapter(spec, slot)
        if errors:
            update["errors"] = errors
        return update

    return _node


__all__ = [
    "InputsBuilder",
    "SegmentNodeSpec",
    "WriteAdapter",
    "build_grounding",
    "build_segment_node",
    "default_inputs_builder",
    "dict_slot_write_adapter",
    "get_data_client",
    "scalar_slot_write_adapter",
]
