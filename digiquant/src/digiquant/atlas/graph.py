"""Compiled Atlas sub-graph — public entry point.

DigiClaw (issue #219) invokes the Atlas pipeline through ``build_atlas_graph``
plus ``AtlasInput``. The contract is deliberately small and stable so the
scheduler never has to know about internal phase structure.

Three graph shapes based on ``run_type``:
- ``baseline`` — full 9-phase pipeline. Preflight → Phase 1 (parallel) →
  Phase 2 → Phase 3 → Phase 4 → Phase 5 (equity → sectors → scorecard) →
  Phase 6 → Phase 7 → Phase 7C (per-ticker) → Phase 7D → Phase 9.
- ``delta`` — same topology, with a triage phase inserted after preflight
  that populates ``state.triage``. Downstream nodes read triage
  in-node and short-circuit carry decisions.
- ``monthly`` — preflight → monthly-synthesis (bypasses the segment layer).

Phase 9 is only wired on baseline + monthly runs per the plan.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Callable  # noqa: F401 — used for LangGraph node shape
from uuid import UUID

from digigraph.graph.pipeline_builder import PipelinePhase, build_pipeline

from digiquant.atlas.phases.phase1_altdata import build_phase1
from digiquant.atlas.phases.phase2_institutional import build_phase2
from digiquant.atlas.phases.phase3_macro import build_phase3
from digiquant.atlas.phases.phase4_assetclass import build_phase4
from digiquant.atlas.phases.phase5_equities import build_phase5
from digiquant.atlas.phases.phase6_consolidate import build_phase6
from digiquant.atlas.phases.phase7_synthesis import build_phase7
from digiquant.hermes.phases.phase7c_analyst import build_phase7c
from digiquant.hermes.phases.phase7cd_debate import build_phase7cd
from digiquant.hermes.phases.phase7d_pm import build_phase7d
from digiquant.hermes.phases.phase9_evolution import Phase9Deps, build_phase9
from digiquant.atlas.phases.phase_monthly import build_phase_monthly
from digiquant.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
    build_preflight_node,
    build_preflight_reflect_node,
)
from digiquant.atlas.phases.publish_phase import PublishDeps, build_publish_phase
from digiquant.atlas.phases.triage_phase import TriageDeps, build_triage_phase
from digiquant.atlas.state import AtlasConfigBundle, AtlasResearchState, RunType


@dataclass(frozen=True)
class AtlasInput:
    """Contract between DigiClaw and the Atlas sub-graph.

    Kept small on purpose — one job's worth of invocation data. The
    watchlist is part of the input (not the state) because Phase 7C's
    fan-out width is determined at graph-compile time; changing the
    watchlist mid-run would require a recompile.
    """

    run_type: RunType
    run_date: date
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
    # Closed-loop reflection deps (#432). Both default to None so the
    # legacy test path (no live DB) keeps compiling without these wired.
    # The CLI threads real instances when SUPABASE creds are present.
    preflight_reflect: PreflightReflectDeps | None = None
    phase9: Phase9Deps | None = None


def build_atlas_graph(
    run_type: RunType,
    *,
    deps: AtlasGraphDeps,
    watchlist: tuple[str, ...] = (),
):
    """Compile and return the StateGraph for ``run_type``.

    Callers:
        >>> graph = build_atlas_graph("baseline", deps=my_deps, watchlist=("AAPL",))
        >>> result = graph.invoke(AtlasResearchState(run_type="baseline", run_date=today))
    """
    preflight_phase = PipelinePhase(
        name="preflight",
        nodes=[_as_node("preflight", build_preflight_node(deps.preflight))],
    )

    if run_type == "monthly":
        phases = [preflight_phase, build_phase_monthly()]
        return build_pipeline(AtlasResearchState, phases)

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

    if run_type == "delta":
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
            *build_phase7c(list(watchlist)),
            # Phase 7C-D Bull/Bear debate (#429). Compile-time upper bound
            # of 1 round matches the default; ``state.config.preferences[
            # "debate_rounds"]`` at runtime controls how many of the wired
            # sub-phases actually call the LLM (1..5 supported). Each
            # ticker gets one bull node + one bear node per round, then
            # one research-manager node at the end.
            *build_phase7cd(list(watchlist), rounds=1),
            *build_phase7d(),
            build_phase9(deps.phase9),  # ``deps.phase9=None`` keeps legacy LLM-only path
        ]
    )
    if deps.publish is not None:
        daily_phases.append(build_publish_phase(deps.publish))
    return build_pipeline(AtlasResearchState, daily_phases)


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
        run_type=atlas_input.run_type,
        run_date=atlas_input.run_date,
        baseline_date=atlas_input.baseline_date,
        config=config or AtlasConfigBundle(watchlist=list(atlas_input.watchlist)),
        custom_prompt=atlas_input.custom_prompt or None,
        **extra,
    )


__all__ = [
    "AtlasGraphDeps",
    "AtlasInput",
    "build_atlas_graph",
    "build_cli_parser",
    "cli_main",
    "initial_state",
    "resolve_cli_inputs",
]


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.atlas.graph …`` by the GitHub Actions
# schedulers (see ``.github/workflows/atlas-*.yml``). The CLI is kept
# intentionally thin: parse flags → resolve baseline → build AtlasInput →
# invoke the compiled graph. Heavy lifting stays in the graph itself.


def _parse_cli_date(value: str):
    from datetime import datetime as _dt

    return _dt.strptime(value, "%Y-%m-%d").date()


# ─── Config-file helpers ─────────────────────────────────────────────────────


def _atlas_config_root():
    """Return Path to digiquant/atlas/config/.

    Resolved from this file's location:
    digiquant/src/digiquant/atlas/graph.py → parents[3] = digiquant/.
    """
    from pathlib import Path

    return Path(__file__).resolve().parents[3] / "atlas" / "config"


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
    except Exception:
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
        return AtlasConfigBundle(
            watchlist=watchlist,
            macro_series=_parse_macro_series_yaml(),
        )

    return _load


def build_cli_parser():
    """Return the argparse parser.

    Exposed for unit tests (``tests/test_cli.py``) to exercise flag
    handling without invoking the graph.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.atlas.graph",
        description="Invoke the Atlas research sub-graph.",
    )
    parser.add_argument(
        "--run-type",
        required=True,
        choices=("baseline", "delta", "monthly"),
        help="Pipeline shape to compile and run.",
    )
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
            "for the latest baseline run. Only meaningful for --run-type delta."
        ),
    )
    parser.add_argument(
        "--watchlist",
        default="",
        help="Comma-separated ticker list. Empty means Phase 7C fan-out is skipped.",
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

    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_SERVICE_KEY"):
        return None

    from digiquant.atlas.supabase_io import SupabaseConfig, build_client

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

    Pure apart from the optional Supabase call behind ``--auto-baseline``;
    ``tests/test_cli.py`` covers both the explicit and auto-baseline
    paths by stubbing that call.
    """
    watchlist = tuple(t.strip() for t in args.watchlist.split(",") if t.strip())
    baseline_date = args.baseline_date

    if args.auto_baseline:
        if args.run_type != "delta":
            raise SystemExit("--auto-baseline only valid with --run-type delta")
        resolved = _auto_resolve_baseline(args.run_date)
        if resolved is None and not args.dry_run:
            raise SystemExit(
                "--auto-baseline could not resolve a baseline date; "
                "is SUPABASE_URL/SUPABASE_SERVICE_KEY set and does "
                "daily_snapshots contain a prior baseline run?"
            )
        baseline_date = resolved

    custom_prompt_raw = (getattr(args, "custom_prompt", "") or "").strip()
    return {
        "run_type": args.run_type,
        "run_date": args.run_date,
        "baseline_date": baseline_date,
        "watchlist": watchlist,
        "custom_prompt": custom_prompt_raw or None,
    }


def _cli_summary(kwargs: dict) -> dict:
    return {
        "run_type": kwargs["run_type"],
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
            from digiquant.atlas.phases.preflight import PreflightDeps

            deps = AtlasGraphDeps(preflight=PreflightDeps(client=None, config_loader=None))  # type: ignore[arg-type]
            build_atlas_graph(kwargs["run_type"], deps=deps, watchlist=kwargs["watchlist"])
            summary["compiled"] = True
        except Exception as exc:  # pragma: no cover — keep dry-run non-fatal
            summary["compile_error"] = repr(exc)

        json.dump(summary, sys.stdout, default=str)
        sys.stdout.write("\n")
        return 0

    from digiquant.atlas.phases.preflight import PreflightDeps
    from digiquant.atlas.supabase_io import SupabaseConfig, build_client

    atlas_input = AtlasInput(**kwargs)
    client = build_client(SupabaseConfig.from_env())
    deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=_make_default_config_loader(atlas_input.watchlist),
        ),
        publish=PublishDeps(client=client) if atlas_input.run_type != "monthly" else None,
        # Triage deps only matter for delta runs; passing them on baseline /
        # monthly is harmless because the triage phase isn't compiled in.
        triage=TriageDeps(client=client) if atlas_input.run_type == "delta" else None,
        # Closed-loop reflection (#432). Wired only on baseline + delta runs;
        # monthly has no daily decisions to resolve. The reflector default
        # (None) inside PreflightReflectDeps falls through to the LiteLLM-
        # backed ``decision-reflector`` skill — see decision_log.py.
        preflight_reflect=(
            PreflightReflectDeps(client=client) if atlas_input.run_type != "monthly" else None
        ),
        phase9=(Phase9Deps(client=client) if atlas_input.run_type != "monthly" else None),
    )
    graph = build_atlas_graph(atlas_input.run_type, deps=deps, watchlist=atlas_input.watchlist)
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
