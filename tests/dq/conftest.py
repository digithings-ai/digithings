"""digiquant test fixtures.

Isolates the dq test suite from uvloop so NautilusTrader's Rust event loop
cannot conflict with libuv signal handlers. Without this, pytest+uvloop on
Linux triggers SIGABRT (exit 134) inside the Nautilus BacktestEngine — see #42.

Root cause: uvicorn[standard] installs uvloop and sets it as the asyncio
event loop policy at import time on Linux. NautilusTrader's BacktestEngine
registers its own signal handlers (SIGTERM/SIGINT) in C++. When uvloop has
already claimed those handlers, the libuv and Rust runtimes race, producing
an assertion failure → SIGABRT. Forcing the standard asyncio policy for the
dq suite prevents the conflict.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys

# Skip collection of modules that transitively import nautilus_trader when the
# extra isn't installed (CI excludes [nautilus] due to SIGABRT — see #42).
# Runtime-level `_SKIP_NATIVE_CRASH` fires too late; collection must short-circuit.
if importlib.util.find_spec("nautilus_trader") is None:
    collect_ignore = [
        "test_api.py",
        "test_audit.py",
        "test_backtest.py",
        "test_calibrations_loader.py",
        "test_nautilus_runner.py",
        "test_pipeline_graph.py",
        "test_strategies.py",
        # Spawned tearsheet workers import digiquant.strategies (→ nautilus).
        "test_tearsheet_isolation.py",
        "test_v1_jobs.py",
    ]


def pytest_configure(config: object) -> None:
    if sys.platform != "win32":
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
