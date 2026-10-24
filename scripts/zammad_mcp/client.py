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
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

DEFAULT_BASE_URL = "https://ticket.sitaas.de"
MAX_SEARCH_LIMIT = 500
MAX_REPORT_TICKETS = 500
PAGE_SIZE = 100
MAX_KEYWORD_TERMS = 10
MIN_KEYWORD_LENGTH = 2

SORT_FIELDS = frozenset({"created_at", "updated_at", "close_at", "id", "number"})

VALID_STATE_CATEGORIES = frozenset({"open", "closed", "pending"})
PENDING_STATE_TYPE_IDS = frozenset({3, 4})

# Canonical display name -> Zammad state_type_id for the known states.
# Zammad seeds new(1)/open(2)/pending-reminder(3)/pending-close(4)/
# closed(5)/merged(6)/removed(7); the German states are this instance's
# custom open/pending states. ``build_query`` merges the live
# ``get_state_types()`` cache over this table (live wins), so custom states
# added later are picked up while casing stays stable for the known ones.
_KNOWN_STATE_TYPES: tuple[tuple[str, int], ...] = (
    ("new", 1),
    ("open", 2),
    ("in Bearbeitung", 2),
    ("gelöst von Dev", 2),
    ("warten auf Kunden", 3),
    ("warten auf Dev", 4),
    ("closed", 5),
    ("merged", 6),
)

_STATE_NAME_BARE_RE = re.compile(r"^[A-Za-z0-9_-]+$")

_state_types_cache: dict[str, int] | None = None

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


def _state_term(name: str) -> str:
    """One ``state.name:`` clause; quote anything beyond a bare word."""
    if _STATE_NAME_BARE_RE.match(name):
        return f"state.name:{name}"
    return f'state.name:"{name}"'


def _window_clauses(since_days: int | None, until_days: int | None) -> list[str]:
    """Validate day offsets and render ``created_at`` date-only clauses."""
    try:
        since = None if since_days is None else int(since_days)
        until = None if until_days is None else int(until_days)
    except (TypeError, ValueError) as exc:
        raise ZammadError("since_days and until_days must be integers") from exc
    ref = datetime.now(timezone.utc).date()
    clauses = []
    if since is not None:
        clauses.append(f"created_at:>={(ref - timedelta(days=since)).isoformat()}")
    if until is not None:
        clauses.append(f"created_at:<{(ref - timedelta(days=until)).isoformat()}")
    return clauses


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
        self._user_cache: dict[int, str] = {}

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

    def _coerce_page(self, page: int) -> int:
        try:
            return max(1, int(page))
        except (TypeError, ValueError) as exc:
            raise ZammadError("page must be an integer") from exc

    def _coerce_page_size(self, per_page: int) -> int:
        try:
            return max(1, min(int(per_page), PAGE_SIZE))
        except (TypeError, ValueError) as exc:
            raise ZammadError("per_page must be an integer") from exc

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

    def search_tickets(
        self, query: str, limit: int = 10, sort_by: str | None = None, order_by: str | None = None
    ) -> list[dict[str, Any]]:
        """Search tickets (Zammad ticket search syntax). Read-only."""
        cleaned = (query or "").strip()
        if not cleaned:
            raise ZammadError("search requires a non-empty query")
        capped = self._coerce_limit(limit)
        params: dict[str, Any] = {"query": cleaned, "limit": capped, "expand": "true"}
        if sort_by is not None:
            if sort_by not in SORT_FIELDS:
                raise ZammadError(f"sort_by must be one of {sorted(SORT_FIELDS)}")
            params["sort_by"] = sort_by
            params["order_by"] = "desc" if order_by is None else order_by
        payload = self._get("/api/v1/tickets/search", params)
        return self._search_rows(payload)

    def count_tickets(self, query: str) -> int:
        """Cheap server-side count via only_total_count (no rows fetched)."""
        cleaned = (query or "").strip()
        if not cleaned:
            raise ZammadError("search requires a non-empty query")
        payload = self._get(
            "/api/v1/tickets/search",
            {"query": cleaned, "limit": 1, "expand": "true", "only_total_count": "true"},
        )
        if isinstance(payload, dict) and isinstance(payload.get("total_count"), int):
            return int(payload["total_count"])
        raise ZammadError("unexpected Zammad count payload")

    def fetch_window(
        self,
        since_days: int | None = None,
        until_days: int | None = None,
        extra_query: str = "",
    ) -> list[dict[str, Any]]:
        """One call fetching a whole time window (limit=500; date-only literals)."""
        clauses = _window_clauses(since_days, until_days)
        if (extra_query or "").strip():
            clauses.append(f"({extra_query.strip()})")
        return self.search_tickets(" AND ".join(clauses) or "*", limit=MAX_SEARCH_LIMIT)

    def _state_category_clause(self, state_category: str) -> str:
        """OR-clause for one state category, derived from state types.

        ``open`` is every state whose type is not a closed type — never the
        bare ``state.name:open`` trap (that matches only the one state
        *named* open). The live ``get_state_types()`` cache is merged over
        the known-state table (live wins); when states are unreachable the
        known table is the fail-closed fallback.
        """
        try:
            live = self.get_state_types()
        except ZammadError:
            live = {}
        merged = {name.lower(): type_id for name, type_id in _KNOWN_STATE_TYPES}
        merged.update(live)
        display = {name.lower(): name for name, _ in _KNOWN_STATE_TYPES}
        for lower in live:
            display.setdefault(lower, lower)
        closed_ids = {merged.get("closed"), merged.get("merged")}
        closed_ids.discard(None)
        if state_category == "closed":
            names = [name for name in ("closed", "merged") if name in merged]
        elif state_category == "pending":
            names = [
                display[lower]
                for lower, type_id in merged.items()
                if type_id in PENDING_STATE_TYPE_IDS
            ]
        else:
            names = [
                display[lower] for lower, type_id in merged.items() if type_id not in closed_ids
            ]
        if not names:
            raise ZammadError(f"no states known for category {state_category!r}")
        return "(" + " OR ".join(_state_term(name) for name in names) + ")"

    def build_query(
        self,
        state_category: str | None = None,
        since_days: int | None = None,
        until_days: int | None = None,
        extra_query: str = "",
    ) -> str:
        """Compose a Zammad search query from a category, window, and extra query.

        A lone extra query is returned as-is; combined clauses join with AND
        (the extra wrapped in parens, same as ``fetch_window``). No clauses
        at all yields ``*``. Read-only (one state-types lookup at most).
        """
        if state_category is not None and state_category not in VALID_STATE_CATEGORIES:
            raise ZammadError(f"state_category must be one of {sorted(VALID_STATE_CATEGORIES)}")
        clauses = _window_clauses(since_days, until_days)
        extra = (extra_query or "").strip()
        if state_category is not None:
            # Category first so the OR-group reads before the AND-window.
            clauses.insert(0, self._state_category_clause(state_category))
        if extra:
            if clauses:
                clauses.append(f"({extra})")
            else:
                return extra
        return " AND ".join(clauses) or "*"

    def get_state_types(self) -> dict[str, int]:
        """Map lower-cased state names to their state_type_id (cached, read-only).

        Open/closed/pending categories derive from these ids downstream —
        never from the bare ``state.name:open`` trap (that matches only the
        one state *named* open, not the open category).
        """
        global _state_types_cache
        if _state_types_cache is not None:
            return _state_types_cache
        payload = self._get("/api/v1/ticket_states")
        if isinstance(payload, dict):
            rows = payload.get("states")
        elif isinstance(payload, list):
            rows = payload
        else:
            rows = None
        if not isinstance(rows, list):
            raise ZammadError("unexpected Zammad state payload")
        mapping: dict[str, int] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = row.get("name")
            type_id = row.get("state_type_id")
            if isinstance(name, str) and name.strip() and isinstance(type_id, int):
                mapping[name.strip().lower()] = type_id
        if not mapping:
            raise ZammadError("unexpected Zammad state payload")
        _state_types_cache = mapping
        return mapping

    def resolve_user(self, user_id: int | str) -> str:
        """Resolve a Zammad user id to a display name (cached, read-only).

        Returns ``firstname lastname`` (fallback: ``login``). Automation
        logins (``jirasync@…``, ``-``, ``auto-*``) are returned as-is for
        the caller to flag.
        """
        try:
            uid = int(user_id)
        except (TypeError, ValueError) as exc:
            raise ZammadError("user id must be a positive integer") from exc
        if uid < 1:
            raise ZammadError("user id must be a positive integer")
        cached = self._user_cache.get(uid)
        if cached is not None:
            return cached
        payload = self._get(f"/api/v1/users/{uid}")
        if not isinstance(payload, dict):
            raise ZammadError("unexpected Zammad user payload")
        first = str(payload.get("firstname") or "").strip()
        last = str(payload.get("lastname") or "").strip()
        name = f"{first} {last}".strip() or str(payload.get("login") or "").strip() or str(uid)
        self._user_cache[uid] = name
        return name

    def search_tickets_by_terms(self, terms: list[str], limit: int = 10) -> list[dict[str, Any]]:
        """Search keywords and merge the matches. Read-only.

        Search semantics differ by instance: multi-word queries and field
        syntax only work with Elasticsearch. The all-terms-AND query runs
        first (exact on ES instances, usually empty on substring ones),
        then each term separately; matches merge by id, newest
        ``updated_at`` first (unknown timestamps last).
        """
        capped = self._coerce_limit(limit)
        totals = list(terms or [])[:MAX_KEYWORD_TERMS]
        merged: dict[Any, dict[str, Any]] = {}

        def _merge(rows: list[dict[str, Any]]) -> None:
            for row in rows:
                key = row.get("id")
                if key is None or key in merged:
                    continue
                merged[key] = row

        if len(totals) > 1:
            _merge(self.search_tickets(" AND ".join(totals), limit=capped))
        for term in totals:
            _merge(self.search_tickets(term, limit=capped))
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

    def list_tickets_page(self, page: int = 1, per_page: int = 50) -> list[dict[str, Any]]:
        """One page of visible tickets, newest updated first. Read-only.

        The list endpoint orders by id (oldest first), so the full visible
        list is fetched (up to ``MAX_REPORT_TICKETS``), sorted by
        ``updated_at`` and sliced here: recent conversations come first.
        """
        page_number = self._coerce_page(page)
        page_size = self._coerce_page_size(per_page)
        tickets = self.list_tickets(MAX_REPORT_TICKETS)
        tickets.sort(key=_updated_sort_key, reverse=True)
        start = (page_number - 1) * page_size
        return tickets[start : start + page_size]
