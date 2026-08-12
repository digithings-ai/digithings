"""Cloudflare D1-backed digivault note store (read path).

Queries D1 over its REST API, so the container needs no Worker binding — the same
approach ``digisearch``'s ``VectorizeBackend`` takes. Credentials are passed in, never
read from the environment inside this class; ``server.py`` does the env reading.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from digivault.d1_errors import D1StoreError as D1StoreError
from digivault.models import NoteDetail, NoteRow, VaultSearchHit

logger = logging.getLogger(__name__)

API_ROOT = "https://api.cloudflare.com/client/v4"

#: (url, headers, body, content_type) -> (status_code, response_text)
HttpPost = Callable[[str, dict[str, str], bytes, str], tuple[int, str]]

#: D1 caps bound parameters at 100 per query; batch writes well under it.
MAX_BOUND_PARAMS = 100

_FTS_TERM = re.compile(r"[A-Za-z0-9_]+")

# WHERE clause has 3 placeholders: `? = ''` skips the prefix filter entirely when
# the caller passed no prefix, `vault_path = ?` matches the prefix note itself, and
# `vault_path LIKE ?` matches everything under it. Together with the MATCH and LIMIT
# placeholders, callers must bind exactly 5 params, in this order: match, prefix,
# prefix, f"{prefix}/%", limit.
_SEARCH_SQL = """
SELECT n.vault_path, n.title, n.note_type, n.summary, n.body,
       n.tags, n.wikilinks, bm25(notes_fts) AS rank
FROM notes_fts
JOIN notes n ON n.rowid = notes_fts.rowid
WHERE notes_fts MATCH ?
  AND (? = '' OR n.vault_path = ? OR n.vault_path LIKE ?)
ORDER BY rank
LIMIT ?
"""

_GET_SQL = """
SELECT vault_path, title, note_type, summary, body, frontmatter,
       tags, wikilinks, parent_doc, segment_index
FROM notes WHERE vault_path = ?
"""

# Same 3-placeholder prefix filter as `_SEARCH_SQL`, plus LIMIT/OFFSET for paging:
# 5 params total, in order: prefix, prefix, f"{prefix}/%", page_size, offset.
_LIST_SQL = """
SELECT vault_path, title, frontmatter, body AS body_markdown
FROM notes
WHERE (? = '' OR vault_path = ? OR vault_path LIKE ?)
ORDER BY vault_path
LIMIT ? OFFSET ?
"""


def normalize_vault_path(value: str) -> str:
    """Canonical form: trimmed, no leading/trailing slash, at most one trailing ``.md`` removed."""
    path = (value or "").strip().strip("/")
    if path.endswith(".md"):
        path = path[: -len(".md")]
    return path


def build_fts_match(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    A raw user question is not valid FTS5 — ``"``, ``(``, ``*``, ``:`` and ``-`` are
    operators, so ``what is "page 13"?`` is a syntax error rather than a search. Each
    alphanumeric run is extracted and double-quoted, which makes every term a literal.
    Returns ``""`` when nothing searchable remains; callers must not issue a query then.
    """
    terms = _FTS_TERM.findall(query or "")
    return " ".join(f'"{t}"' for t in terms)


def _default_http_post(
    url: str, headers: dict[str, str], body: bytes, content_type: str
) -> tuple[int, str]:
    import httpx

    response = httpx.post(
        url, headers={**headers, "Content-Type": content_type}, content=body, timeout=60.0
    )
    return response.status_code, response.text


def _parse_response_body(text: str) -> dict[str, Any]:
    """Best-effort JSON parse of a D1 response body; ``{}`` on anything else.

    A non-JSON body (e.g. an HTML error page on a transport-level failure) must not
    raise out of the parser itself — the caller still needs to fall through to its
    own status-code-based error message.
    """
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rows_or_raise(operation: str, status: int, text: str) -> list[dict[str, Any]]:
    """Return the first statement's rows, or raise ``D1StoreError``.

    Checks the HTTP status *and* the body-level ``success``/``result`` fields: D1 can
    answer HTTP 200 with an application-level failure, which a status-only check misses.
    The API token is never interpolated into the message — only ``status``/``text``
    (D1 never echoes the request's Authorization header back in a response body) feed it.
    """
    body = _parse_response_body(text)
    if status >= 300 or body.get("success") is False or body.get("result") is None:
        errors = body.get("errors") or []
        detail = json.dumps(errors)[:500] if errors else text[:500]
        raise D1StoreError(f"d1 {operation} failed ({status}): {detail}")
    result = body.get("result") or []
    if not result:
        return []
    return list(result[0].get("results") or [])


def _json_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(v) for v in value)
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, ValueError):
        return ()
    return tuple(str(v) for v in parsed) if isinstance(parsed, list) else ()


def _json_obj(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


class D1Store:
    """Read-only D1 note store for one corpus. Writes go through scripts/d1_sync.py."""

    def __init__(
        self,
        database_id: str,
        *,
        account_id: str,
        api_token: str,
        http_post: HttpPost | None = None,
    ) -> None:
        self.database_id = database_id
        self._account_id = account_id
        self._api_token = api_token
        self._post = http_post or _default_http_post

    def _url(self) -> str:
        return f"{API_ROOT}/accounts/{self._account_id}/d1/database/{self.database_id}/query"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_token}"}

    def query(self, sql: str, params: list[Any], *, operation: str) -> list[dict[str, Any]]:
        """Execute one statement and return its rows. Raises ``D1StoreError`` on failure."""
        start = time.perf_counter()
        body = json.dumps({"sql": sql, "params": params}).encode()
        status, text = self._post(self._url(), self._headers(), body, "application/json")
        try:
            return _rows_or_raise(operation, status, text)
        except D1StoreError:
            logger.error(
                "d1 query failed",
                extra={
                    "operation": f"d1_{operation}",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                    "database_id": self.database_id,
                    "status_code": status,
                },
            )
            raise

    def search(
        self, query: str, *, limit: int = 7, path_prefix: str | None = None
    ) -> list[VaultSearchHit]:
        match = build_fts_match(query)
        if not match:
            return []
        prefix = normalize_vault_path(path_prefix or "")
        rows = self.query(
            _SEARCH_SQL,
            [match, prefix, prefix, f"{prefix}/%", limit],
            operation="search",
        )
        return [
            VaultSearchHit(
                vault_path=str(r.get("vault_path") or ""),
                title=str(r.get("title") or ""),
                note_type=str(r.get("note_type") or ""),
                summary=str(r.get("summary") or ""),
                body_markdown=str(r.get("body") or ""),
                tags=_json_list(r.get("tags")),
                wikilinks=_json_list(r.get("wikilinks")),
                rank=float(r.get("rank") or 0.0),
            )
            for r in rows
        ]

    def get_note(self, vault_path: str) -> NoteDetail | None:
        path = normalize_vault_path(vault_path)
        if not path:
            return None
        rows = self.query(_GET_SQL, [path], operation="get_note")
        if not rows:
            return None
        r = rows[0]
        return NoteDetail(
            vault_path=str(r.get("vault_path") or ""),
            title=str(r.get("title") or ""),
            note_type=str(r.get("note_type") or ""),
            summary=str(r.get("summary") or ""),
            body_markdown=str(r.get("body") or ""),
            frontmatter=_json_obj(r.get("frontmatter")),
            tags=_json_list(r.get("tags")),
            wikilinks=_json_list(r.get("wikilinks")),
            parent_doc=(str(r["parent_doc"]) if r.get("parent_doc") else None),
            segment_index=(int(r["segment_index"]) if r.get("segment_index") is not None else None),
        )

    def list_notes(self, *, path_prefix: str | None = None, page_size: int = 500) -> list[NoteRow]:
        if page_size <= 0:
            raise ValueError(f"page_size must be positive, got {page_size}")
        prefix = normalize_vault_path(path_prefix or "")
        out: list[NoteRow] = []
        offset = 0
        while True:
            rows = self.query(
                _LIST_SQL,
                [prefix, prefix, f"{prefix}/%", page_size, offset],
                operation="list_notes",
            )
            # `frontmatter` is a TEXT column (JSON-encoded) in D1; `NoteRow.frontmatter`
            # is typed `dict`, and pydantic v2 rejects a raw string for a dict field
            # (it does not auto-parse JSON), so it must be decoded before validation.
            out.extend(
                NoteRow.model_validate({**r, "frontmatter": _json_obj(r.get("frontmatter"))})
                for r in rows
            )
            if len(rows) < page_size:
                return out
            offset += page_size
