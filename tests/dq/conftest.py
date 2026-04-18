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
import sys


def pytest_configure(config: object) -> None:
    if sys.platform != "win32":
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
