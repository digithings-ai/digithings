"""DigiQuant MCP server: backtest, optimize, export, strategy catalog.

Run::

    pip install -e "digiquant[mcp]"
    python -m digiquant.mcp_server

Uses the same ``service_*`` functions as the HTTP API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP

    _MCP_AVAILABLE = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_AVAILABLE = False


def _require_mcp() -> type:
    if not _MCP_AVAILABLE:
        raise ImportError("Install mcp: pip install digiquant[mcp]")
    return FastMCP  # type: ignore[return-value]


def create_mcp_server() -> Any:
    _require_mcp()
    mcp = FastMCP("DigiQuant")

    @mcp.tool()
    def digiquant_list_strategies() -> str:
        """List registered strategies (name, aliases, description, default_params)."""
        from digiquant.service import service_list_strategies

        return json.dumps(service_list_strategies(), indent=2)

    @mcp.tool()
    def digiquant_run_backtest(
        strategy_name: str,
        symbols_json: str,
        data_dir: str | None = None,
        data_path: str | None = None,
        strategy_params_json: str | None = None,
    ) -> str:
        """Run a Nautilus backtest. symbols_json is a JSON array e.g. '["AAPL"]'."""
        symbols: list[str] = json.loads(symbols_json)
        params = json.loads(strategy_params_json) if strategy_params_json else None
        from digiquant.service import service_run_backtest

        result = service_run_backtest(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            strategy_params=params,
        )
        return result.model_dump_json(indent=2)

    @mcp.tool()
    def digiquant_run_optimize(
        strategy_name: str,
        symbols_json: str,
        data_dir: str | None = None,
        data_path: str | None = None,
        method: str = "grid",
        n_trials: int = 50,
    ) -> str:
        """Run parameter optimization (grid, bayesian, or random)."""
        symbols: list[str] = json.loads(symbols_json)
        from digiquant.service import service_run_optimize

        result = service_run_optimize(
            strategy_name=strategy_name,
            symbols=symbols,
            data_path=data_path,
            data_dir=data_dir,
            method=method,
            n_trials=n_trials,
        )
        return result.model_dump_json(indent=2)

    @mcp.tool()
    def digiquant_export(
        strategy_name: str,
        target: str,
        params_json: str | None = None,
    ) -> str:
        """Export strategy config (JSON or nautilus_bundle zip). targets: nautilus, nautilus_bundle, …"""
        params = json.loads(params_json) if params_json else {}
        from digiquant.service import service_run_export

        result = service_run_export(
            strategy_name=strategy_name,
            params=params,
            target=target,
        )
        return result.model_dump_json(indent=2)

    @mcp.tool()
    def digiquant_run_pipeline(
        strategy_name: str,
        symbols_json: str,
        data_dir: str | None = None,
        data_path: str | None = None,
        strategy_params_json: str | None = None,
        export_target: str = "nautilus",
        run_optimize: bool = True,
        run_export: bool = True,
        method: str = "grid",
        n_trials: int = 50,
        constraints_json: str | None = None,
    ) -> str:
        """Run validate → backtest → optional optimize → optional export via internal LangGraph.

        Returns JSON with ``trace``, and serialized ``backtest`` / ``optimize`` / ``export`` when run.
        """
        symbols: list[str] = json.loads(symbols_json)
        params = json.loads(strategy_params_json) if strategy_params_json else None
        constraints = json.loads(constraints_json) if constraints_json else None
        from digiquant.graph.pipeline import run_quant_workflow

        raw = run_quant_workflow(
            {
                "strategy_name": strategy_name,
                "symbols": symbols,
                "data_path": data_path,
                "data_dir": data_dir,
                "strategy_params": params,
                "export_target": export_target,
                "run_optimize": run_optimize,
                "run_export": run_export,
                "method": method,
                "n_trials": n_trials,
                "constraints": constraints,
            }
        )
        return json.dumps(raw, indent=2)

    @mcp.tool()
    def digiquant_get_price_technicals(ticker: str, lookback: int = 20) -> str:
        """Latest technical indicators + recent daily window for a ticker (JSON).

        Reads the maintained ``price_technicals`` table in Supabase. Returns
        ``{"error": ...}`` if the data layer is unavailable.
        """
        from digiquant.olympus.atlas.data.queries import get_price_technicals
        from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

        try:
            client = build_client(SupabaseConfig.from_env())
            result = get_price_technicals(client=client, ticker=ticker, lookback=lookback)
        except Exception as exc:  # noqa: BLE001 — surface as JSON to the caller, never crash
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, default=str)

    @mcp.tool()
    def digiquant_get_macro_series(series_ids: list[str], lookback: int = 6) -> str:
        """Latest values + recent window for FRED macro series ids (JSON).

        Reads the maintained ``macro_series_observations`` table in Supabase.
        Returns ``{"error": ...}`` if the data layer is unavailable.
        """
        from digiquant.olympus.atlas.data.queries import get_macro_series
        from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

        try:
            client = build_client(SupabaseConfig.from_env())
            result = get_macro_series(client=client, series_ids=series_ids, lookback=lookback)
        except Exception as exc:  # noqa: BLE001 — surface as JSON to the caller, never crash
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        return json.dumps(result, default=str)

    return mcp


def run_mcp(
    transport: str = "streamable-http",
    host: str = "127.0.0.1",
    port: int = 8767,
) -> None:
    mcp = create_mcp_server()
    logger.info("Starting DigiQuant MCP server on %s:%d (transport=%s)", host, port, transport)
    mcp.run(transport=transport, host=host, port=port)


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
    parser = argparse.ArgumentParser(description="DigiQuant MCP server")
    parser.add_argument("--stdio", action="store_true", help="Use stdio transport (Claude Desktop)")
    parser.add_argument("--host", default=os.environ.get("DIGIQUANT_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("DIGIQUANT_MCP_PORT", "8767"))
    )
    args = parser.parse_args()
    transport = "stdio" if args.stdio else "streamable-http"
    run_mcp(transport=transport, host=args.host, port=args.port)
