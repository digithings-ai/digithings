"""Minimal read-only Zammad REST client (GET only).

Auth is a Zammad API token sent as ``Authorization: Token token=<token>``.
``ZAMMAD_API_TOKEN`` (or the explicit argument) may hold either the raw token
or the full ``Token token=<token>`` header value — the digichat tenant config
forwards the same variable verbatim through digigraph, which sends it as the
``Authorization`` header, so one value serves both paths. Never logged or
committed.
"""

from __future__ import annotations

import os
from typing import Any, Callable

import httpx

DEFAULT_BASE_URL = "https://ticket.sitaas.de"
MAX_SEARCH_LIMIT = 50
MAX_REPORT_TICKETS = 500
PAGE_SIZE = 100

JsonGetter = Callable[..., Any]


class ZammadError(RuntimeError):
    """Raised for configuration, transport, or response errors."""


def _http_get_json(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> Any:
    """Default transport: one GET, JSON response, error translation."""
    try:
        response = httpx.get(
            url, params=params, headers=headers, timeout=timeout, follow_redirects=True
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        snippet = exc.response.text[:200].replace("\n", " ")
        raise ZammadError(f"Zammad HTTP {exc.response.status_code}: {snippet}") from exc
    except httpx.HTTPError as exc:
        raise ZammadError(f"Zammad request failed: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise ZammadError("Zammad returned a non-JSON response") from exc


class ZammadClient:
    """Read-only client for the Zammad REST API."""

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = 30.0,
        get_json: JsonGetter | None = None,
    ) -> None:
        resolved_base = (base_url or os.environ.get("ZAMMAD_BASE_URL") or DEFAULT_BASE_URL).strip()
        self.base_url = resolved_base.rstrip("/")
        self.token = (
            token if token is not None else os.environ.get("ZAMMAD_API_TOKEN", "")
        ).strip()
        self.timeout = timeout
        self._get_json = get_json or _http_get_json

    @property
    def configured(self) -> bool:
        """True when both a base URL and a token are present."""
        return bool(self.base_url and self.token)

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise ZammadError("ZAMMAD_API_TOKEN is not set")
        value = self.token
        if not value.lower().startswith("token token="):
            value = f"Token token={value}"
        return {"Authorization": value, "Accept": "application/json"}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        return self._get_json(
            f"{self.base_url}{path}",
            params=params,
            headers=self._headers(),
            timeout=self.timeout,
        )

    def search_tickets(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search tickets (Zammad ticket search syntax). Read-only."""
        cleaned = (query or "").strip()
        if not cleaned:
            raise ZammadError("search requires a non-empty query")
        try:
            capped = max(1, min(int(limit), MAX_SEARCH_LIMIT))
        except (TypeError, ValueError) as exc:
            raise ZammadError("limit must be an integer") from exc
        payload = self._get(
            "/api/v1/tickets/search",
            {"query": cleaned, "limit": capped, "expand": "true"},
        )
        if isinstance(payload, dict):
            rows = payload.get("tickets")
        else:
            rows = payload
        if not isinstance(rows, list):
            raise ZammadError("unexpected Zammad search payload")
        return [row for row in rows if isinstance(row, dict)]

    def _coerce_id(self, ticket_id: int | str) -> int:
        try:
            tid = int(ticket_id)
        except (TypeError, ValueError) as exc:
            raise ZammadError("ticket id must be a positive integer") from exc
        if tid < 1:
            raise ZammadError("ticket id must be a positive integer")
        return tid

    def get_ticket(self, ticket_id: int | str) -> dict[str, Any]:
        """Fetch one ticket by id, with relation names expanded. Read-only."""
        tid = self._coerce_id(ticket_id)
        payload = self._get(f"/api/v1/tickets/{tid}", {"expand": "true"})
        if not isinstance(payload, dict):
            raise ZammadError("unexpected Zammad ticket payload")
        return payload

    def get_articles(self, ticket_id: int | str) -> list[dict[str, Any]]:
        """Fetch a ticket's articles (oldest first). Read-only."""
        tid = self._coerce_id(ticket_id)
        payload = self._get(f"/api/v1/ticket_articles/by_ticket/{tid}", {"expand": "true"})
        if not isinstance(payload, list):
            raise ZammadError("unexpected Zammad article payload")
        return [row for row in payload if isinstance(row, dict)]

    def list_tickets(self, max_tickets: int = MAX_REPORT_TICKETS) -> list[dict[str, Any]]:
        """List visible tickets, expanded, paginated. Read-only.

        Used by the report tool: the plain list endpoint pages through every
        ticket the token can see (group permissions apply server-side).
        """
        try:
            cap = max(1, min(int(max_tickets), MAX_REPORT_TICKETS))
        except (TypeError, ValueError) as exc:
            raise ZammadError("max_tickets must be an integer") from exc
        tickets: list[dict[str, Any]] = []
        page = 1
        while len(tickets) < cap:
            payload = self._get(
                "/api/v1/tickets",
                {"page": page, "per_page": PAGE_SIZE, "expand": "true"},
            )
            if not isinstance(payload, list):
                raise ZammadError("unexpected Zammad ticket list payload")
            rows = [row for row in payload if isinstance(row, dict)]
            if not rows:
                break
            tickets.extend(rows)
            if len(payload) < PAGE_SIZE:
                break
            page += 1
        return tickets[:cap]
