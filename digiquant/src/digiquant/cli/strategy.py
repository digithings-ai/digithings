"""`digiquant strategy …` subcommands (#160).

Wraps :func:`digiquant.service.service_list_strategies` — same path as HTTP
``GET /strategies`` and MCP ``digiquant_list_strategies``.
"""

from __future__ import annotations

import json

import click


@click.group()
def strategy() -> None:
    """Discover registered Nautilus strategies."""


def _filter_strategies(query: str) -> list[dict]:
    """Case-insensitive match on name, aliases, or description."""
    from digiquant.service import service_list_strategies

    needle = query.strip().lower()
    if not needle:
        raise click.UsageError("search query must be non-empty.")
    matched: list[dict] = []
    for item in service_list_strategies():
        haystacks = [str(item.get("name") or "")]
        haystacks.extend(str(a) for a in (item.get("aliases") or []))
        haystacks.append(str(item.get("description") or ""))
        if any(needle in h.lower() for h in haystacks):
            matched.append(item)
    return matched


@strategy.command("list")
def strategy_list() -> None:
    """List registered strategies (JSON; same payload as MCP digiquant_list_strategies)."""
    from digiquant.service import service_list_strategies

    click.echo(json.dumps(service_list_strategies(), indent=2))


@strategy.command("search")
@click.argument("query")
def strategy_search(query: str) -> None:
    """Search strategies by name, alias, or description substring."""
    click.echo(json.dumps(_filter_strategies(query), indent=2))


__all__ = ["strategy"]
