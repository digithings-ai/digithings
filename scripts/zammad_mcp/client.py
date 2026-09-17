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
import re
from typing import Any, Callable

import httpx

DEFAULT_BASE_URL = "https://ticket.sitaas.de"
MAX_SEARCH_LIMIT = 50
MAX_REPORT_TICKETS = 500
PAGE_SIZE = 100
MAX_KEYWORD_TERMS = 5
MIN_KEYWORD_LENGTH = 2

JsonGetter = Callable[..., Any]

_FIELD_QUERY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*:(\([^)]*\)|\"(?:[^\"\\]|\\.)*\"|\S+)")
_KEYWORD_NOISE_RE = re.compile(r"[~*()\"']")
_TERM_TRIM = ".,;:!?[]{}<>#"
_KEYWORD_STOPWORDS = frozenset(
    {
        "and",
        "or",
        "not",
        "to",
        "der",
        "die",
        "das",
        "dem",
        "den",
        "des",
        "ein",
        "eine",
        "einer",
        "eines",
        "einem",
        "einen",
        "ist",
        "und",
        "oder",
        "zu",
        "zur",
        "zum",
        "am",
        "im",
        "in",
        "an",
        "auf",
        "für",
        "fuer",
        "mit",
        "von",
        "vom",
        "bei",
    }
)


class ZammadError(RuntimeError):
    """Raised for configuration, transport, or response errors."""


def keyword_terms(query: str) -> list[str]:
    """Extract plain keywords from a Zammad search query.

    Without Elasticsearch, ticket search only matches the whole query string
    as one substring, so field syntax (``state.name:open``) and long
    multi-word phrases silently match nothing. Field values are kept so a
    caller can retry the terms one by one.
    """
    stripped = _FIELD_QUERY_RE.sub(lambda match: f" {match.group(1)} ", query or "")
    stripped = _KEYWORD_NOISE_RE.sub(" ", stripped)
    terms: list[str] = []
    seen: set[str] = set()
    for raw in stripped.split():
        term = raw.strip(_TERM_TRIM)
        if len(term) < MIN_KEYWORD_LENGTH:
            continue
        lowered = term.lower()
        if lowered in _KEYWORD_STOPWORDS or lowered in seen:
            continue
        seen.add(lowered)
        terms.append(term)
        if len(terms) >= MAX_KEYWORD_TERMS:
            break
    return terms


def _updated_sort_key(ticket: dict[str, Any]) -> str:
    """Sort key for merged keyword results: newest first, unknown last."""
    value = ticket.get("updated_at")
    return str(value) if value else ""


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

    def _coerce_limit(self, limit: int) -> int:
        try:
            return max(1, min(int(limit), MAX_SEARCH_LIMIT))
        except (TypeError, ValueError) as exc:
            raise ZammadError("limit must be an integer") from exc

    def _search_rows(self, payload: Any) -> list[dict[str, Any]]:
        rows: Any = payload
        if isinstance(payload, dict):
            rows = None
            for key in ("tickets", "records", "objects"):
                value = payload.get(key)
                if isinstance(value, list):
                    rows = value
                    break
        if not isinstance(rows, list):
            raise ZammadError("unexpected Zammad search payload")
        return [row for row in rows if isinstance(row, dict)]

    def search_tickets(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """Search tickets (Zammad ticket search syntax). Read-only."""
        cleaned = (query or "").strip()
        if not cleaned:
            raise ZammadError("search requires a non-empty query")
        capped = self._coerce_limit(limit)
        payload = self._get(
            "/api/v1/tickets/search",
            {"query": cleaned, "limit": capped, "expand": "true"},
        )
        return self._search_rows(payload)

    def search_tickets_by_terms(self, terms: list[str], limit: int = 10) -> list[dict[str, Any]]:
        """Search each keyword separately and merge the matches. Read-only.

        Search semantics differ by instance: multi-word queries and field
        syntax only work with Elasticsearch. Term-by-term search is the
        fallback for instances that only do a substring match.
        """
        capped = self._coerce_limit(limit)
        merged: dict[Any, dict[str, Any]] = {}
        for term in terms[:MAX_KEYWORD_TERMS]:
            for row in self.search_tickets(term, limit=capped):
                key = row.get("id")
                if key is None or key in merged:
                    continue
                merged[key] = row
        ordered = sorted(merged.values(), key=_updated_sort_key, reverse=True)
        return ordered[:capped]

    def _coerce_id(self, ticket_id: int | str) -> int:
        try:
            tid = int(str(ticket_id).strip().lstrip("#"))
        except (TypeError, ValueError) as exc:
            raise ZammadError("ticket id must be a positive integer") from exc
        if tid < 1:
            raise ZammadError("ticket id must be a positive integer")
        return tid

    def _lookup_ticket_number(self, number: object) -> int | None:
        """Map a ticket number (shown as ``#28312``) to its internal id."""
        try:
            rows = self.search_tickets(str(number), limit=MAX_SEARCH_LIMIT)
        except ZammadError:
            return None
        for row in rows:
            if str(row.get("number")) == str(number):
                resolved = row.get("id")
                if isinstance(resolved, int) and resolved > 0:
                    return resolved
        return None

    def _fetch_ticket(self, tid: int) -> dict[str, Any]:
        payload = self._get(f"/api/v1/tickets/{tid}", {"expand": "true"})
        if not isinstance(payload, dict):
            raise ZammadError("unexpected Zammad ticket payload")
        return payload

    def get_ticket(self, ticket_id: int | str) -> dict[str, Any]:
        """Fetch one ticket by internal id or ticket number. Read-only.

        A ``#``-prefixed value is the number shown in results (``#28312``)
        and is resolved by number first. A bare number is tried as the
        internal id first and falls back to a number search on 404.
        """
        raw = str(ticket_id).strip()
        if raw.startswith("#"):
            number = raw.lstrip("#").strip()
            if not number.isdigit():
                raise ZammadError("ticket id must be a positive integer")
            resolved = self._lookup_ticket_number(number)
            if resolved is None:
                raise ZammadError(f"no ticket with number {number}")
            return self._fetch_ticket(resolved)
        tid = self._coerce_id(ticket_id)
        try:
            return self._fetch_ticket(tid)
        except ZammadError as exc:
            if "HTTP 404" not in str(exc):
                raise
            resolved = self._lookup_ticket_number(tid)
            if resolved is None:
                raise
            return self._fetch_ticket(resolved)

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
