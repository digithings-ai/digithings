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
from typing import (  # score:allow untyped any — heterogeneous node-update dict shape
    Any,
    Callable,
    Literal,
    NamedTuple,
)

from digigraph.graph.research_agent import run_research_agent
from digigraph.model_config import get_model_for_mode, get_model_for_phase
from pydantic import BaseModel

from digiquant.olympus.atlas.phases.fail_soft import run_segment_fail_soft
from digiquant.olympus.atlas.research_attention import (
    apply_segment_metric_patch,
    artifact_target_key,
    carry_segment_slot,
    research_attention_enforce_path,
    resolve_attention_plan_for_node,
    resolve_research_attention_rollout_mode,
)
from digiquant.olympus.atlas.skills import load_skill, load_skill_edit
from digiquant.olympus.atlas.state import (
    AtlasResearchState,
    Carried,
    PhaseError,
    SegmentPayload,
    SegmentSlot,
    refresh_scope_forces_full,
)

# Imported for its registration side effect (#1741): ``telemetry`` registers the
# merge-fallback ``breakdown`` contributor (#1736 seam) at import time. This module writes
# ``state.merge_fallbacks`` and every phase module imports it, so the contributor is wired
# on any compiled graph. Keep the import here rather than in ``diagnostics.py`` — the seam
# exists so a new key costs one module plus one line, not an edit to the gate rules.
from digiquant.olympus.atlas.telemetry import merge_fallback_breakdown  # noqa: F401
from digiquant.olympus.atlas.triage import triage_decision_to_signal
from digiquant.olympus.edit_mode import (
    DocumentPatch,
    EditMode,
    PriorPublished,
    artifact_document_key,
    resolve_edit_mode,
)
from digiquant.olympus.edit_mode.content_identity import (
    UNCHANGED_SINCE_KEY,
    clear_unchanged,
    mark_unchanged,
    prior_content_date,
)
from digiquant.olympus.edit_mode.merge import MergeError, merge_document_patch, section_index
from digiquant.olympus.research_retrieval.planner import AttentionRolloutMode

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
    except Exception as exc:  # any client failure → paid fallback, never crash
        logger.warning("macro freshness probe: client unavailable (%s); paid fallback", exc)
        return True
    try:
        from digiquant.olympus.atlas.supabase_io import query_macro_series_freshness

        latest = query_macro_series_freshness(client=client)
    except Exception as exc:  # any probe failure → paid fallback
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
    use_research_tools: bool = False,
    research_phase: Any | None = None,
    watchlist: tuple[str, ...] = (),
) -> tuple[list[dict[str, Any]] | None, Callable[[str, dict[str, Any]], str] | None, dict | None]:
    """Resolve ``(tools, execute_tool, web_grounding)`` for one research call.

    - ``tools`` / ``execute_tool``: the Supabase data tools (function calling).
    - ``web_grounding``: a cited grounding-summary dict to inject into ``phase_inputs`` —
      either an OpenRouter ``openrouter:web_search`` pre-pass (``live_search``) or a web
      search read of the tracked AI-portfolio accounts (``ai_portfolios``). ``None`` if
      unavailable.

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
    if use_data_tools and _data_tools_enabled():
        try:
            from digiquant.olympus.atlas.data.tools import DATA_TOOLS, build_data_tool_dispatcher

            # Anchor "as of" reads to the run's logical date (not wall-clock) so tool
            # outputs are reproducible + look-ahead-safe for backfills/delta runs.
            execute_tool = build_data_tool_dispatcher(
                _atlas_data_client(), run_date=run_date, allowed_tables=data_tool_tables
            )
            tools = DATA_TOOLS
        except Exception as exc:  # degrade to tool-less rather than crash the phase
            logger.warning("data tools unavailable (%s); proceeding without them", exc)
            tools = None
            execute_tool = None
    if use_research_tools and research_phase is not None and _data_tools_enabled():
        try:
            from digiquant.olympus.research_retrieval import (
                RESEARCH_TOOLS,
                build_research_tool_dispatcher,
            )
            from digiquant.olympus.research_retrieval.blinding import portfolio_tool_allowed

            research_defs = list(RESEARCH_TOOLS)
            if not portfolio_tool_allowed(research_phase):
                research_defs = [
                    t for t in research_defs if t["function"]["name"] != "query_portfolio"
                ]
            research_execute = build_research_tool_dispatcher(
                _atlas_data_client(),
                run_date=run_date,
                phase=research_phase,
                watchlist=watchlist,
            )
            if tools is None:
                tools = research_defs
                execute_tool = research_execute
            else:
                existing = execute_tool

                def _combined_execute(name: str, args: dict[str, Any]) -> str:
                    data_names = {t["function"]["name"] for t in DATA_TOOLS}
                    if name in data_names and existing is not None:
                        return existing(name, args)
                    return research_execute(name, args)

                tools = list(tools) + research_defs
                execute_tool = _combined_execute
        except Exception as exc:  # degrade to tool-less rather than crash the phase
            logger.warning("research tools unavailable (%s); proceeding without them", exc)
    if ai_portfolios:
        from digigraph.model_config import get_grounding_model

        from digiquant.olympus.atlas.data.ai_portfolios import fetch_ai_portfolio_grounding

        grounding = get_grounding_model(segment=segment or "ai-portfolios")
        if grounding:
            web_grounding = fetch_ai_portfolio_grounding(model=grounding, run_date=run_date)
    elif live_search:
        from digigraph.model_config import get_grounding_model

        grounding = get_grounding_model(segment=segment or "research")
        if live_search_is_fallback and not _ingested_macro_stale(run_date):
            logger.info(
                "%s: ingested macro layer fresh — skipping paid fallback web_search",
                segment or "macro",
            )
        elif grounding:
            from digiquant.olympus.atlas.data.web_grounding import fetch_web_grounding

            web_grounding = fetch_web_grounding(
                model=grounding, segment=segment or "research", run_date=run_date, scope=scope
            )
    return tools, execute_tool, web_grounding


def apply_web_grounding_to_inputs(
    phase_inputs: dict[str, Any],
    *,
    web_grounding: dict[str, Any] | None,
    segment: str,
    live_search: bool,
    live_search_is_fallback: bool = False,
) -> dict[str, Any]:
    """Merge web grounding into ``phase_inputs``; flag or fail when absent.

    A ``live_search_is_fallback`` segment (e.g. macro, #711) is grounded by its primary
    ingested-data layer; the paid web_search is a stale-only supplement that ``build_grounding``
    skips on the fresh-data hot path. Its absence is the normal cost-cut, NOT an ungrounded
    segment — so it is neither failed-hard (``OLYMPUS_WEB_SEARCH=required``) nor flagged
    ``grounding_absent`` (which would wrongly tell the analyst to lower conviction; #946 is for
    segments where web search is the *primary* grounding).
    """
    from digiquant.olympus.atlas.data.web_grounding import (
        OlympusWebSearchError,
        olympus_web_search_required,
    )

    inputs = dict(phase_inputs)
    if web_grounding:
        inputs["web_grounding"] = web_grounding
        return inputs
    if not live_search or live_search_is_fallback:
        return inputs
    if olympus_web_search_required():
        raise OlympusWebSearchError(
            f"{segment}: OLYMPUS_WEB_SEARCH=required but web grounding unavailable"
        )
    inputs["grounding_absent"] = True
    logger.warning(
        "%s: grounding-dependent segment received no web_grounding; "
        "flagging grounding_absent=True in phase_inputs",
        segment,
    )
    return inputs


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
    """Enable the OpenRouter web-search AI-portfolio grounding pre-pass for this segment."""

    extra_context_keys: tuple[str, ...] = ()
    """Prior-document keys (beyond this segment's own) to keep in shared context.

    Segment nodes receive ``prior_context.latest_segments`` filtered to their
    own slug plus these keys (#696) — e.g. asset-class nodes declare
    ``("macro",)``. The full latest-per-key dump is synthesis-only context.
    """

    data_layer_scope: DataLayerScope = "full"
    """How much of ``data_layer.market_context`` this segment receives (#935).

    Defaults to ``full``: the segment phases (macro / asset-class / sector /
    equity) reason cross-asset over the whole market_context. Slimmer scopes are
    for the ticker-scoped analyst and portfolio-scoped PM nodes, which build
    their own ``_shared_context`` calls directly. See :data:`DataLayerScope`.
    """


# Type aliases for the two factory seams.
InputsBuilder = Callable[[AtlasResearchState, SegmentNodeSpec], dict[str, Any]]
WriteAdapter = Callable[[SegmentNodeSpec, SegmentSlot], dict[str, Any]]


# --- Shared-context diet (#935) -------------------------------------------------
#
# The shared_context block was the #2 cost driver after model routing: the whole
# ``data_layer`` (every ETF's technicals + every macro series) and the full
# ``last_snapshots`` history were dumped into *every* phase node's prompt,
# regardless of what the node actually reasons over. Two knobs slim it without
# changing what a phase can reason about:
#
#   * ``data_layer_scope`` — a per-phase allowlist over ``market_context``.
#     Analyst nodes fetch their own ticker's technicals via the data tools, so
#     they don't need the run-wide per-ticker ETF dump; the PM is portfolio- not
#     ticker-scoped. Freshness probes + the compact regime signals (``fed_odds``,
#     ``onchain_positioning``) are cheap and kept for every scope.
#   * ``slim_snapshots`` — on a delta run, the full N-snapshot ``last_snapshots``
#     history is redundant inside shared_context (the phases that consume it —
#     triage / phase9 / monthly — pull it into their own ``phase_inputs``). Keep
#     only the latest snapshot's compact bias row + the segment slugs that
#     changed vs the baseline, so a delta node still sees yesterday's stance.
#
# The block keys stay the same and SHARED_CONTEXT remains the first (stable)
# content part, so the stable→volatile prompt-cache ordering is unchanged (#935).

DataLayerScope = Literal["full", "portfolio", "ticker", "none"]
"""How much of ``data_layer.market_context`` a phase node receives.

- ``full`` (default): the entire market_context — every ETF's technicals + every
  macro series. For nodes that reason cross-asset (macro, asset classes, sectors,
  equity, synthesis, monthly, evolution).
- ``portfolio``: drop the per-ticker ``price_technicals`` ETF dump (the PM reads
  the book + prices via the data tools), keep macro series + regime signals.
- ``ticker``: drop both the per-ticker ETF dump *and* the bulk macro series —
  blinded analyst specialists fetch their own ticker's data via the tools; keep
  only the compact regime signals (fed_odds / onchain) for awareness.
- ``none``: drop ``market_context`` entirely (freshness probes only).
"""

# Compact regime signals preflight folds into ``market_context`` (#801/#806).
# Cheap and broadly useful, so every non-``full`` scope keeps them.
_REGIME_SIGNAL_KEYS: tuple[str, ...] = ("fed_odds", "onchain_positioning")

# Bias fields carried in the slim delta snapshot (mirrors Phase6BiasRow's
# regime + per-asset bias surface — the part a delta node needs to see
# yesterday's stance without re-reading the full digest snapshot).
# NOTE: ``date`` is deliberately excluded — it is renamed to ``prior_date``
# in ``_slim_prior_snapshots`` so the model does not confuse the prior
# snapshot's date with the current run's analysis date (#949).
_SNAPSHOT_BIAS_KEYS: tuple[str, ...] = (
    "run_type",
    "macro_regime",
    "equity_bias",
    "crypto_bias",
    "bond_bias",
    "commodity_bias",
    "forex_bias",
    "vix_level",
    "fed_odds",
    "regime_label",
    "market_regime_snapshot",
)


def _scoped_data_layer(data_layer: dict[str, Any], scope: DataLayerScope) -> dict[str, Any]:
    """Return ``data_layer`` with ``market_context`` trimmed to ``scope`` (#935).

    Freshness probes (``*_latest``, ``*_count``, ``fallback_used``) are always
    kept — they're scalars. Only ``market_context`` is trimmed; the slimmer
    scopes drop the per-ticker / bulk-macro blocks the node doesn't read but
    keep the compact regime signals.
    """
    if scope == "full":
        return data_layer
    out = dict(data_layer)
    mc = data_layer.get("market_context") or {}
    if scope == "none" or not isinstance(mc, dict):
        out["market_context"] = {}
        return out
    trimmed: dict[str, Any] = {}
    if "as_of" in mc:
        trimmed["as_of"] = mc["as_of"]
    if scope == "portfolio":
        # PM: keep macro context, drop the per-ticker ETF technicals dump.
        if mc.get("macro_series"):
            trimmed["macro_series"] = mc["macro_series"]
    # ``ticker`` scope keeps neither block — analysts fetch their own.
    for key in _REGIME_SIGNAL_KEYS:
        if key in mc:
            trimmed[key] = mc[key]
    out["market_context"] = trimmed
    return out


def _changed_segment_keys(state: AtlasResearchState) -> list[str]:
    """Segment slugs the current delta run regenerated (vs carried).

    Read from the triage decisions when present; falls back to the freshly
    written phase outputs. Used to tell a delta node *which* segments moved so
    the slim snapshot points at the right deltas without the full history.
    """
    if state.triage is not None and state.triage.decisions:
        return sorted(d.segment for d in state.triage.decisions if d.decision == "regenerate")
    changed: set[str] = set()
    for field in ("phase1_outputs", "phase2_outputs", "phase4_outputs", "phase5_outputs"):
        outputs = getattr(state, field, None) or {}
        for slug, slot in outputs.items():
            payload = getattr(slot, "payload", None)
            if getattr(payload, "source", None) == "today":
                changed.add(slug)
    return sorted(changed)


def _slim_prior_snapshots(prior: dict[str, Any], state: AtlasResearchState) -> None:
    """In-place: replace the full ``last_snapshots`` history with a slim delta view.

    On a delta run the full N-snapshot history is redundant in shared_context;
    keep only the latest snapshot's compact ``bias_row`` plus the slugs that
    changed this run. Mutates ``prior`` (a fresh ``model_dump`` copy).

    The snapshot's ``date`` is renamed to ``prior_date`` so the model does not
    confuse the prior snapshot's date with the current run's analysis date
    (``run_date`` at the top level of shared_context) (#949).
    """
    snapshots = prior.get("last_snapshots") or []
    bias_row: dict[str, Any] = {}
    if snapshots:
        snap = snapshots[0].get("snapshot") if isinstance(snapshots[0], dict) else None
        if isinstance(snap, dict):
            bias_row = {k: snap[k] for k in _SNAPSHOT_BIAS_KEYS if k in snap}
        # Carry the snapshot's own envelope dates so continuity is preserved.
        # ``date`` is renamed to ``prior_date`` to avoid the model confusing it
        # with the current analysis date (#949).
        for env_key in ("run_type", "baseline_date"):
            if isinstance(snapshots[0], dict) and env_key in snapshots[0]:
                bias_row.setdefault(env_key, snapshots[0][env_key])
        if isinstance(snapshots[0], dict):
            snap_date = snapshots[0].get("date") or (snap or {}).get("date")
            if snap_date is not None:
                bias_row["prior_date"] = snap_date
    prior.pop("last_snapshots", None)
    prior["bias_row"] = bias_row
    prior["changed_segments"] = _changed_segment_keys(state)


# Source keys kept when the segment-payload diet runs on a delta (#949): the provenance
# trio the synthesis/digest phases cite. Guarantees a source never degrades to
# ``title:null`` after slimming.
_SOURCE_PROVENANCE_KEYS: frozenset[str] = frozenset({"id", "title", "url"})


def _slim_segment_payloads(prior: dict[str, Any]) -> None:
    """In-place: trim fat from ``latest_segments`` payloads on delta runs (#949).

    On a delta run, each segment's prior payload is carried in shared_context for
    continuity. The full body text (``notes``, detailed ``material_findings``
    summaries) is noise for a delta phase that only needs the prior stance + source
    provenance. This function trims the payload while *explicitly* preserving every
    source's ``id``, ``title``, and ``url`` — the provenance chain the synthesis
    and digest phases need for citations.

    Mutates ``prior`` in-place (called on a fresh ``model_dump`` copy).
    """
    segments = prior.get("latest_segments")
    if not isinstance(segments, dict):
        return
    for _key, row in segments.items():
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        # Preserve source provenance: keep id + title + url on every source.
        sources = payload.get("sources")
        if isinstance(sources, list):
            payload["sources"] = [
                {k: s[k] for k in _SOURCE_PROVENANCE_KEYS if k in s} if isinstance(s, dict) else s
                for s in sources
            ]
        # Trim fat text fields that a delta node doesn't need in shared context.
        notes = payload.get("notes")
        if isinstance(notes, str) and len(notes) > 120:
            payload["notes"] = notes[:120] + "..."


def _shared_context(
    state: AtlasResearchState,
    *,
    context_keys: tuple[str, ...] | None = None,
    data_layer_scope: DataLayerScope = "full",
    slim_snapshots: bool | None = None,
) -> dict[str, Any]:
    """Assemble the stable, run-wide context block passed to every phase node.

    Serialized with sorted keys inside run_research_agent's formatter, so
    identical inputs produce identical cache keys across phase calls. The block
    keys + ordering are unchanged by the diet knobs below, so SHARED_CONTEXT
    stays the first (stable) prompt content part — preserving the stable→volatile
    prompt-cache ordering (#935).

    ``context_keys`` filters ``prior_context.latest_segments`` to the prior
    documents the node actually consumes (#696). The unfiltered latest-per-key
    dump (every segment + ``analyst/*`` + ``pm-rebalance`` + digests) is noise
    for a single segment node and a direct token multiplier across the run;
    ``None`` keeps the full block (synthesis-level callers).

    ``data_layer_scope`` trims ``data_layer.market_context`` to what the phase
    reasons over (#935) — see :data:`DataLayerScope`. Analyst nodes get
    ticker-scoped context; the PM gets portfolio-scoped; cross-asset phases keep
    the full block.

    ``slim_snapshots`` replaces the full ``last_snapshots`` history with a slim
    delta view (latest bias row + changed segments). ``None`` (default) auto-ons
    for delta runs and offs for baseline/monthly; pass an explicit bool to force.

    On delta runs, ``latest_segments`` payloads are also slimmed: fat text fields
    are trimmed while source provenance (``id``, ``title``, ``url``) is explicitly
    preserved (#949).
    """
    prior = state.prior_context.model_dump(mode="json")
    if context_keys is not None:
        wanted = set(context_keys)
        prior["latest_segments"] = {
            key: row for key, row in (prior.get("latest_segments") or {}).items() if key in wanted
        }
    if slim_snapshots is None:
        slim_snapshots = state.run_type == "delta"
    if slim_snapshots:
        _slim_prior_snapshots(prior, state)
        _slim_segment_payloads(prior)
    return {
        "run_type": state.run_type,
        "run_date": state.run_date.isoformat(),
        "baseline_date": state.baseline_date.isoformat() if state.baseline_date else None,
        "config": state.config.model_dump(mode="json"),
        "prior_context": prior,
        "data_layer": _scoped_data_layer(
            state.data_layer.model_dump(mode="json"), data_layer_scope
        ),
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


class _StatePriorLoader:
    """Resolve segment priors from ``state.prior_context.latest_segments``."""

    def __init__(self, state: AtlasResearchState) -> None:
        self._state = state

    def load(self, artifact_key: tuple[str, str], run_date: date) -> PriorPublished | None:
        doc_key = artifact_document_key(artifact_key)
        row = self._state.prior_context.latest_segments.get(doc_key)
        if not isinstance(row, dict):
            return None
        row_date = row.get("date")
        payload = row.get("payload")
        if not isinstance(row_date, str) or not isinstance(payload, dict):
            return None
        published = date.fromisoformat(row_date)
        if published >= run_date:
            return None
        return PriorPublished(
            date=published,
            document_key=doc_key,
            payload=dict(payload),
            # The content clock, distinct from the publish date (#1749). ``prior_content_date``
            # returns ``published`` when the row carries no ``unchanged_since`` marker, so a
            # pre-marker row resolves exactly as it did before.
            content_date=prior_content_date(payload, published),
        )


def _triage_reason_for_segment(state: AtlasResearchState, segment: str) -> str | None:
    if state.triage is None:
        return None
    decision = next((d for d in state.triage.decisions if d.segment == segment), None)
    return decision.reason if decision is not None else None


def _resolve_segment_edit_mode(state: AtlasResearchState, segment: str) -> EditMode:
    loader = _StatePriorLoader(state)
    triage_signal = None
    if state.triage is not None:
        decision = next((d for d in state.triage.decisions if d.segment == segment), None)
        if decision is not None:
            triage_signal = triage_decision_to_signal(decision)
    return resolve_edit_mode(
        artifact_key=("segment", segment),
        run_date=state.run_date,
        prior_loader=loader,
        triage=triage_signal,
        force_full_rewrite=refresh_scope_forces_full(state.refresh_scope, artifact="segment"),
    )


def _carry_baseline_date(state: AtlasResearchState, segment: str) -> date:
    prior = _StatePriorLoader(state).load(("segment", segment), state.run_date)
    if prior is not None:
        return prior.date
    return state.baseline_date or state.run_date


def _edit_phase_inputs(
    *,
    base_inputs: dict[str, Any],
    prior: PriorPublished,
    triage_reason: str | None,
) -> dict[str, Any]:
    return {
        **base_inputs,
        "edit_mode": "edit",
        "prior_date": prior.date.isoformat(),
        "prior_document": prior.payload,
        "section_index": section_index(prior.payload),
        "triage_reason": triage_reason or "",
    }


class EditSegmentResult(NamedTuple):
    """Outcome of one edit-mode segment attempt.

    ``slot is None`` ⇒ the patch could not be merged and the caller must regenerate in
    full mode (#1641). ``merge_fallback_reason`` carries the *why* for the non-gating
    telemetry that #1641 omitted (#1741) and is set only in that case.

    ``content_changed`` / ``unchanged_since`` are the content-identity outcome (#1749). They
    default to "changed" so every early return — a failed patch call, a non-``SegmentPayload``
    body, a merge fallback — is treated as a real edit rather than silently reported as a
    freeze. Read them by attribute, not by tuple unpacking: the caller used to destructure
    four values positionally and that is now brittle.
    """

    slot: SegmentSlot | None
    errors: list[PhaseError]
    delta: DocumentPatch | None
    merge_fallback_reason: str | None = None
    content_changed: bool = True
    unchanged_since: str | None = None


# Cap on the stored merge-failure reason. A Pydantic ValidationError message carries the
# full offending body; ``atlas_run_diagnostics.breakdown`` is an operator-facing jsonb
# column, not a log sink, and the same cap is applied to ``master_digest_failed``.
_MERGE_FALLBACK_REASON_MAX = 300


def _delta_row(result: EditSegmentResult) -> dict[str, Any]:
    """The published ``document-deltas/<key>`` payload, plus the deterministic merge outcome.

    The delta row is the audit artifact for an edit-mode segment, and on a no-op merge it was
    the most misleading thing the pipeline wrote: production's 2026-07-31
    ``document-deltas/sector-healthcare`` row advertised ``status="updated"`` with six ``set``
    ops and a per-op ``reason`` each, over a body byte-identical to 07-29's. Every op set a
    value that was already present — the row asserted six specific changes that did not happen.

    ``content_changed`` is derived by the pipeline, never by the model, which is why it is
    attached to the dumped row here rather than added as a ``DocumentPatch`` field — there it
    would become part of the LLM's output schema. Nothing re-validates a published delta row
    back into ``DocumentPatch``, so the extra keys are safe despite ``extra="forbid"``.
    """
    row = result.delta.model_dump(mode="json") if result.delta is not None else {}
    row["content_changed"] = result.content_changed
    if result.unchanged_since:
        row[UNCHANGED_SINCE_KEY] = result.unchanged_since
    return row


def _run_edit_segment(
    *,
    state: AtlasResearchState,
    spec: SegmentNodeSpec,
    inputs: dict[str, Any],
    prior: PriorPublished,
    triage_reason: str | None,
    shared: dict[str, Any],
    eff_model: str,
    tools: list[dict[str, Any]] | None,
    execute_tool: Callable[[str, dict[str, Any]], str] | None,
    model: str | None,
) -> EditSegmentResult:
    """Run one segment in edit mode. A ``None`` slot means the patch merge failed and
    the caller must fall back to full-mode regeneration (#1641)."""
    skill_text = load_skill_edit(spec.skill_slug)
    edit_inputs = _edit_phase_inputs(
        base_inputs=inputs,
        prior=prior,
        triage_reason=triage_reason,
    )

    def _run_patch() -> DocumentPatch:
        result = run_research_agent(
            skill_text=skill_text,
            phase_inputs=edit_inputs,
            shared_context=shared,
            output_model=DocumentPatch,
            model=model,
            phase_slug=spec.segment_slug,
            tools=tools,
            execute_tool=execute_tool,
        )
        if not isinstance(result, DocumentPatch):
            msg = f"edit-mode expected DocumentPatch, got {type(result).__name__}"
            raise TypeError(msg)
        return result

    patch_slot, errors = run_segment_fail_soft(
        run_fn=_run_patch,
        segment_slug=spec.segment_slug,
        phase=spec.phase_outputs_field,
        run_date=state.run_date,
        baseline_date=prior.date,
    )
    if errors:
        return EditSegmentResult(patch_slot, errors, None)

    payload = patch_slot.payload
    if not isinstance(payload, SegmentPayload):
        return EditSegmentResult(patch_slot, errors, None)
    patch_model = DocumentPatch.model_validate(payload.body)

    try:
        merge_result = merge_document_patch(
            prior.payload,
            patch_model,
            schema_validator=lambda body: spec.output_model.model_validate(body),
        )
    except (MergeError, Exception) as exc:
        # Fall back to FULL regeneration instead of carrying + failing the segment
        # (#1641): a merge failure is a patch-shape defect, not evidence the segment
        # can't be researched today. Mirrors the digest edit path's fallback. No
        # PhaseError here — a successful full run must not leave the run degraded;
        # the full path's own fail-soft covers a second failure.
        reason = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "edit-mode merge failed for segment %r (%s); falling back to full generation",
            spec.segment_slug,
            reason,
        )
        return EditSegmentResult(None, [], None, reason[:_MERGE_FALLBACK_REASON_MAX].strip())

    merged_body = dict(merge_result.materialized)
    merged_body.setdefault("segment", spec.segment_slug)
    merged_body["date"] = state.run_date.isoformat()
    # Content-identity provenance (#1749/#1751). The body above is about to be published
    # under the run date with source="today" whether or not the merge changed anything, so
    # stamp what actually happened. ``mark_unchanged`` PROPAGATES the prior chain's
    # ``unchanged_since`` rather than resetting it, which is what lets ``gap_days`` accumulate
    # and §5.3.2's hard cap eventually fire; ``clear_unchanged`` is the matching reset, needed
    # because ``apply_ops`` copies the prior body and would otherwise carry a stale marker
    # forward through every subsequent real edit.
    if merge_result.merge_stats.content_changed:
        clear_unchanged(merged_body)
    else:
        mark_unchanged(merged_body, prior=prior.payload, prior_date=prior.date)
    slot = SegmentSlot(
        payload=SegmentPayload(
            segment=spec.segment_slug,
            body=merged_body,
            as_of=state.run_date,
        )
    )
    return EditSegmentResult(
        slot,
        [],
        merge_result.delta,
        content_changed=merge_result.merge_stats.content_changed,
        unchanged_since=merged_body.get(UNCHANGED_SINCE_KEY),
    )


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
        # Non-gating: an edit→full fallback that then succeeds must still leave the run
        # `ok`, but it must stop being invisible (#1741).
        merge_fallbacks: dict[str, str] = {}
        target_key = artifact_target_key("segment", spec.segment_slug)
        rollout = resolve_research_attention_rollout_mode()
        if rollout is not AttentionRolloutMode.OFF and not state.custom_prompt:
            resolve_attention_plan_for_node(state)
        enforce_path = research_attention_enforce_path(state, target_key=target_key)
        if enforce_path == "carry":
            reason = _triage_reason_for_segment(state, spec.segment_slug) or "attention_carry"
            prior = _StatePriorLoader(state).load(("segment", spec.segment_slug), state.run_date)
            return write_adapter(
                spec,
                carry_segment_slot(state, spec.segment_slug, reason=reason, prior=prior),
            )
        if enforce_path == "metric_patch":
            prior = _StatePriorLoader(state).load(("segment", spec.segment_slug), state.run_date)
            if prior is not None:
                return write_adapter(
                    spec,
                    apply_segment_metric_patch(state, spec.segment_slug, prior),
                )
            enforce_path = None
        if triage_gate is not None:
            carried = triage_gate(state, spec.segment_slug)
        else:
            mode = _resolve_segment_edit_mode(state, spec.segment_slug)
            if mode == "skip":
                carried = Carried(
                    baseline_date=_carry_baseline_date(state, spec.segment_slug),
                    reason=_triage_reason_for_segment(state, spec.segment_slug) or "quiet_carry",
                )

        if carried is not None:
            return write_adapter(spec, SegmentSlot(payload=carried))

        shared = _shared_context(
            state,
            context_keys=(spec.segment_slug, *spec.extra_context_keys),
            data_layer_scope=spec.data_layer_scope,
        )
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
        elif spec.live_search or spec.ai_portfolios:
            inputs = apply_web_grounding_to_inputs(
                inputs,
                web_grounding=None,
                segment=spec.segment_slug,
                live_search=spec.live_search or spec.ai_portfolios,
                live_search_is_fallback=spec.live_search_is_fallback,
            )

        edit_mode = _resolve_segment_edit_mode(state, spec.segment_slug)
        if edit_mode == "edit":
            prior = _StatePriorLoader(state).load(("segment", spec.segment_slug), state.run_date)
            if prior is None:
                edit_mode = "full"
            else:
                edit_result = _run_edit_segment(
                    state=state,
                    spec=spec,
                    inputs=inputs,
                    prior=prior,
                    triage_reason=_triage_reason_for_segment(state, spec.segment_slug),
                    shared=shared,
                    eff_model=eff_model,
                    tools=tools,
                    execute_tool=execute_tool,
                    model=model,
                )
                slot, errors = edit_result.slot, edit_result.errors
                fallback_reason = edit_result.merge_fallback_reason
                if slot is not None:
                    update = write_adapter(spec, slot)
                    if edit_result.delta is not None:
                        update["document_deltas"] = {spec.segment_slug: _delta_row(edit_result)}
                    if not edit_result.content_changed:
                        # Run-level tally for the diagnostics breakdown (#1751). Written here
                        # rather than derived at summarize time because the merge outcome is
                        # only known at the node, and the published body's marker is the only
                        # other record of it.
                        update["content_freezes"] = {
                            spec.segment_slug: edit_result.unchanged_since or ""
                        }
                    if errors:
                        update["errors"] = errors
                    return update
                # slot is None ⇒ patch merge failed (#1641) — regenerate from scratch
                # via the full path below rather than carrying + degrading the run.
                # Record it so a cost audit can count the segments that paid twice.
                merge_fallbacks = {spec.segment_slug: fallback_reason or "merge_failed"}

        skill_text = load_skill(spec.skill_slug)

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
        if merge_fallbacks:
            update["merge_fallbacks"] = merge_fallbacks
        return update

    return _node


__all__ = [
    "DataLayerScope",
    "EditSegmentResult",
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
