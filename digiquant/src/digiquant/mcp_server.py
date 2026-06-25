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

    # ── Slapper tearsheet pipeline (price → Nautilus backtest → TradingView parity) ──
    # These wrap the repo's pipeline scripts so the whole flow is MCP-discoverable.
    # Paths are resolved relative to this package (editable/source checkout).
    def _scripts_dir() -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parents[2] / "scripts")

    def _validation_dir() -> str:
        from pathlib import Path

        return str(Path(__file__).resolve().parents[3] / "scripts" / "validation")

    @mcp.tool()
    def digiquant_fetch_coinbase_ohlcv(
        symbols_json: str = '["BTC/USD", "ETH/USD", "SOL/USD"]',
        start: str = "2017-01-01",
        cache_dir: str | None = None,
    ) -> str:
        """Fetch daily OHLCV from Coinbase (CCXT) into the price-history cache.

        ``symbols_json`` is a JSON array of CCXT symbols. Returns JSON mapping each
        ticker to ``{bars, first, last, path}`` (or ``{error}``).
        """
        import sys
        from pathlib import Path

        sd = _scripts_dir()
        if sd not in sys.path:
            sys.path.insert(0, sd)
        try:
            import ccxt
            from fetch_coinbase import DEFAULT_CACHE, SYMBOLS, bars_to_polars, fetch_all_daily
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        cache = Path(cache_dir) if cache_dir else DEFAULT_CACHE
        cache.mkdir(parents=True, exist_ok=True)
        exchange = ccxt.coinbase()
        out: dict[str, Any] = {}
        for sym in json.loads(symbols_json):
            ticker = SYMBOLS.get(sym, sym.replace("/", "-"))
            try:
                bars = fetch_all_daily(exchange, sym, start)
                if not bars:
                    out[ticker] = {"error": "no data"}
                    continue
                df = bars_to_polars(bars, ticker).unique(subset=["timestamp"], keep="last").sort("timestamp")
                path = cache / f"{ticker}.csv"
                df.write_csv(path)
                out[ticker] = {"bars": len(df), "first": df["timestamp"][0],
                               "last": df["timestamp"][-1], "path": str(path)}
            except Exception as exc:  # noqa: BLE001 — surface per-symbol, never crash
                out[ticker] = {"error": f"{type(exc).__name__}: {exc}"}
        return json.dumps(out, indent=2, default=str)

    @mcp.tool()
    def digiquant_generate_slapper_tearsheet(
        strategy: str | None = None,
        cache_dir: str | None = None,
    ) -> str:
        """Run the NautilusTrader backtest for the Slapper family and write TV-style
        tearsheet JSON to the digiquant.io frontend. ``strategy=None`` runs all three.

        Reads structure from ``strategies/settings.json`` (public) and calibrations
        from ``calibrations.json`` (private). Returns the index entries written.
        """
        import sys
        from pathlib import Path

        sd = _scripts_dir()
        if sd not in sys.path:
            sys.path.insert(0, sd)
        try:
            import generate_tearsheets as gt
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

        settings = gt.load_settings()
        cache = Path(cache_dir) if cache_dir else gt.DEFAULT_CACHE
        targets = ({strategy: settings["strategies"][strategy]} if strategy
                   else settings["strategies"])
        results = []
        for strat, cfg in targets.items():
            entry = gt.run_and_write(strat, cfg["symbol"], settings, cache, gt.FRONTEND_STRATEGIES)
            if entry:
                results.append(entry)
        return json.dumps(results, indent=2, default=str)

    @mcp.tool()
    def digiquant_validate_slapper_vs_tradingview(
        strategy: str,
        ohlcv_csv: str,
        tv_export_csv: str,
        start_date: str = "2018-01-01",
    ) -> str:
        """Trade-level parity check of a Slapper strategy against a TradingView
        'List of Trades' CSV export (matches entry date + direction; breaks misses
        down by signal family). Returns match counts and the diff lists as JSON.
        """
        import sys

        vd = _validation_dir()
        if vd not in sys.path:
            sys.path.insert(0, vd)
        try:
            from compare_tv import compare
        except ImportError as exc:
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
        try:
            return json.dumps(compare(strategy, ohlcv_csv, tv_export_csv, start_date), indent=2, default=str)
        except Exception as exc:  # noqa: BLE001 — surface as JSON to the caller
            return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

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
