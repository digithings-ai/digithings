"""digiquant plugin surface (repo-split 1.2, DIG-3691).

Contract between the public ``digiquant`` core (R0, staying open) and the
private ``digiquant-strategies`` distribution (R1, proprietary strategies +
optimiser + SDCA MCP/CLI). R1 imports from public ``digiquant``; without a
declared surface any R0 refactor breaks R1 silently.

Three entry-point groups (semver-guaranteed):

- ``digiquant.strategies`` — strategy discovery. The loaded object is either
  a callable ``register(register_fn)`` or an object with a
  ``register_strategies(register_fn)`` method. ``register_fn`` is
  :func:`digiquant.strategies.registry.register`.
- ``digiquant.mcp_tools`` — SDCA MCP tools. The loaded object is either a
  callable ``(mcp, maybe_tool) -> None`` or an object with a
  ``register_mcp_tools(mcp, maybe_tool)`` method. ``mcp`` is the FastMCP
  server under construction; ``maybe_tool`` is the scope/entitlement-aware
  decorator used by :func:`digiquant.mcp_server.create_mcp_server`.
- ``digiquant.cli`` — SDCA CLI subcommands. The loaded object is either a
  callable ``(main) -> None`` (a click group callback adding subcommands) or
  an object with a ``register_cli(main)`` method.

SDCA functional seams (same three groups, no new group): the optimiser
(``optimize._run_sdca_optimize``), the power-law fitter inside
``mcp_server.digiquant_fit_btc_power_law``, and the tearsheet script's
``materialize_sdca_risk_index`` each consult the plugin first and fall back
to the in-tree implementation while R1 still lives in this repo. After the
split the fallback goes away and the hook is the only path.

R0 CI runs a dummy-plugin conformance test
(``tests/dq/test_digiquant_plugin.py``); R1 CI runs nightly against
``digiquant@main``.

Discovery is fail-closed: a broken entry point warns and is skipped, never
raising into the caller.
"""

from __future__ import annotations

import warnings
from typing import Any, Callable

STRATEGIES_GROUP = "digiquant.strategies"
MCP_TOOLS_GROUP = "digiquant.mcp_tools"
CLI_GROUP = "digiquant.cli"

__all__ = [
    "STRATEGIES_GROUP",
    "MCP_TOOLS_GROUP",
    "CLI_GROUP",
    "discover",
    "register_plugin_strategies",
    "register_plugin_mcp_tools",
    "register_plugin_cli",
    "register_chart",
    "get_chart",
    "list_charts",
    "get_sdca_optimize_hook",
    "get_power_law_hook",
    "get_risk_index_hook",
]


def discover(group: str) -> list:
    """Return the entry points declared for ``group`` (possibly empty).

    Never raises: metadata errors yield ``[]``.
    """
    try:
        from importlib import metadata as _metadata
    except ImportError:  # pragma: no cover — Python >=3.8 always has this
        return []
    try:
        eps = _metadata.entry_points(group=group)
    except TypeError:
        # Older API: entry_points() takes no group kwarg.
        try:
            all_eps = _metadata.entry_points()
            eps = [ep for ep in all_eps if ep.group == group]
        except Exception:
            return []
    except Exception:
        return []
    try:
        return list(eps)
    except Exception:
        return []


def _load(ep: Any) -> Any | None:
    try:
        return ep.load()
    except Exception as exc:  # fail-closed: warn, skip
        warnings.warn(f"digiquant.plugin: skipping broken entry point {ep!r}: {exc}")
        return None


def register_plugin_strategies(register_fn: Callable[..., None]) -> int:
    """Register every ``digiquant.strategies`` plugin. Returns count registered."""
    count = 0
    for ep in discover(STRATEGIES_GROUP):
        obj = _load(ep)
        if obj is None:
            continue
        try:
            if callable(obj):
                obj(register_fn)
            elif hasattr(obj, "register_strategies"):
                obj.register_strategies(register_fn)
            else:
                warnings.warn(
                    f"digiquant.plugin: entry point {ep!r} has no "
                    "register(register_fn) protocol"
                )
                continue
            count += 1
            _register_plugin_charts(obj)
        except Exception as exc:
            warnings.warn(f"digiquant.plugin: strategy plugin {ep!r} failed: {exc}")
    return count


def register_plugin_mcp_tools(mcp: Any, maybe_tool: Any) -> int:
    """Register every ``digiquant.mcp_tools`` plugin. Returns count registered."""
    count = 0
    for ep in discover(MCP_TOOLS_GROUP):
        obj = _load(ep)
        if obj is None:
            continue
        try:
            if callable(obj):
                obj(mcp, maybe_tool)
            elif hasattr(obj, "register_mcp_tools"):
                obj.register_mcp_tools(mcp, maybe_tool)
            else:
                warnings.warn(
                    f"digiquant.plugin: entry point {ep!r} has no "
                    "register_mcp_tools(mcp, maybe_tool) protocol"
                )
                continue
            count += 1
        except Exception as exc:
            warnings.warn(f"digiquant.plugin: MCP plugin {ep!r} failed: {exc}")
    return count


def register_plugin_cli(main: Any) -> int:
    """Register every ``digiquant.cli`` plugin onto the click group. Returns count."""
    count = 0
    for ep in discover(CLI_GROUP):
        obj = _load(ep)
        if obj is None:
            continue
        try:
            if callable(obj):
                obj(main)
            elif hasattr(obj, "register_cli"):
                obj.register_cli(main)
            else:
                warnings.warn(
                    f"digiquant.plugin: entry point {ep!r} has no "
                    "register_cli(main) protocol"
                )
                continue
            count += 1
        except Exception as exc:
            warnings.warn(f"digiquant.plugin: CLI plugin {ep!r} failed: {exc}")
    return count


# ---------------------------------------------------------------------------
# Chart seam (charts/sdca.py travels with R1; same distribution as strategies)
# ---------------------------------------------------------------------------

_CHARTS: dict[str, Any] = {}


def register_chart(name: str, builder: Any) -> None:
    """Register a chart builder by name (SDCA diagnostic figures)."""
    _CHARTS[name] = builder


def get_chart(name: str) -> Any | None:
    """Return the chart builder registered under ``name``, if any."""
    return _CHARTS.get(name)


def list_charts() -> list[str]:
    """Return the sorted names of registered chart builders."""
    return sorted(_CHARTS)


def _register_plugin_charts(obj: Any) -> None:
    """Let a strategy plugin contribute chart builders (optional protocol)."""
    registrar = getattr(obj, "register_charts", None)
    if registrar is None:
        return
    try:
        registrar(register_chart)
    except Exception as exc:
        warnings.warn(f"digiquant.plugin: chart registration failed: {exc}")


# ---------------------------------------------------------------------------
# SDCA functional hooks (optimiser, power-law fitter, risk-index builder)
# ---------------------------------------------------------------------------


def _first_attr(attr: str) -> Any | None:
    """Return the first ``attr`` found on any strategy plugin, else None."""
    for ep in discover(STRATEGIES_GROUP):
        obj = _load(ep)
        if obj is None:
            continue
        target = getattr(obj, attr, None)
        if target is not None:
            return target
    return None


def get_sdca_optimize_hook() -> Any | None:
    """Return a plugin ``run_sdca_optimize`` callable, if any plugin provides one."""
    return _first_attr("run_sdca_optimize")


def get_power_law_hook() -> Any | None:
    """Return a plugin ``(fit_btc_power_law, save_coefficients)`` pair provider.

    A strategy plugin may expose ``power_law_fns() -> (fit, save)``. Returns
    the pair, or None when no plugin provides it (caller falls back to the
    in-tree ``strategies.sdca.btc_power_law`` implementation).
    """
    provider = _first_attr("power_law_fns")
    if provider is None:
        return None
    try:
        return provider()
    except Exception as exc:
        warnings.warn(f"digiquant.plugin: power_law_fns failed: {exc}")
        return None


def get_risk_index_hook() -> Any | None:
    """Return a plugin ``materialize_sdca_risk_index`` callable, if any."""
    return _first_attr("materialize_sdca_risk_index")
