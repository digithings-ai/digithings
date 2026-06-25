"""Compiled Atlas sub-graph — research only.

DigiClaw (issue #219) and the chain orchestrator invoke the Atlas pipeline
through ``build_atlas_graph`` + ``AtlasInput``. The contract is deliberately
small and stable so callers never have to know about internal phase
structure.

Per ADR-0015, Atlas owns research only. Analysis, debate, PM, and
reflection moved to ``digiquant.olympus.hermes`` (#471/#472). The
end-to-end cron entry point is :func:`digiquant.olympus.hermes.chain.run_atlas_then_hermes`,
which wires Atlas (no publish) → Hermes → publish_phase.

Single **daily** graph topology: preflight → optional preflight_reflect →
triage → Phase 1–7 → optional publish_phase. Per-artifact edit vs full vs
skip is resolved in-node via ``resolve_edit_mode`` (not separate graphs).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable  # noqa: F401 — used for LangGraph node shape
from uuid import UUID

from digigraph.graph.pipeline_builder import PipelinePhase, build_pipeline

from digiquant.olympus.atlas.phases.phase1_altdata import build_phase1
from digiquant.olympus.atlas.phases.phase2_institutional import build_phase2
from digiquant.olympus.atlas.phases.phase3_macro import build_phase3
from digiquant.olympus.atlas.phases.phase4_assetclass import build_phase4
from digiquant.olympus.atlas.phases.phase5_equities import build_phase5
from digiquant.olympus.atlas.phases.phase6_consolidate import build_phase6
from digiquant.olympus.atlas.phases.phase7_synthesis import build_phase7
from digiquant.olympus.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
    build_preflight_node,
    build_preflight_reflect_node,
)
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps, build_publish_phase
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps, build_triage_phase
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Cadence,
    RefreshScope,
    RunType,
)


@dataclass(frozen=True)
class AtlasInput:
    """Contract between DigiClaw and the Atlas sub-graph.

    Kept small on purpose — one job's worth of invocation data. The
    watchlist is part of the input (not the state) because Phase 7C's
    fan-out width is determined at graph-compile time; changing the
    watchlist mid-run would require a recompile.
    """

    run_date: date
    cadence: Cadence = "daily"
    refresh_scope: RefreshScope = "none"
    baseline_date: date | None = None
    watchlist: tuple[str, ...] = ()
    digi_bearer: str | None = None
    # Optional user-supplied prompt for a one-off custom research run (#313).
    # Empty string is treated as None at CLI parse time.
    custom_prompt: str | None = None


@dataclass(frozen=True)
class AtlasGraphDeps:
    """Dependencies the sub-graph needs at invoke time.

    The caller injects a preflight deps object (Supabase client + config
    loader). This keeps the graph-construction pure — no env reads, no
    implicit globals.

    ``publish`` is optional: ``None`` skips the terminal publish phase entirely
    (preserves the dry-run path that never builds a real Supabase client).
    Production CLI threads a ``PublishDeps`` carrying the same client used for
    preflight reads. Monthly runs ignore ``publish`` regardless — they have a
    different output shape and ``daily_snapshots.run_type`` rejects ``monthly``.

    ``triage`` is optional: ``None`` builds the triage phase without a
    Supabase client, which keeps the legacy test path (no live DB) green.
    The price-delta signal is empty in that mode and high-tier rules
    regenerate by default.
    """

    preflight: PreflightDeps
    publish: PublishDeps | None = None
    triage: TriageDeps | None = None
    # Closed-loop reflection-read deps (#432). Default None so the legacy
    # test path (no live DB) keeps compiling. The reflection *write* deps
    # (formerly ``phase9``) moved to Hermes per ADR-0015.
    preflight_reflect: PreflightReflectDeps | None = None


def build_atlas_graph(
    *,
    deps: AtlasGraphDeps,
    watchlist: tuple[str, ...] = (),
    checkpointer: Any = None,
):
    """Compile and return the daily Atlas StateGraph.

    Callers:
        >>> graph = build_atlas_graph(deps=my_deps, watchlist=("AAPL",))
        >>> result = graph.invoke(AtlasResearchState(run_type="delta", run_date=today))
    """
    preflight_phase = PipelinePhase(
        name="preflight",
        nodes=[_as_node("preflight", build_preflight_node(deps.preflight))],
    )

    daily_phases: list[PipelinePhase] = [preflight_phase]

    # Phase B of #432 — resolve any due ``decision_log`` rows by computing
    # alpha vs SPY and calling the decision-reflector skill. Sequenced
    # immediately after preflight so the reflection LLM call lands inside
    # the pre-flight stage but preflight itself stays LLM-free. Skipped
    # entirely when ``preflight_reflect`` deps aren't wired (legacy test
    # path + dry-run path both rely on this).
    if deps.preflight_reflect is not None:
        daily_phases.append(
            PipelinePhase(
                name="preflight_reflect",
                nodes=[
                    _as_node(
                        "preflight-reflect",
                        build_preflight_reflect_node(deps.preflight_reflect),
                    )
                ],
            )
        )

    daily_phases.append(build_triage_phase(deps.triage))

    daily_phases.extend(
        [
            build_phase1(),
            build_phase2(),
            build_phase3(),
            build_phase4(),
            *build_phase5(),
            build_phase6(),
            build_phase7(),
        ]
    )
    if deps.publish is not None:
        # Standalone Atlas runs (CLI without --no-publish, tests with a
        # FakeSupabaseClient) publish research-only artifacts. The chain
        # orchestrator passes ``publish=None`` and wires publish_phase
        # after Hermes instead — see digiquant.olympus.hermes.chain.
        daily_phases.append(build_publish_phase(deps.publish))
    return build_pipeline(AtlasResearchState, daily_phases, checkpointer=checkpointer)


def _as_node(name: str, run: Callable[..., dict[str, Any]]):
    """Wrap a plain callable into a NodeSpec without reaching into phase internals."""
    from digigraph.graph.pipeline_builder import NodeSpec

    return NodeSpec(name=name, run=run)


# ─── Initial-state helper ───────────────────────────────────────────────────


def initial_state(
    atlas_input: AtlasInput,
    config: AtlasConfigBundle | None = None,
    run_id: UUID | None = None,
) -> AtlasResearchState:
    """Build an ``AtlasResearchState`` from ``AtlasInput``.

    Separated from ``build_atlas_graph`` so tests and DigiClaw can
    construct states without touching the graph compiler.
    """
    extra: dict[str, Any] = {}
    if run_id is not None:
        extra["run_id"] = run_id
    return AtlasResearchState(
        run_type=_legacy_run_type(atlas_input.refresh_scope),
        cadence=atlas_input.cadence,
        refresh_scope=atlas_input.refresh_scope,
        run_date=atlas_input.run_date,
        baseline_date=atlas_input.baseline_date,
        config=config or AtlasConfigBundle(watchlist=list(atlas_input.watchlist)),
        custom_prompt=atlas_input.custom_prompt or None,
        **extra,
    )


__all__ = [
    "AtlasGraphDeps",
    "AtlasInput",
    "_legacy_run_type",
    "build_atlas_graph",
    "build_cli_parser",
    "cli_main",
    "initial_state",
    "resolve_cli_inputs",
]


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.olympus.atlas.graph …`` by the GitHub Actions
# schedulers (see ``.github/workflows/atlas-*.yml``). The CLI is kept
# intentionally thin: parse flags → resolve baseline → build AtlasInput →
# invoke the compiled graph. Heavy lifting stays in the graph itself.


def _parse_cli_date(value: str):
    from datetime import datetime as _dt

    return _dt.strptime(value, "%Y-%m-%d").date()


# ─── Config-file helpers ─────────────────────────────────────────────────────


def _atlas_config_root():
    """Return ``digiquant/src/digiquant/olympus/atlas/config/``.

    Config ships inside the Atlas package alongside skills + templates
    via ``[tool.setuptools.package-data]`` (#486).
    """
    from pathlib import Path

    return Path(__file__).resolve().parent / "config"


def _parse_watchlist_md() -> list[str]:
    """Extract ticker symbols from config/watchlist.md table rows.

    Matches rows of the form ``| TICKER | description | … |``.
    Falls back to an empty list when the file is absent.
    """
    import re

    path = _atlas_config_root() / "watchlist.md"
    if not path.exists():
        return []
    tickers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*\|\s*([A-Z0-9]{1,6})\s*\|", line)
        if m:
            ticker = m.group(1)
            if ticker not in tickers:
                tickers.append(ticker)
    return tickers


def _parse_macro_series_yaml() -> list[str]:
    """Extract series IDs from config/macro_series.yaml.

    Returns an empty list when the file is absent or unparseable.
    """
    import yaml

    path = _atlas_config_root() / "macro_series.yaml"
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError, UnicodeDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    ids: list[str] = []
    for section in data.values():
        if isinstance(section, dict) and "series" in section:
            for item in section.get("series", []):
                if isinstance(item, dict) and "id" in item:
                    sid = str(item["id"])
                    if sid not in ids:
                        ids.append(sid)
    return ids


def _make_default_config_loader(
    cli_watchlist: tuple[str, ...],
) -> Callable[[], AtlasConfigBundle]:
    """Return a config_loader closure for the CLI path.

    CLI ``--watchlist`` takes priority; falls back to config/watchlist.md
    when the flag is omitted. Macro series IDs always come from
    config/macro_series.yaml (empty list when absent).
    """

    def _load() -> AtlasConfigBundle:
        watchlist = list(cli_watchlist) if cli_watchlist else _parse_watchlist_md()
        from digiquant.olympus.atlas.dashboard_digest import portfolio_preferences_static

        return AtlasConfigBundle(
            watchlist=watchlist,
            macro_series=_parse_macro_series_yaml(),
            preferences=portfolio_preferences_static(_atlas_config_root() / "portfolio.json"),
        )

    return _load


def _legacy_run_type(refresh_scope: RefreshScope) -> RunType:
    """Map operator refresh scope to the legacy ``daily_snapshots.run_type`` label."""
    return "baseline" if refresh_scope == "all" else "delta"


def _add_cadence_cli_args(parser) -> None:
    parser.add_argument(
        "--cadence",
        default="daily",
        choices=("daily",),
        help="Pipeline cadence (v1: daily only).",
    )
    parser.add_argument(
        "--refresh-scope",
        default="none",
        choices=("none", "all", "segments", "hermes", "digest", "beliefs"),
        dest="refresh_scope",
        help="Force full rewrites for matching artifact classes (operator escape hatch).",
    )
    parser.add_argument(
        "--run-type",
        default=None,
        choices=("baseline", "delta", "monthly"),
        help="Deprecated — use --cadence daily and --refresh-scope.",
    )


def _resolve_cadence_inputs(args) -> tuple[Cadence, RefreshScope]:
    import warnings

    cadence: Cadence = args.cadence
    refresh_scope: RefreshScope = args.refresh_scope
    run_type = getattr(args, "run_type", None)
    if run_type is not None:
        warnings.warn(
            f"--run-type {run_type!r} is deprecated; use --cadence daily and --refresh-scope",
            DeprecationWarning,
            stacklevel=3,
        )
        if run_type == "monthly":
            raise SystemExit("--run-type monthly is removed; use --cadence daily")
        if run_type == "baseline":
            refresh_scope = "all"
    if cadence != "daily":
        raise SystemExit(f"Only --cadence daily is supported (got {cadence!r})")
    return cadence, refresh_scope


def build_cli_parser():
    """Return the argparse parser.

    Exposed for unit tests (``tests/test_cli.py``) to exercise flag
    handling without invoking the graph.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.olympus.atlas.graph",
        description="Invoke the Atlas research sub-graph.",
    )
    _add_cadence_cli_args(parser)
    parser.add_argument(
        "--run-date",
        required=True,
        type=_parse_cli_date,
        help="YYYY-MM-DD — the logical date this run represents.",
    )
    parser.add_argument(
        "--baseline-date",
        type=_parse_cli_date,
        default=None,
        help="Explicit baseline date for delta runs. Ignored when --auto-baseline is set.",
    )
    parser.add_argument(
        "--auto-baseline",
        action="store_true",
        help=(
            "Resolve --baseline-date from Supabase by querying daily_snapshots "
            "for the latest baseline run. Deprecated — prefer --refresh-scope all."
        ),
    )
    parser.add_argument(
        "--watchlist",
        default="",
        help=(
            "Comma-separated ticker list. Empty falls back to config/watchlist.md "
            "(#694); pass 'none' to skip the Phase 7C fan-out entirely."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve inputs + compile graph, print JSON summary, exit 0 (no LLM calls).",
    )
    parser.add_argument(
        "--custom-prompt",
        default="",
        help=(
            "Optional one-off research prompt (#313). When set, Phase 7 synthesis "
            "includes the prompt as additional context and the publish phase routes "
            "the digest under doc_type='Custom Research'. Empty string means none."
        ),
    )
    return parser


def _auto_resolve_baseline(run_date: date) -> date | None:
    """Query Supabase for the latest baseline run date from ``daily_snapshots``.

    Returns ``None`` when Supabase credentials are absent or no prior baseline
    exists; the caller decides whether that's a fatal condition (it is, for real
    runs; tolerated under ``--dry-run`` so the scheduler smoke test stays hermetic).
    """
    import os

    if not os.getenv("CORE_SUPABASE_URL", os.getenv("SUPABASE_URL")) or not os.getenv(
        "CORE_SUPABASE_SERVICE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    ):
        return None

    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    client = build_client(SupabaseConfig.from_env())
    resp = (
        client.table("daily_snapshots")
        .select("date")
        .eq("run_type", "baseline")
        .lt("date", run_date.isoformat())
        .order("date", desc=True)
        .limit(1)
        .execute()
    )
    rows = getattr(resp, "data", None) or []
    if not rows:
        return None
    raw = rows[0].get("date")
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        return _parse_cli_date(raw)
    return None


def resolve_cli_inputs(args) -> dict:
    """Translate argparse Namespace → AtlasInput kwargs.

    Pure apart from the optional Supabase call behind ``--auto-baseline`` and
    the ``config/watchlist.md`` read on the no-flag fallback;
    ``tests/dq/atlas/test_cli.py`` covers the explicit and auto-baseline
    paths by stubbing that call.
    """
    raw_watchlist = args.watchlist.strip()
    if raw_watchlist.lower() == "none":
        # Explicit opt-out: compile zero 7C/7CD nodes (the pre-#694 empty
        # behavior, now opt-in instead of the accidental default).
        watchlist: tuple[str, ...] = ()
    else:
        watchlist = tuple(t.strip() for t in raw_watchlist.split(",") if t.strip())
        if not watchlist:
            # Scheduled/CI runs pass no --watchlist. Fall back to config/watchlist.md
            # so the Hermes 7C/7CD per-ticker fan-out actually runs (#694) — the
            # graphs are compiled from AtlasInput.watchlist, and an empty tuple
            # silently skipped every analyst/debate node on scheduled runs.
            # ATLAS_MAX_ANALYSTS still caps the fan-out at phase-build time.
            watchlist = tuple(_parse_watchlist_md())
    baseline_date = args.baseline_date
    cadence, refresh_scope = _resolve_cadence_inputs(args)

    if args.auto_baseline:
        if getattr(args, "run_type", None) not in (None, "delta"):
            raise SystemExit("--auto-baseline only valid with deprecated --run-type delta")
        resolved = _auto_resolve_baseline(args.run_date)
        if resolved is None and not args.dry_run:
            raise SystemExit(
                "--auto-baseline could not resolve a baseline date; "
                "is SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY set and does "
                "daily_snapshots contain a prior baseline run?"
            )
        baseline_date = resolved

    custom_prompt_raw = (getattr(args, "custom_prompt", "") or "").strip()
    return {
        "cadence": cadence,
        "refresh_scope": refresh_scope,
        "run_date": args.run_date,
        "baseline_date": baseline_date,
        "watchlist": watchlist,
        "custom_prompt": custom_prompt_raw or None,
    }


def _cli_summary(kwargs: dict) -> dict:
    return {
        "cadence": kwargs["cadence"],
        "refresh_scope": kwargs["refresh_scope"],
        "run_type": _legacy_run_type(kwargs["refresh_scope"]),
        "run_date": kwargs["run_date"].isoformat(),
        "baseline_date": (kwargs["baseline_date"].isoformat() if kwargs["baseline_date"] else None),
        "watchlist": list(kwargs["watchlist"]),
    }


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    import json
    import sys

    parser = build_cli_parser()
    args = parser.parse_args(argv)
    kwargs = resolve_cli_inputs(args)

    if args.dry_run:
        # Confirm the graph compiles cleanly, but skip invocation — no LLM calls.
        summary = _cli_summary(kwargs) | {"dry_run": True, "compiled": False}
        try:
            from digiquant.olympus.atlas.phases.preflight import PreflightDeps

            deps = AtlasGraphDeps(preflight=PreflightDeps(client=None, config_loader=None))  # type: ignore[arg-type]
            build_atlas_graph(deps=deps, watchlist=kwargs["watchlist"])
            summary["compiled"] = True
        except Exception as exc:  # pragma: no cover — keep dry-run non-fatal
            summary["compile_error"] = repr(exc)

        json.dump(summary, sys.stdout, default=str)
        sys.stdout.write("\n")
        return 0

    from digiquant.olympus.atlas.phases.preflight import PreflightDeps
    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    atlas_input = AtlasInput(**kwargs)
    client = build_client(SupabaseConfig.from_env())
    deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=_make_default_config_loader(atlas_input.watchlist),
        ),
        publish=PublishDeps(client=client),
        triage=TriageDeps(client=client),
        preflight_reflect=PreflightReflectDeps(client=client),
    )
    graph = build_atlas_graph(deps=deps, watchlist=atlas_input.watchlist)
    state = initial_state(atlas_input)
    # graph.invoke raises on any phase failure; we let exceptions propagate
    # to the CLI so the workflow step exits non-zero and the failure-issue
    # step fires. A successful return here is the only success path.
    graph.invoke(state)
    json.dump({"ok": True, "summary": _cli_summary(kwargs)}, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())
