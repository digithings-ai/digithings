"""digiquant CLI: web_search tooling health checks (no fallbacks)."""

from __future__ import annotations

import click

__all__ = ["web_search"]


@click.group()
def web_search() -> None:
    """web_search tooling health (book-pipeline pre-flight gate)."""


@web_search.command("healthcheck")
@click.option(
    "--timeout",
    "timeout_s",
    type=float,
    default=25.0,
    show_default=True,
    help="Seconds to wait for the single health-check search.",
)
def healthcheck(timeout_s: float) -> None:
    """Prove web_search answers before the pipeline runs (#4198).

    Exits non-zero with a precise diagnostic (tool, endpoint, error, elapsed)
    when the tool is down, rate-limited, timing out, or returning no results.
    """
    from digiquant.research.data.web_search_health import (
        WebSearchHealthError,
        check_web_search_health,
    )

    try:
        health = check_web_search_health(timeout_s=timeout_s)
    except WebSearchHealthError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"web_search ok: endpoint={health.endpoint} results={health.results} "
        f"elapsed={health.elapsed_s:.2f}s"
    )
