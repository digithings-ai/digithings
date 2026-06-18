"""Bounded-timeout ``httpx`` client helpers.

Centralizes the default timeout envelope used for every service-to-service
HTTP call across the DigiThings monorepo. Bare ``httpx.AsyncClient()`` and
``httpx.Client()`` constructions wait *forever* on a slow upstream (LLM,
broker, vector store), which is unacceptable for production request-path
code. This module provides thin factory helpers that preload a sensible
``httpx.Timeout`` and let callers override any phase per call site.

Timeout envelope
----------------

``DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0)``

Rationale for each phase:

- **connect = 5 s** — TCP / TLS establishment. Broker APIs and internal
  services on the compose network should handshake in well under a second.
  Five seconds tolerates transient DNS hiccups without masking a dead
  upstream.
- **read = 30 s** — socket read between chunks. LLM completion calls are
  the long pole: a single token stream can legitimately sit idle for many
  seconds between chunks on complex prompts. Thirty seconds is generous for
  non-streaming JSON APIs while still bounding catastrophic stalls.
- **write = 10 s** — socket write between chunks. Request bodies are
  typically small JSON payloads; ten seconds is conservative headroom.
- **pool = 5 s** — wait time when acquiring a connection from the pool.
  Short on purpose: a starved pool is usually a bug, not a reason to wedge
  a caller.

Callers that need a different envelope (e.g. long-running backtests) should
pass an explicit ``timeout=`` keyword argument; the helpers forward it
verbatim to ``httpx``. Accepted override types mirror ``httpx``:

- ``float`` / ``int`` — single value applied to all phases.
- ``httpx.Timeout`` — full per-phase override.
- ``None`` — disable timeouts (discouraged; audit before use).
"""

from __future__ import annotations

from typing import Any

import httpx

__all__ = ["DEFAULT_TIMEOUT", "async_client", "sync_client"]

# Bounded envelope. See module docstring for rationale.
DEFAULT_TIMEOUT: httpx.Timeout = httpx.Timeout(
    connect=5.0,
    read=30.0,
    write=10.0,
    pool=5.0,
)


def async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Return an ``httpx.AsyncClient`` pre-configured with the default timeout.

    Any ``httpx.AsyncClient`` keyword argument is accepted and forwarded
    (``base_url``, ``headers``, ``auth``, ``transport``, ``limits``,
    ``verify``, ``http2``, etc.). Pass ``timeout=`` to override the default
    envelope for this client instance.
    """
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    return httpx.AsyncClient(timeout=timeout, **kwargs)


def sync_client(**kwargs: Any) -> httpx.Client:
    """Return an ``httpx.Client`` pre-configured with the default timeout.

    Mirrors :func:`async_client` for blocking call sites. Prefer the async
    variant for new code; the sync helper exists for existing synchronous
    consumers and short-lived CLI tools.
    """
    timeout = kwargs.pop("timeout", DEFAULT_TIMEOUT)
    return httpx.Client(timeout=timeout, **kwargs)
