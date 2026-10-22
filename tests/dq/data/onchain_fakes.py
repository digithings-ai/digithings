"""Shared HTTP doubles for the on-chain series clients.

Five on-chain client test modules used to carry their own copy of the same
two doubles: a response whose ``raise_for_status`` raised, and a session
that recorded the URLs it was called with. One fake lives here now.

The response double raises ``httpx.HTTPStatusError`` and carries the body on
the response, because the production clients wrap that error and read the
body back to build their message — a fake that raised a bare ``RuntimeError``
would hide the payload the client is supposed to report.
"""

from __future__ import annotations

from typing import Any  # score:allow untyped any — fake HTTP session / JSON bodies

import httpx


class FakeResponse:
    """Response double for the on-chain clients (no network)."""

    def __init__(self, body: object, status: int = 200) -> None:
        self._body = body
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", "https://onchain.invalid/"),
                response=httpx.Response(self.status_code, json=self._body),
            )

    def json(self) -> object:
        return self._body


class FakeSession:
    """Session double: records the calls, routes by URL, never touches the network."""

    def __init__(
        self,
        *,
        by_url: dict[str, object] | None = None,
        body: object | None = None,
        default: object | None = None,
        exc: Exception | None = None,
    ) -> None:
        self._by_url = by_url or {}
        self._body = body
        self._default = default
        self._exc = exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._respond(url, kwargs)

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        return self._respond(url, kwargs)

    def _respond(self, url: str, kwargs: dict[str, Any]) -> FakeResponse:
        self.calls.append((url, kwargs))
        if self._exc is not None:
            raise self._exc
        if url in self._by_url:
            return FakeResponse(self._by_url[url])
        for key, payload in self._by_url.items():
            if key in url:
                return FakeResponse(payload)
        if self._body is not None:
            return FakeResponse(self._body)
        if isinstance(self._default, dict):
            return FakeResponse(dict(self._default))
        return FakeResponse({} if self._default is None else self._default)


def mvrv_slice() -> dict[str, Any]:
    """Captured-shape SeriesData: day1 indexes 800-805 (2011-03-14...18)."""
    return {
        "version": 4126600656,
        "index": "day1",
        "type": "StoredF32",
        "start": 800,
        "end": 805,
        "stamp": "2026-08-30T22:07:42Z",
        "data": [3.214286, 3.214286, 3.178571, 3.142857, 2.931034],
    }
