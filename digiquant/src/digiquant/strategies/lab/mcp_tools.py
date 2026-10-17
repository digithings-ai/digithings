"""SDCA lab tools, published through the ``digiquant.mcp_tools`` entry point.

A distribution declares its MCP tools under
``[project.entry-points."digiquant.mcp_tools"]``, and the host registers each
declared object on the FastMCP server it is building (``mcp_server.
create_mcp_server`` -> ``plugin.register_plugin_mcp_tools``). This module is the
lab's declaration, so the tools register exactly like an in-tree one: same
``maybe_tool`` decorator, same scope filtering, same refusal list.

``register_mcp_tools(mcp, maybe_tool)`` is the protocol the host calls. The
declared entry point may also be a bare callable, which is why this is a
function taking both arguments rather than an object with a method.

These three tools stay on the default full-scope surface. They are research and
optimization entry points, and the read scope is the customer dashboard-chat
surface, so neither ``READ_SCOPE_TOOLS`` nor ``COMPUTE_TOOLS`` names them and a
``scope="read"`` server does not offer them.

The lab imports sit inside each tool rather than at module import. The plugin
loader is fail-closed: it warns and drops the whole object if importing it
raises, so a module-level engine import that broke would remove the surface
silently, with nothing to read. Importing inside the body keeps registration
independent of the engine and turns a broken engine into a response body.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["TOOL_NAMES", "register_mcp_tools"]

#: The MCP names this plugin registers, in registration order.
TOOL_NAMES: tuple[str, ...] = (
    "lab_list_presets",
    "lab_describe_preset",
    "lab_run_golden_path",
)


def register_mcp_tools(mcp: Any, maybe_tool: Any) -> None:
    """Register the lab tools on ``mcp`` (the ``digiquant.mcp_tools`` protocol)."""

    @maybe_tool("lab_list_presets")
    def lab_list_presets() -> str:
        """List the accumulation/distribution presets the lab can backtest."""
        from digiquant.strategies.lab import presets as _presets

        names = _presets.list_presets()
        return json.dumps({"count": len(names), "presets": names}, indent=2)

    @maybe_tool("lab_describe_preset")
    def lab_describe_preset(name: str) -> str:
        """Describe one preset: its curve nodes, long-only flag and description."""
        from digiquant.strategies.lab import presets as _presets

        try:
            preset = _presets.load_preset(name)
        except Exception as exc:
            return json.dumps(
                {
                    "error": f"{type(exc).__name__}: {exc}",
                    "known": _presets.list_presets(),
                },
                indent=2,
            )
        return json.dumps(
            {
                "name": name,
                "description": preset.description,
                "long_only": preset.long_only,
                "curve_nodes": list(preset.curve_nodes),
            },
            indent=2,
        )

    @maybe_tool("lab_run_golden_path")
    def lab_run_golden_path(
        symbol: str,
        data_dir: str,
        risk_model: str = "btc_power_law",
        preset: str = "balanced",
        initial_cash: float | None = None,
        trials_json: str | None = None,
        with_tearsheet: bool = True,
    ) -> str:
        """Run research -> backtest -> optimize -> tearsheet for one symbol.

        ``symbol`` selects the OHLCV CSV under ``data_dir``. ``trials_json`` is an
        optional JSON array of shape-parameter overrides; when it is given the
        optimize stage runs with the rails fitter for ``risk_model``.

        The response carries the verdict and the backtest caveat: this is the
        curve simulator, not a Nautilus ``BacktestResult``, and the numbers must
        not be read as a published backtest.
        """
        from digiquant.strategies.lab import golden_path as _golden_path

        try:
            trials = json.loads(trials_json) if trials_json else None
            kwargs: dict[str, Any] = {}
            if initial_cash is not None:
                kwargs["initial_cash"] = float(initial_cash)
            if trials is not None:
                kwargs["trials"] = trials
                kwargs["rails_fitter"] = _golden_path.rails_fitter_for(risk_model)
            result = _golden_path.run_golden_path(
                symbols=[symbol],
                data_dir=data_dir,
                risk_model_name=risk_model,
                preset=preset,
                with_tearsheet=bool(with_tearsheet),
                **kwargs,
            )
        except Exception as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"}, indent=2)

        research = result.research
        report = result.backtest.report
        return json.dumps(
            {
                "symbol": symbol,
                "risk_model": risk_model,
                "preset": result.preset_name,
                "range": {
                    "start": str(research.start),
                    "end": str(research.end),
                    "rows": research.row_count,
                    "dropped_warmup_rows": research.dropped_warmup_rows,
                },
                "backtest": {
                    "authoritative": result.backtest.authoritative,
                    "caveat": result.backtest.caveat,
                    "total_return_pct": report.total_return_pct,
                    "vs_flat_dca_pct": report.vs_flat_dca_pct,
                    "max_drawdown_pct": report.dca_max_drawdown_pct,
                },
                "verdict": {
                    "cleared": result.verdict.cleared,
                    "reason": result.verdict.reason,
                },
                "optimize_ran": result.optimize is not None,
                "stages": list(result.stages),
            },
            indent=2,
        )
