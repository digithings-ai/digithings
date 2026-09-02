"""Bounded httpx timeouts for PostgREST I/O (#3319, #3426).

``build_client`` applies these as ``httpx.Timeout``. Ledger ``_insert`` does
not wrap ``execute()`` in a thread deadline — abandoning the worker while an
INSERT may still complete forks the append-only chain.
"""

from __future__ import annotations

CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 60.0
WRITE_TIMEOUT_SECONDS = 30.0
POOL_TIMEOUT_SECONDS = 10.0
