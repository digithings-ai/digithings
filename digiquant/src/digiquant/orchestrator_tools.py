"""OpenAI-style orchestrator tool definitions for digiquant.

digigraph fetches these via ``POST /v1/orchestrator_tools`` and executes via
``POST /v1/orchestrator_invoke`` so quant tooling is owned by this service.
"""

from __future__ import annotations

from typing import Any


def _pipeline_parameters() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "strategy_name": {"type": "string", "description": "Registered strategy name"},
            "symbols": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Ticker symbols",
            },
            "data_path": {"type": "string", "description": "Single OHLCV CSV path (optional)"},
            "data_dir": {"type": "string", "description": "Directory of {SYMBOL}.csv (optional)"},
            "strategy_params": {"type": "object", "description": "Optional initial params"},
            "export_target": {"type": "string", "description": "e.g. nautilus"},
            "run_optimize": {"type": "boolean", "default": True},
            "run_export": {"type": "boolean", "default": True},
            "method": {"type": "string", "default": "grid"},
            "n_trials": {"type": "integer", "default": 50},
            "constraints": {"type": "object", "description": "OptimizationConstraints fields"},
        },
        "required": ["strategy_name", "symbols"],
    }


def build_digiquant_list_strategies_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_list_strategies",
            "description": "List registered Nautilus strategies (name, aliases, description, default_params).",
            "parameters": {"type": "object", "properties": {}},
        },
    }


def build_digiquant_run_backtest_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_backtest",
            "description": "Run a Nautilus backtest for a strategy and symbols. Requires data_path or data_dir.",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                    "data_path": {"type": "string"},
                    "data_dir": {"type": "string"},
                    "strategy_params": {"type": "object"},
                    "tearsheet_path": {"type": "string"},
                    "full_tearsheet": {"type": "boolean", "default": True},
                },
                "required": ["strategy_name", "symbols"],
            },
        },
    }


def build_digiquant_run_optimize_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_optimize",
            "description": (
                "Run parameter optimization (grid, bayesian, random). "
                "strategy_name='sdca' is Stage B walk-forward (vs-flat-DCA); "
                "freeze Stage A weights via strategy_params *_weight keys. "
                "Requires data_path or data_dir."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "symbols": {"type": "array", "items": {"type": "string"}},
                    "data_path": {"type": "string"},
                    "data_dir": {"type": "string"},
                    "param_grid": {"type": "array", "items": {"type": "object"}},
                    "method": {"type": "string", "default": "grid"},
                    "n_trials": {"type": "integer", "default": 50},
                    "objective": {"type": "string", "default": "sharpe"},
                    "constraints": {"type": "object"},
                    "strategy_params": {
                        "type": "object",
                        "description": (
                            "Base/frozen params. For sdca Stage B, pass "
                            "valuation_weight / weekly_rsi_weight / ... from "
                            "digiquant_fit_sdca_weights.regularized_weight_params."
                        ),
                    },
                },
                "required": ["strategy_name", "symbols"],
            },
        },
    }


def build_digiquant_run_export_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_export",
            "description": "Export strategy + params to a target artifact (e.g. nautilus).",
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_name": {"type": "string"},
                    "params": {"type": "object", "description": "Best params from optimize"},
                    "target": {"type": "string", "default": "nautilus"},
                },
                "required": ["strategy_name"],
            },
        },
    }


def build_digiquant_run_pipeline_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_run_pipeline",
            "description": "Run validate → backtest → optional optimize → optional export via internal LangGraph pipeline.",
            "parameters": _pipeline_parameters(),
        },
    }


def build_digiquant_pipeline_delegate_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_pipeline_delegate",
            "description": "digigraph hub alias for digiquant_run_pipeline (same HTTP /v1/workflow behavior).",
            "parameters": _pipeline_parameters(),
        },
    }


def build_digiquant_fetch_coinbase_ohlcv_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fetch_coinbase_ohlcv",
            "description": (
                "Fetch OHLCV from Coinbase (CCXT) into the price-history "
                "cache. Any Coinbase spot pair, any supported timeframe. "
                "Fail-soft per symbol."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols_json": {
                        "type": "string",
                        "description": 'JSON array of CCXT symbols, e.g. ["BTC/USD"]',
                    },
                    "start": {"type": "string"},
                    "end": {
                        "type": "string",
                        "description": "End date (YYYY-MM-DD); defaults to now",
                    },
                    "timeframe": {
                        "type": "string",
                        "description": "CCXT timeframe: 1m,5m,15m,30m,1h,2h,6h,1d (default 1d)",
                    },
                    "through_yesterday": {
                        "type": "boolean",
                        "description": "Drop today's incomplete UTC bar (only meaningful for timeframe=1d)",
                    },
                    "cache_dir": {"type": "string"},
                },
            },
        },
    }


def build_digifetch_quote_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_quote",
            "description": (
                "Latest quote for one listing via Gloomberb Cloud (anonymous; "
                "enrichment only — free-tier data is delayed up to 15 minutes). "
                "Default-ON behind the GLOOMBERB_ENABLED kill switch. Payload "
                "carries 'Sourced from Gloomberb' attribution and a term.gloom.sh "
                "deep link. Refs #4069."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker, e.g. 'AAPL'"},
                    "exchange": {
                        "type": "string",
                        "description": "Optional venue, e.g. 'NASDAQ'/'LSE'",
                    },
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_quotes_batch_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_quotes_batch",
            "description": (
                "Batch quotes for 1-20 listings (Gloomberb Cloud, anonymous). "
                "Per-item status/stale preserved: a stale listing is a null quote "
                "with a reason code, not a failed batch."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "1-20 ticker symbols",
                    },
                },
                "required": ["symbols"],
            },
        },
    }


def build_digifetch_price_history_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_price_history",
            "description": (
                "OHLCV bars for one listing (Gloomberb Cloud). Caps per "
                "resolution: 5m→1wk, 15m→1mo, 1h→3mo, 1d→5y (default), "
                "1wk→5y, 1mo→all-time; out-of-contract requests return typed "
                "invalid_input (never clamped). For windows beyond the caps "
                "(e.g. 1wk back to 2015) pass start_date/end_date (ISO "
                "YYYY-MM-DD, mutually exclusive with range) — the request is "
                "sent as rangeKey=ALL + startDate/endDate. Only the 1wk "
                "window is probe-verified; intraday windows are allowed but "
                "upstream-unverified."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "resolution": {
                        "type": "string",
                        "enum": ["1m", "5m", "15m", "30m", "1h", "1d", "1wk", "1mo"],
                    },
                    "range": {
                        "type": "string",
                        "enum": ["1D", "1W", "1M", "3M", "6M", "1Y", "5Y", "ALL"],
                        "description": "Defaults to 5Y for resolution=1d only",
                    },
                    "start_date": {
                        "type": "string",
                        "description": (
                            "ISO YYYY-MM-DD window start; mutually exclusive "
                            "with range, widens past the resolution cap"
                        ),
                    },
                    "end_date": {
                        "type": "string",
                        "description": ("ISO YYYY-MM-DD window end; mutually exclusive with range"),
                    },
                    "exchange": {"type": "string"},
                },
                "required": ["symbol", "resolution"],
            },
        },
    }


def build_digifetch_ticker_financials_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_ticker_financials",
            "description": (
                "Quote, profile, fundamentals, statements, and price history "
                "(Gloomberb Cloud). extended_statements=true requests the "
                "SEC-sourced extended statement history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "exchange": {"type": "string"},
                    "extended_statements": {"type": "boolean", "default": False},
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_options_chain_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_options_chain",
            "description": (
                "Options chain for one listing (Gloomberb Cloud). Calls/puts are "
                "normalized to a side field per contract; the free-tier delay is "
                "reported in data.delay_note."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "exchange": {"type": "string"},
                    "expiration": {
                        "type": "integer",
                        "description": "Optional expiration in epoch seconds (all expirations when omitted)",
                    },
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_sec_filings_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_sec_filings",
            "description": (
                "SEC filings, filing documents, or filing content (Gloomberb "
                "Cloud /cloud/sec; anonymous, live-verified 200). what=documents/"
                "content require cik + accession from an earlier filings lookup. "
                "Cross-check vs direct EDGAR, not a replacement."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "what": {
                        "type": "string",
                        "enum": ["filings", "documents", "content"],
                        "default": "filings",
                    },
                    "count": {"type": "integer", "default": 15},
                    "cik": {"type": "string"},
                    "accession": {"type": "string"},
                    "form": {"type": "string"},
                },
                "required": ["ticker"],
            },
        },
    }


def build_digifetch_holders_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_holders",
            "description": (
                "Holder records for one symbol (Gloomberb Cloud; session-gated). "
                "Requires GLOOMBERB_SESSION_COOKIE — without it the envelope is a "
                "typed auth_required error. owner_type filters client-side."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "owner_type": {
                        "type": "string",
                        "enum": ["all", "insider", "institution", "fund", "direct"],
                        "default": "all",
                    },
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_analyst_research_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_analyst_research",
            "description": (
                "Analyst recommendation, price target, and rating actions "
                "(Gloomberb Cloud; session-gated). Requires "
                "GLOOMBERB_SESSION_COOKIE — typed auth_required without it."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_corporate_actions_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_corporate_actions",
            "description": (
                "Dividends, splits, and earnings history for one symbol "
                "(Gloomberb Cloud; session-gated). Requires "
                "GLOOMBERB_SESSION_COOKIE — typed auth_required without it. "
                "One kind-discriminated action list."
            ),
            "parameters": {
                "type": "object",
                "properties": {"symbol": {"type": "string"}},
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_earnings_calendar_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_earnings_calendar",
            "description": (
                "Upcoming earnings dates for 1-20 symbols (Yahoo via yfinance; "
                "no Cloud route). horizon_days bounds the window from today; "
                "fail-soft per symbol (throttled symbols land in warnings)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {"type": "array", "items": {"type": "string"}},
                    "horizon_days": {"type": "integer", "default": 90},
                },
                "required": ["symbols"],
            },
        },
    }


def build_digifetch_exchange_rate_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_exchange_rate",
            "description": (
                "USD exchange rate for an ISO-4217 currency (Gloomberb Cloud). "
                "The Cloud route is USD-based (to_currency must be USD); the "
                "15-minute delay is data.delay_note, kept distinct from stale."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "from_currency": {"type": "string", "description": "ISO-4217, e.g. 'EUR'"},
                    "to_currency": {"type": "string", "default": "USD"},
                },
                "required": ["from_currency"],
            },
        },
    }


def build_digifetch_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_search",
            "description": (
                "Search listings across venues (Gloomberb Cloud, anonymous). "
                "limit is >=1; values above the wrapper cap of 10 are clamped "
                "to 10 and flagged via data.limit_clamped. Results keep "
                "symbol/exchange per row so the caller can pick a listing "
                "before quote/history."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "description": "Clamped to 10 (with data.limit_clamped=true) when larger",
                    },
                },
                "required": ["query"],
            },
        },
    }


def build_digifetch_news_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_news",
            "description": (
                "Aggregated market news headlines (Gloomberb Cloud, anonymous). "
                "feed selects latest/top/breaking/ticker/sector/topic; ticker "
                "filters the ticker feed; story_id fetches one story by id."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feed": {
                        "type": "string",
                        "enum": ["latest", "top", "breaking", "ticker", "sector", "topic"],
                        "default": "latest",
                    },
                    "ticker": {"type": "string"},
                    "story_id": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    }


def build_digifetch_econ_calendar_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_econ_calendar",
            "description": (
                "Structured economic calendar (Gloomberb Cloud, anonymous). The "
                "route returns a fixed-size window (~105 rows; upstream ignores "
                "limit), so the tool takes no parameters. Rows carry "
                "date/time/country/event/actual/forecast/prior/impact; wire "
                "prints may be numeric or text (e.g. '3.2%'). Enrichment only: "
                "the platform's data is delayed and is never a pipeline primary."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    }


def build_digifetch_econ_series_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_econ_series",
            "description": (
                "FRED-style macro series observations + metadata (Gloomberb "
                "Cloud, anonymous). series_id is the FRED id (e.g. CPIAUCSL); "
                "sort_order is asc/desc. Missing prints (FRED '.') map to null."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "series_id": {
                        "type": "string",
                        "description": "FRED series id, e.g. 'CPIAUCSL'",
                    },
                    "limit": {"type": "integer", "default": 100},
                    "sort_order": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                },
                "required": ["series_id"],
            },
        },
    }


def build_digifetch_yield_curve_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_yield_curve",
            "description": (
                "Treasury yield-curve tenors (Gloomberb Cloud, anonymous). "
                "Each point carries maturity/maturityYears/yield/asOf/stale; "
                "any stale tenor folds into the envelope stale flag."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    }


def build_digifetch_cds_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_cds",
            "description": (
                "DTCC PPD CDS trade tape (Gloomberb Cloud, anonymous). days is "
                "bounded 1-90 and validated client-side (out-of-range is typed "
                "invalid_input, no request). issuer/limit filter the tape; "
                "trade rows preserve unknown fields."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "issuer": {"type": "string", "description": "Optional issuer name filter"},
                    "days": {"type": "integer", "default": 30, "minimum": 1, "maximum": 90},
                    "limit": {"type": "integer", "default": 100},
                },
            },
        },
    }


def build_digifetch_research_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_research_search",
            "description": (
                "Full-text research search across transcripts/news/filings "
                "(Gloomberb Cloud; session-gated). Requires "
                "GLOOMBERB_SESSION_COOKIE — 401 without it maps to typed "
                "auth_required. Hits carry docType/ticker/title/url/snippet; "
                "offset/limit page the result and data.pagination returns "
                "total/hasMore/nextOffset/countCapped. Enrichment only: the "
                "platform's data is delayed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                    "offset": {"type": "integer", "default": 0, "minimum": 0},
                },
                "required": ["query"],
            },
        },
    }


def build_digifetch_congress_trades_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_congress_trades",
            "description": (
                "US House disclosure trades (Gloomberb Cloud, anonymous). The "
                "upstream OCR dependency is currently failing (HTTP 500, "
                "Mistral monthly spend cap) and surfaces as typed "
                "upstream_error; exposed so coverage completes when upstream "
                "recovers. year/limit filter the tape."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer", "description": "Optional disclosure year filter"},
                    "limit": {"type": "integer", "default": 50},
                },
            },
        },
    }


def build_digifetch_transcripts_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_transcripts",
            "description": (
                "Earnings-call transcripts (Gloomberb Cloud; session-gated, "
                "requires Gloomberb Pro). Requires GLOOMBERB_SESSION_COOKIE and "
                "a Pro plan — a free session's 'Pro plan required' body maps to "
                "typed pro_required, never an empty success. ticker lists a "
                "listing's calls; transcript_id (from a list row) fetches one "
                "call's detail — provide exactly one. Adds a term.gloom.sh "
                "deep link for ticker."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                    "transcript_id": {"type": "string"},
                },
            },
        },
    }


def build_digifetch_statements_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_statements",
            "description": (
                "Annual/quarterly financial statement rows (Gloomberb Cloud; "
                "session-gated). Requires GLOOMBERB_SESSION_COOKIE — without it "
                "the call is a typed auth_required with no request. period is "
                "annual|quarterly|both; rows carry date/currency plus common "
                "line items (extras preserve the rest). Enrichment only: the "
                "platform's data is delayed and is never a pipeline primary."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "period": {
                        "type": "string",
                        "enum": ["annual", "quarterly", "both"],
                        "default": "annual",
                    },
                    "exchange": {"type": "string"},
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_ticker_tweets_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_ticker_tweets",
            "description": (
                "Recent X/Twitter posts mentioning one ticker (Gloomberb Cloud; "
                "session-gated). Requires GLOOMBERB_SESSION_COOKIE. The "
                "upstream applies neither limit nor hours, so the client drops "
                "rows older than now - hours when hours is given, slices to "
                "limit, and reports total_available/truncated. Social posts are "
                "delayed and best-effort — pair with a live web search when "
                "recency matters. Adds a term.gloom.sh deep link for ticker."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer", "default": 50},
                    "hours": {
                        "type": "integer",
                        "description": "Optional lookback window in hours",
                    },
                    "include_replies": {"type": "boolean", "default": False},
                },
                "required": ["ticker"],
            },
        },
    }


def build_digifetch_tweet_search_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_tweet_search",
            "description": (
                "Search X/Twitter posts by query (Gloomberb Cloud; "
                "session-gated). Requires GLOOMBERB_SESSION_COOKIE. query_type "
                "is Latest|Top; the upstream applies neither limit nor hours, "
                "so the client drops rows older than now - hours when hours is "
                "given, slices to limit, and reports total_available/truncated. "
                "Social search is delayed and best-effort — pair with a live "
                "web search when recency matters."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "query_type": {
                        "type": "string",
                        "enum": ["Latest", "Top"],
                        "default": "Latest",
                    },
                    "limit": {"type": "integer", "default": 50},
                    "hours": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    }


def build_digifetch_venues_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_venues",
            "description": (
                "Exchange venue metadata (Gloomberb Cloud, anonymous). No "
                "parameters; rows carry mic/name/title/country/timezone plus "
                "session clock fields (isOpen, timeToOpenSeconds, ...). "
                "Enrichment only."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    }


def build_digifetch_screener_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_screener",
            "description": (
                "Market screener for gainers/losers/most-active (Gloomberb "
                "Cloud; **requires Gloomberb Pro**). Requires "
                "GLOOMBERB_SESSION_COOKIE and a Pro plan — a free session's "
                "HTTP 200 status=unsupported + reasonCode=PRO_REQUIRED (or a "
                "402 'Pro plan required' body) maps to typed pro_required, "
                "never not_found. count is 1-50; mode is cache-first|refresh. "
                "Prices are delayed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["gainers", "losers", "most-active"],
                    },
                    "count": {
                        "type": "integer",
                        "default": 25,
                        "minimum": 1,
                        "maximum": 50,
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["cache-first", "refresh"],
                        "default": "cache-first",
                    },
                },
                "required": ["category"],
            },
        },
    }


def build_digifetch_13f_funds_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_13f_funds",
            "description": (
                "13F fund lookup (Gloomberb Cloud, anonymous). what=search "
                "(query -> name), what=top (quarter in the live 2026Q2 form), "
                "what=tickers (list -> tickers=A,B), what=holders (cusip + "
                "period_of_report). Live-verified for search/top/tickers; the "
                "holders route currently answers an upstream 400 for every "
                "period format probed. SEC filing data is cached/delayed — "
                "cross-check against EDGAR for decisions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "enum": ["search", "top", "tickers", "holders"],
                    },
                    "query": {"type": "string", "description": "what=search fund name"},
                    "quarter": {"type": "string", "description": "what=top, e.g. '2026Q2'"},
                    "tickers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "what=tickers, 1-50 symbols",
                    },
                    "cusip": {"type": "string", "description": "what=holders CUSIP"},
                    "period_of_report": {"type": "string", "description": "what=holders period"},
                    "limit": {"type": "integer", "default": 25},
                    "offset": {"type": "integer", "default": 0, "minimum": 0},
                },
                "required": ["what"],
            },
        },
    }


def build_digifetch_13f_holdings_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_13f_holdings",
            "description": (
                "13F filings / fund forms / one form's holdings (Gloomberb "
                "Cloud, anonymous). what=filings (from_date+to_date, ISO "
                "YYYY-MM-DD), what=forms (cik), what=form "
                "(cik+accession_number). cik is zero-padded to 10 digits and "
                "accession_number is normalized to the dashed form "
                "client-side; malformed dates/accessions are typed "
                "invalid_input with no request. An upstream 13F rejection "
                "proxied as a 5xx (Forms13F 4xx body) maps to non-retryable "
                "invalid_input without opening the circuit breaker. Holding "
                "rows map to issuer/shares/share_type plus voting-authority "
                "columns; form computes has_more from a full page (the "
                "upstream caps one form at 20,000 rows, MAX_FORM_ROWS). SEC "
                "filing data is cached/delayed — cross-check against EDGAR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "what": {
                        "type": "string",
                        "enum": ["filings", "forms", "form"],
                    },
                    "cik": {"type": "string"},
                    "accession_number": {"type": "string"},
                    "from_date": {"type": "string", "description": "what=filings ISO date"},
                    "to_date": {"type": "string", "description": "what=filings ISO date"},
                    "limit": {"type": "integer", "default": 50},
                    "offset": {"type": "integer", "default": 0, "minimum": 0},
                },
                "required": ["what"],
            },
        },
    }


def build_digifetch_shiller_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_shiller",
            "description": (
                "Robert Shiller's monthly valuation series (Gloomberb Cloud, "
                "anonymous). Returns the most recent limit rows (default 240; "
                "the full series is ~1869 rows from 1871) with price/dividend/"
                "earnings/CPI/long-rate plus CAPE and excess CAPE yield; "
                "total_available/truncated report the tail slice. Long-run "
                "reference data (monthly cadence), not intraday."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 240, "minimum": 1, "maximum": 2000},
                },
            },
        },
    }


def build_digifetch_proxy_statements_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_proxy_statements",
            "description": (
                "Executive-compensation proxy statements (Gloomberb Cloud, "
                "anonymous open reads). what=list lists every proxy for the "
                "ticker; what=statement returns one full proxy (comp tables, "
                "say-on-pay, key figures) and requires year — the PROXY "
                "(filing) year, not the fiscal year. Adds a term.gloom.sh "
                "deep link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "what": {"type": "string", "enum": ["list", "statement"], "default": "list"},
                    "year": {"type": "integer", "description": "what=statement proxy year"},
                },
                "required": ["ticker"],
            },
        },
    }


def build_digifetch_filing_events_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_filing_events",
            "description": (
                "Classified 8-K filing events for one ticker (Gloomberb Cloud, "
                "anonymous). Rows carry item codes/labels/kinds, materiality, "
                "the SEC document URL, named people, and a model reading "
                "(read=true) when the filing carried news. Newest first; limit "
                "caps the page. Adds a term.gloom.sh deep link. Cached/delayed "
                "— cross-check against EDGAR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "limit": {"type": "integer", "default": 20, "minimum": 1, "maximum": 200},
                },
                "required": ["ticker"],
            },
        },
    }


def build_digifetch_risk_reports_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_risk_reports",
            "description": (
                "10-K risk-factor reports, diffed year-over-year (Gloomberb "
                "Cloud, anonymous). what=list lists report years with counts "
                "and an overview; what=report returns one year's extracted "
                "risk factors, groups, the added/removed/reworded diff, and "
                "notes (requires year). Adds a term.gloom.sh deep link. "
                "Cached/delayed — cross-check against EDGAR."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "what": {"type": "string", "enum": ["list", "report"], "default": "list"},
                    "year": {"type": "integer", "description": "what=report report year"},
                },
                "required": ["ticker"],
            },
        },
    }


def build_digifetch_short_interest_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_short_interest",
            "description": (
                "Biweekly short-interest settlements (Gloomberb Cloud; "
                "session-gated). Requires GLOOMBERB_SESSION_COOKIE — without it "
                "the call is a typed auth_required with no request. years is "
                "1-10 (the upstream silently falls back to a 3-year window "
                "outside that range; the contract rejects it first). Points "
                "carry shares short, average daily volume, days to cover, and "
                "change percent. Adds a term.gloom.sh deep link. "
                "Exchange-reported, delayed by reporting cadence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "years": {"type": "integer", "default": 3, "minimum": 1, "maximum": 10},
                },
                "required": ["symbol"],
            },
        },
    }


def build_digifetch_equity_diagnostic_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digifetch_equity_diagnostic",
            "description": (
                "AI evidence review for one listing (Gloomberb Cloud; "
                "session-gated). Requires GLOOMBERB_SESSION_COOKIE. The first "
                "request per symbol answers a pending payload "
                "(status=generating + retryAfterMs); retry until a report "
                "arrives (complete/partial/insufficient_data) whose findings "
                "keep observation and interpretation separate. Free sessions "
                "only receive access=preview; mode=refresh asks the server to "
                "regenerate. Gloomberb's model-generated reading — not "
                "investment advice. Complete reports are cached, pending ones "
                "are not. Adds a term.gloom.sh deep link."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "exchange": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "enum": ["cache-first", "refresh"],
                        "default": "cache-first",
                    },
                },
                "required": ["symbol"],
            },
        },
    }


def build_digiquant_fit_btc_power_law_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fit_btc_power_law",
            "description": (
                "Fit SDCA BTC power-law (RAQQR) rails from cached daily prices "
                "via history_cache.py (not a bespoke fetch)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "default": "BTC-USD"},
                    "cache_dir": {"type": "string"},
                    "refresh": {"type": "boolean", "default": True},
                    "output_path": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
        },
    }


def build_digiquant_build_sdca_risk_index_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_build_sdca_risk_index",
            "description": (
                "Build the SDCA date/risk parquet from a RiskModel + cached "
                "prices. profile=btc_v1|eth_research_v1 applies SdcaAssetProfile "
                "rails/oscillators/allowlist."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "default": "BTC-USD"},
                    "cache_dir": {"type": "string"},
                    "refresh": {"type": "boolean", "default": True},
                    "risk_model": {"type": "string", "default": "btc_power_law"},
                    "profile": {"type": "string"},
                    "profile_json": {"type": "string"},
                    "coefficients_path": {"type": "string"},
                    "output_path": {"type": "string"},
                    "indicator_weights": {"type": "string", "default": "{}"},
                    "m2_path": {"type": "string"},
                    "dxy_path": {"type": "string"},
                    "eth_ticker": {"type": "string", "default": "ETH-USD"},
                    "valuation_form": {"type": "string", "default": "log_quadratic"},
                    "rolling_window": {"type": "integer", "default": 90},
                },
            },
        },
    }


def build_digiquant_fetch_bitview_series_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fetch_bitview_series",
            "description": (
                "Fetch Bitview/BRK on-chain day1 series (mvrv, asopr_24h, "
                "puell_multiple, rhodl_ratio) into data/onchain/bitview. "
                "JSON API only; nupl refused by default (dual-count of mvrv) "
                "unless allow_derived=true. Fail-soft. CM community CC BY-NC "
                "is not fetched. Refs #1086."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "series_ids_json": {
                        "type": "string",
                        "description": "JSON array of BRK series ids",
                    },
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "number", "default": 30},
                    "start": {"type": "integer"},
                    "end": {"type": "integer"},
                    "allow_derived": {
                        "type": "boolean",
                        "description": "Fetch series normally refused as derived/dual-count (e.g. nupl)",
                        "default": False,
                    },
                },
            },
        },
    }


def build_digiquant_fetch_bgeometrics_series_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fetch_bgeometrics_series",
            "description": (
                "Fetch one Bitcoin valuation/on-chain metric from "
                "bitcoin-data.com (BGeometrics): 700+ metrics (mvrv, "
                "mvrv-zscore, nupl, sopr, realized-price, thermocap-multiple, "
                "mayer-multiple, pi-cycle, rainbow-chart, power-law-model-price, "
                "and more). API key now effectively required (bitcoin-data.com "
                "markets registration as mandatory even for the free tier); "
                "pass token or set BGEOMETRICS_API_TOKEN. Free tier: 10 "
                "req/hour, 15/day shared across all metrics — fetch one "
                "metric per call. History capped at ~4 years; for deeper "
                "multi-cycle history use digiquant_fetch_coinmetrics_series "
                "instead. Fail-soft."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "bitcoin-data.com metric slug, e.g. 'mvrv'",
                        "default": "mvrv",
                    },
                    "startday": {"type": "string", "description": "YYYY-MM-DD"},
                    "endday": {"type": "string", "description": "YYYY-MM-DD"},
                    "last": {
                        "type": "boolean",
                        "description": "fetch only the most recent value",
                        "default": False,
                    },
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "number", "default": 30},
                    "token": {"type": "string", "description": "bitcoin-data.com API token"},
                },
                "required": ["metric"],
            },
        },
    }


def build_digiquant_fetch_coinmetrics_series_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fetch_coinmetrics_series",
            "description": (
                "Fetch one on-chain metric for one asset from the CoinMetrics "
                "Community API (free, no API key required). One metric/asset "
                "per call — use digiquant_list_coinmetrics_catalog to discover "
                "what's available per-asset. BTC's CapMVRVCur (MVRV valuation "
                "ratio) has full history back to 2010-07-18. CC BY-NC — "
                "research-only, do not republish derived series commercially. "
                "Fail-soft."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "CoinMetrics metric id, e.g. 'CapMVRVCur'",
                        "default": "CapMVRVCur",
                    },
                    "asset": {"type": "string", "default": "btc"},
                    "start_time": {"type": "string", "description": "ISO 8601 or YYYY-MM-DD"},
                    "end_time": {"type": "string", "description": "ISO 8601 or YYYY-MM-DD"},
                    "page_size": {"type": "integer", "default": 10000},
                    "cache_dir": {"type": "string"},
                    "timeout": {"type": "number", "default": 30},
                    "api_key": {
                        "type": "string",
                        "description": "Registered CoinMetrics API key (optional)",
                    },
                },
                "required": ["metric"],
            },
        },
    }


def build_digiquant_list_coinmetrics_catalog_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_list_coinmetrics_catalog",
            "description": (
                "List which CoinMetrics community metrics exist for an asset "
                "(or all assets). Discovery tool — call before "
                "digiquant_fetch_coinmetrics_series to find real metric names "
                "instead of guessing. Fail-soft."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "asset": {"type": "string", "description": "Restrict to one asset, e.g. 'btc'"},
                    "timeout": {"type": "number", "default": 30},
                    "api_key": {
                        "type": "string",
                        "description": "Registered CoinMetrics API key (optional)",
                    },
                },
            },
        },
    }


def build_digiquant_fit_sdca_weights_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_fit_sdca_weights",
            "description": (
                "Stage A: fit SDCA composite weights so risk overlaps the "
                "asset's cycle windows, then regularize. Stage B is "
                "digiquant_run_optimize strategy_name=sdca. Not a second "
                "optimizer product. No live-trading."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "profile": {"type": "string", "default": "btc_v1"},
                    "profile_json": {"type": "string"},
                    "cache_dir": {"type": "string"},
                    "coefficients_path": {"type": "string"},
                    "output_path": {"type": "string"},
                    "m2_path": {"type": "string"},
                    "dxy_path": {"type": "string"},
                    "eth_ticker": {"type": "string", "default": "ETH-USD"},
                    "valuation_form": {"type": "string", "default": "log_quadratic"},
                    "rolling_window": {"type": "integer", "default": 90},
                },
            },
        },
    }


def build_dashboard_run_policy_replay_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_run_policy_replay",
            "description": (
                "Register a policy replay run against a stored pair. Returns summary "
                "IDs/status only. Never activates or promotes production policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pair_content_hash": {
                        "type": "string",
                        "description": "64-hex content hash of a stored ReplayPairSpec",
                    },
                    "run_id": {
                        "type": "string",
                        "description": "Optional stable run id (generated if omitted)",
                    },
                },
                "required": ["pair_content_hash"],
            },
        },
    }


def build_dashboard_get_policy_replay_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_get_policy_replay",
            "description": "Fetch a policy replay run summary by run_id (fail closed if unknown).",
            "parameters": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                },
                "required": ["run_id"],
            },
        },
    }


def build_dashboard_get_policy_comparison_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_get_policy_comparison",
            "description": (
                "Fetch a policy comparison summary (artifact IDs and status only — "
                "no confidential evidence)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comparison_id": {"type": "string"},
                },
                "required": ["comparison_id"],
            },
        },
    }


def build_dashboard_evaluate_policy_gate_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_evaluate_policy_gate",
            "description": (
                "Evaluate immutable human-authored gate criteria against a comparison. "
                "Returns eligibility for human review only — never activates policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "comparison_id": {"type": "string"},
                    "criteria_version_id": {"type": "string"},
                },
                "required": ["comparison_id", "criteria_version_id"],
            },
        },
    }


def build_dashboard_get_policy_gate_evaluation_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "dashboard_get_policy_gate_evaluation",
            "description": "Fetch a gate-evaluation summary by evaluation_id (fail closed if unknown).",
            "parameters": {
                "type": "object",
                "properties": {
                    "evaluation_id": {"type": "string"},
                },
                "required": ["evaluation_id"],
            },
        },
    }


def build_digiquant_compile_research_portfolio_tool() -> dict[str, Any]:
    """Dry compile research + portfolio graphs for digigraph product graphs (#3415)."""
    return {
        "type": "function",
        "function": {
            "name": "digiquant_compile_research_portfolio",
            "description": (
                "Compile digiquant research and portfolio LangGraph topologies without "
                "LLM calls or book writes. Used by digigraph product graphs "
                "(research-portfolio-chain) as the dry-run path (#3415)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "run_date": {
                        "type": "string",
                        "description": "ISO date (YYYY-MM-DD). Defaults to UTC today.",
                    },
                    "cadence": {"type": "string", "default": "daily"},
                    "refresh_scope": {"type": "string", "default": "none"},
                    "watchlist": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tickers for Phase 7C / portfolio width.",
                    },
                    "graph_name": {
                        "type": "string",
                        "default": "research-portfolio-chain",
                        "description": "digigraph product graph name for idempotency key.",
                    },
                },
            },
        },
    }


def build_digiquant_get_trade_levels_tool() -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": "digiquant_get_trade_levels",
            "description": (
                "Compute causal trade levels (entry band, structural/ATR stop, "
                "R-multiple take-profit ladder, trail policy) for a long or short "
                "direction. Read-only — never sizes or places orders. Supply "
                "ohlc_json (a JSON array of OHLC bars) as the primary data path, "
                "or a locally cached ticker as a convenience."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "direction": {
                        "type": "string",
                        "enum": ["long", "short"],
                        "description": "Trade direction the levels are computed for",
                    },
                    "ohlc_json": {
                        "type": "string",
                        "description": (
                            "JSON array of bars: [{timestamp, open, high, low, "
                            "close, volume}, ...] sorted ascending. Primary path."
                        ),
                    },
                    "pair": {
                        "type": "string",
                        "description": "Instrument label echoed in the contract, e.g. 'EUR/USD'",
                    },
                    "ticker": {
                        "type": "string",
                        "description": (
                            "Optional ticker with a local history-cache CSV "
                            "(non-blocking convenience; no network fetch)"
                        ),
                    },
                    "config_json": {
                        "type": "string",
                        "description": "Optional JSON object of LevelsConfig overrides",
                    },
                    "cache_dir": {
                        "type": "string",
                        "description": "Optional cache directory for the ticker convenience path",
                    },
                },
                "required": ["direction"],
            },
        },
    }


def _with_entitlement(tool: dict[str, Any]) -> dict[str, Any]:
    """Attach the declared entitlement to a digifetch tool schema (#4110 phase 5).

    The vocabulary lives in :mod:`digiquant.data.gloomberb.entitlements`; the
    MCP registration injects the same note into its description and tags the
    registered function, so the two surfaces cannot drift.
    """
    from digiquant.data.gloomberb.entitlements import TOOL_ENTITLEMENTS, with_entitlement_note

    name = tool.get("function", {}).get("name")
    entitlement = TOOL_ENTITLEMENTS.get(name)
    if entitlement is None:
        return tool
    tool["entitlement"] = entitlement
    function = tool["function"]
    function["description"] = with_entitlement_note(name, function["description"])
    return tool


def build_orchestrator_tool_manifest() -> list[dict[str, Any]]:
    """Return the full digiquant orchestrator tool surface.

    Every digifetch tool carries a top-level ``entitlement`` declaration
    (``free`` | ``session`` | ``preview`` | ``pro``) and an entitlement note in
    its description; see :mod:`digiquant.data.gloomberb.entitlements`.
    """
    tools = [
        build_digiquant_list_strategies_tool(),
        build_digiquant_run_backtest_tool(),
        build_digiquant_run_optimize_tool(),
        build_digiquant_run_export_tool(),
        build_digiquant_run_pipeline_tool(),
        build_digiquant_pipeline_delegate_tool(),
        build_digiquant_fetch_coinbase_ohlcv_tool(),
        build_digifetch_quote_tool(),
        build_digifetch_quotes_batch_tool(),
        build_digifetch_price_history_tool(),
        build_digifetch_ticker_financials_tool(),
        build_digifetch_options_chain_tool(),
        build_digifetch_sec_filings_tool(),
        build_digifetch_holders_tool(),
        build_digifetch_analyst_research_tool(),
        build_digifetch_corporate_actions_tool(),
        build_digifetch_earnings_calendar_tool(),
        build_digifetch_exchange_rate_tool(),
        build_digifetch_search_tool(),
        build_digifetch_news_tool(),
        build_digifetch_econ_calendar_tool(),
        build_digifetch_econ_series_tool(),
        build_digifetch_yield_curve_tool(),
        build_digifetch_cds_tool(),
        build_digifetch_research_search_tool(),
        build_digifetch_congress_trades_tool(),
        build_digifetch_transcripts_tool(),
        build_digifetch_statements_tool(),
        build_digifetch_ticker_tweets_tool(),
        build_digifetch_tweet_search_tool(),
        build_digifetch_venues_tool(),
        build_digifetch_screener_tool(),
        build_digifetch_13f_funds_tool(),
        build_digifetch_13f_holdings_tool(),
        build_digifetch_shiller_tool(),
        build_digifetch_proxy_statements_tool(),
        build_digifetch_filing_events_tool(),
        build_digifetch_risk_reports_tool(),
        build_digifetch_short_interest_tool(),
        build_digifetch_equity_diagnostic_tool(),
        build_digiquant_fit_btc_power_law_tool(),
        build_digiquant_build_sdca_risk_index_tool(),
        build_digiquant_fetch_bitview_series_tool(),
        build_digiquant_fetch_bgeometrics_series_tool(),
        build_digiquant_fetch_coinmetrics_series_tool(),
        build_digiquant_list_coinmetrics_catalog_tool(),
        build_digiquant_get_trade_levels_tool(),
        build_digiquant_fit_sdca_weights_tool(),
        build_digiquant_compile_research_portfolio_tool(),
        build_dashboard_run_policy_replay_tool(),
        build_dashboard_get_policy_replay_tool(),
        build_dashboard_get_policy_comparison_tool(),
        build_dashboard_evaluate_policy_gate_tool(),
        build_dashboard_get_policy_gate_evaluation_tool(),
    ]
    return [_with_entitlement(tool) for tool in tools]
