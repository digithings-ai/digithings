"""Atlas → Hermes chain orchestrator (ADR-0015).

Atlas research-only → Hermes analyst/debate/PM → ``publish_phase``.
Cron entry point: ``python -m digiquant.olympus.hermes.chain``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from digiquant.olympus.atlas.graph import (
    AtlasGraphDeps,
    AtlasInput,
    build_atlas_graph,
    initial_state,
)

# DESLOP-034: import keeps phase_monthly in module graph for ADR-0015 doc linkage (no lazy split).
from digiquant.olympus.atlas.phases.phase_monthly import build_phase_monthly  # noqa: F401
from digiquant.olympus.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
)
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps, build_publish_phase
from digiquant.olympus.atlas.phases.triage_phase import TriageDeps
from digiquant.olympus.atlas.state import AtlasResearchState
from digiquant.olympus.hermes.graph import HermesGraphDeps, Phase9Deps, build_hermes_graph

__all__ = [
    "ChainDeps",
    "cli_main",
    "run_atlas_then_hermes",
]


@dataclass(frozen=True)
class ChainDeps:
    """Dependencies for the Atlas → Hermes chain.

    Atlas-side deps (preflight, triage, preflight-reflect) come from
    :class:`AtlasGraphDeps`. Hermes-side deps (phase9 reflection write)
    come from :class:`HermesGraphDeps`. The terminal ``publish``
    :class:`PublishDeps` is shared — one Supabase client writes
    everything at the end.
    """

    atlas: AtlasGraphDeps
    hermes: HermesGraphDeps
    publish: PublishDeps | None = None


def run_atlas_then_hermes(
    *,
    atlas_input: AtlasInput,
    deps: ChainDeps,
    debate_rounds: int = 1,
) -> AtlasResearchState:
    """Compose Atlas → Hermes → publish, return the final state.

    ``deps.atlas.publish`` is overridden to ``None`` for the Atlas pass —
    publish runs once at the very end with the full populated state.
    """
    # Atlas: research only, no publish.
    atlas_deps = AtlasGraphDeps(
        preflight=deps.atlas.preflight,
        publish=None,  # chain handles publish at the end
        triage=deps.atlas.triage,
        preflight_reflect=deps.atlas.preflight_reflect,
    )
    atlas_graph = build_atlas_graph(
        atlas_input.run_type, deps=atlas_deps, watchlist=atlas_input.watchlist
    )
    state = initial_state(atlas_input)
    state = atlas_graph.invoke(state)

    # Monthly runs end at Atlas's phase_monthly. No Hermes, no terminal
    # publish (phase_monthly handles its own output shape).
    if atlas_input.run_type == "monthly":
        return state

    # Hermes: analysis, debate, PM, reflection.
    hermes_graph = build_hermes_graph(
        watchlist=list(atlas_input.watchlist),
        deps=deps.hermes,
        debate_rounds=debate_rounds,
    )
    state = hermes_graph.invoke(state)

    # Terminal publish — single pass over the fully populated state.
    if deps.publish is not None:
        from digiquant.olympus.hermes.pipeline_builder import build_pipeline

        publish_only = [build_publish_phase(deps.publish)]
        # Re-use the same state model + pipeline machinery for consistency.
        publish_graph = build_pipeline(AtlasResearchState, publish_only)
        state = publish_graph.invoke(state)

    return state


# ─── CLI entry point ────────────────────────────────────────────────────────
#
# Invoked as ``python -m digiquant.olympus.hermes.chain --run-type baseline …`` by
# the cron workflows (atlas-baseline.yml / atlas-delta.yml /
# atlas-monthly.yml). Mirrors the old ``python -m digiquant.olympus.atlas.graph``
# CLI surface so the workflow YAML diff stays minimal.


def _parse_cli_date(value: str) -> date:
    from datetime import datetime as _dt

    return _dt.strptime(value, "%Y-%m-%d").date()


def _build_cli_parser():
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m digiquant.olympus.hermes.chain",
        description="Run Atlas → Hermes end-to-end (research + analysis + PM + reflection).",
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
        help="Resolve --baseline-date from Supabase (delta runs only).",
    )
    parser.add_argument(
        "--watchlist",
        default="",
        help="Comma-separated ticker list. Empty means Phase 7C fan-out is skipped.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve inputs + compile graphs, print summary, exit 0 (no LLM calls).",
    )
    parser.add_argument(
        "--custom-prompt",
        default="",
        help=(
            "Optional one-off research prompt (#313). When set, Phase 7 synthesis "
            "includes the prompt as additional context."
        ),
    )
    return parser


def cli_main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    import json
    import sys

    # Re-use Atlas's CLI helpers — they already handle --auto-baseline,
    # watchlist parsing, summary formatting.
    from digiquant.olympus.atlas.graph import _make_default_config_loader, resolve_cli_inputs

    parser = _build_cli_parser()
    args = parser.parse_args(argv)
    kwargs = resolve_cli_inputs(args)
    atlas_input = AtlasInput(**kwargs)

    summary = {
        "run_type": atlas_input.run_type,
        "run_date": atlas_input.run_date.isoformat(),
        "baseline_date": (
            atlas_input.baseline_date.isoformat() if atlas_input.baseline_date else None
        ),
        "watchlist": list(atlas_input.watchlist),
    }

    if args.dry_run:
        # Compile both graphs cleanly, no invocation.
        compiled = {"atlas": False, "hermes": False}
        try:
            atlas_deps = AtlasGraphDeps(
                preflight=PreflightDeps(client=None, config_loader=None)  # type: ignore[arg-type]
            )
            build_atlas_graph(
                atlas_input.run_type, deps=atlas_deps, watchlist=atlas_input.watchlist
            )
            compiled["atlas"] = True
            if atlas_input.run_type != "monthly":
                build_hermes_graph(watchlist=list(atlas_input.watchlist))
                compiled["hermes"] = True
        except Exception as exc:  # pragma: no cover
            summary["compile_error"] = repr(exc)
        json.dump({**summary, "dry_run": True, "compiled": compiled}, sys.stdout, default=str)
        sys.stdout.write("\n")
        return 0

    from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

    client = build_client(SupabaseConfig.from_env())
    atlas_deps = AtlasGraphDeps(
        preflight=PreflightDeps(
            client=client,
            config_loader=_make_default_config_loader(atlas_input.watchlist),
        ),
        publish=None,  # chain handles publish at the end
        triage=TriageDeps(client=client) if atlas_input.run_type == "delta" else None,
        preflight_reflect=(
            PreflightReflectDeps(client=client) if atlas_input.run_type != "monthly" else None
        ),
    )
    hermes_deps = HermesGraphDeps(
        phase9=(Phase9Deps(client=client) if atlas_input.run_type != "monthly" else None),
    )
    chain_deps = ChainDeps(
        atlas=atlas_deps,
        hermes=hermes_deps,
        publish=PublishDeps(client=client) if atlas_input.run_type != "monthly" else None,
    )
    run_atlas_then_hermes(atlas_input=atlas_input, deps=chain_deps)

    json.dump({"ok": True, "summary": summary}, sys.stdout, default=str)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(cli_main())
