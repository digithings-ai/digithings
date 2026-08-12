"""Cloudflare D1-backed digivault note store (read path).

Queries D1 over its REST API, so the container needs no Worker binding — the same
approach ``digisearch``'s ``VectorizeBackend`` takes. Credentials are passed in, never
read from the environment inside this class; ``server.py`` does the env reading.
"""

from __future__ import annotations

import json
import logging
import random
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

#: (seconds) -> None. Injected the same way as `HttpPost` above so a unit test can
#: record requested backoff durations instead of `query()` actually blocking on
#: `time.sleep` between retries.
SleepFn = Callable[[float], None]

_FTS_TERM = re.compile(r"\w+")

#: Safety cap on `list_notes` pagination. A backend that keeps returning full pages
#: (broken prefix filter, server bug) would otherwise loop until the process is
#: killed, burning one metered D1 API call per iteration — a reviewer verified this by
#: aborting a real run at 2000 requests. 500 pages at the default `page_size=500` is
#: 250k rows, comfortably above any real client-vault corpus (see CLAUDE.md's target
#: market: small/personal vaults, not institutional scale).
MAX_LIST_PAGES = 500

#: Bounded retry policy for `D1Store.query()` (#2239 follow-up M6). `query()` is the
#: synchronous read path a chat turn blocks on, so the bound stays modest: 3 total
#: attempts (2 retries) with exponential backoff starting at a quarter second. See
#: `_is_retryable_status` for exactly which failures this applies to.
MAX_ATTEMPTS = 3
INITIAL_BACKOFF_SECONDS = 0.25
BACKOFF_MULTIPLIER = 2.0
#: Kept strictly below `BACKOFF_MULTIPLIER - 1`. A jittered delay for attempt N is at
#: most `base(N) * (1 + RETRY_JITTER_FRACTION)`; the un-jittered floor for attempt
#: N + 1 is `base(N) * BACKOFF_MULTIPLIER`. Because 1 + RETRY_JITTER_FRACTION <
#: BACKOFF_MULTIPLIER, the jittered delay for N can never reach N + 1's floor —
#: backoff durations are strictly increasing across retries regardless of the random
#: draw, which is what lets a test assert growth without controlling or injecting the
#: random source itself.
RETRY_JITTER_FRACTION = 0.2

# WHERE clause has 3 placeholders: `? = ''` skips the prefix filter entirely when
# the caller passed no prefix, `vault_path = ?` matches the prefix note itself, and
# `vault_path LIKE ? ESCAPE '\'` matches everything under it. The LIKE pattern's
# prefix component must be escaped with `_escape_like` before binding — `_` and `%`
# are LIKE wildcards, and an unescaped client prefix containing either leaks rows from
# a sibling corpus (e.g. prefix `clients/my_corp` would also match
# `clients/myXcorp/...` without escaping). The `? = ''` and `vault_path = ?` legs bind
# the *unescaped* normalized prefix — they're equality checks, not LIKE patterns.
# Together with the MATCH and LIMIT placeholders, callers must bind exactly 5 params,
# in this order: match, prefix, prefix, f"{escaped_prefix}/%", limit.
_SEARCH_SQL = """
SELECT n.vault_path, n.title, n.note_type, n.summary, n.body,
       n.tags, n.wikilinks, bm25(notes_fts) AS rank
FROM notes_fts
JOIN notes n ON n.rowid = notes_fts.rowid
WHERE notes_fts MATCH ?
  AND (? = '' OR n.vault_path = ? OR n.vault_path LIKE ? ESCAPE '\\')
ORDER BY rank
LIMIT ?
"""

_GET_SQL = """
SELECT vault_path, title, note_type, summary, body, frontmatter,
       tags, wikilinks, parent_doc, segment_index
FROM notes WHERE vault_path = ?
"""

# Same 3-placeholder prefix filter as `_SEARCH_SQL` (see its comment for the escaping
# requirement), plus LIMIT/OFFSET for paging: 5 params total, in order: prefix, prefix,
# f"{escaped_prefix}/%", page_size, offset.
_LIST_SQL = """
SELECT vault_path, title, frontmatter, body AS body_markdown
FROM notes
WHERE (? = '' OR vault_path = ? OR vault_path LIKE ? ESCAPE '\\')
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
    ``\\w+`` run (Unicode-aware — matches accented Latin, Chinese, Cyrillic, and this
    vault's Romanian ``ș``/``ț``/``ă``, not just ASCII) is extracted and double-quoted
    (with any embedded ``"`` doubled, defensively — ``\\w`` cannot itself match one, but
    a future change to the term regex must not reopen the FTS5-injection risk this
    guards against), which makes every term a literal. Returns ``""`` when nothing
    searchable remains; callers must not issue a query then.

    Terms are joined with ``OR``, not FTS5's implicit-AND space join. digigraph passes
    the *whole user question* as the query, and AND-joining means every one of "what",
    "is", "the", etc. must appear in a note for it to match at all — verified against a
    real FTS5 index that this makes ``"what is on page 13 of the OCC filing?"`` return
    zero rows even though a note titled "OCC filing notes" discussing page 13 exists.
    OR-join plus the existing ``ORDER BY bm25(...)`` and ``LIMIT`` lets ranking do the
    selection instead: bm25 is IDF-weighted, so a note matching only "OCC" and "page"
    and "13" still outranks one that only happens to contain "the" and "is".

    Chose OR-ranking over `local_search.py`'s `_STOPWORDS` approach deliberately: a
    hand-maintained stopword set is per-language (that one is English-only), and this
    vault serves Romanian content too — a second list would need maintaining in
    lockstep, and a query mixing both languages would still leak whichever list is
    missing. bm25's IDF term already down-weights common words in *any* language
    without a list to keep in sync, and OR-join never returns *fewer* rows than
    AND-join would have for the same query, only ranks them — so it strictly subsumes
    what stopword-stripping was buying in `local_search.py`.
    """
    terms = _FTS_TERM.findall(query or "")
    return " OR ".join(f'"{t.replace(chr(34), chr(34) * 2)}"' for t in terms)


def _escape_like(value: str) -> str:
    """Escape ``\\``, ``%`` and ``_`` so ``value`` is a literal LIKE prefix, not a pattern.

    ``%`` and ``_`` are LIKE wildcards; binding a caller-supplied path prefix into a
    ``LIKE ?`` pattern without escaping them lets ``_`` in a prefix match any single
    character and leak a sibling corpus's rows across the tenant-isolation boundary —
    verified: an unescaped prefix ``clients/my_corp`` also matches
    ``clients/myXcorp/...``. Must be paired with ``LIKE ? ESCAPE '\\'`` in the SQL and
    applied only to the prefix component, never the trailing ``/%`` wildcard suffix.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def resolve_path_prefix(path_prefix: str | None) -> str:
    """Normalize ``path_prefix``, keeping "no prefix" distinct from "empty prefix".

    Public (no leading underscore) because it is shared across a module boundary:
    this module's own ``search``/``list_notes`` use it for the SQL ``? = ''`` filter
    below, and ``server.py``'s ``POST /v1/notes/by-path`` route uses this same
    function to decide whether a caller-supplied prefix counts as "no scoping
    requested," before doing its own (non-SQL) startswith check. Sharing one
    function means the two enforcement points cannot drift apart on what "empty"
    means — the #2239 review found the by-path route had reimplemented (and gotten
    wrong) exactly this semantics with a plain ``if prefix and ...`` check that
    fails open on a non-``None`` prefix normalizing to empty.

    ``None`` means the caller deliberately wants no filtering, and every row (or,
    on the by-path route, every path) is a legitimate match. Any other value is a
    prefix the caller *does* intend to scope to; if it normalizes to the empty
    string (``"/"``, ``".md"``, ``"   "``, ``"///"``, ...) the SQL's ``? = ''``
    branch would otherwise match every row too — but here that is a caller bug, not
    an isolation boundary anyone asked to skip, and on a multi-tenant read path
    fail-open is the wrong default. Raise instead: pass ``None`` explicitly to opt
    out of prefix scoping.
    """
    if path_prefix is None:
        return ""
    normalized = normalize_vault_path(path_prefix)
    if not normalized:
        raise ValueError(
            f"path_prefix {path_prefix!r} normalizes to an empty prefix, which would "
            "silently disable prefix scoping instead of enforcing it; pass "
            "path_prefix=None explicitly to opt out of scoping"
        )
    return normalized


def _default_http_post(
    url: str, headers: dict[str, str], body: bytes, content_type: str
) -> tuple[int, str]:
    import httpx

    response = httpx.post(
        url, headers={**headers, "Content-Type": content_type}, content=body, timeout=60.0
    )
    return response.status_code, response.text


def _default_sleep(seconds: float) -> None:
    time.sleep(seconds)


def _is_retryable_status(status: int) -> bool:
    """Transient-looking HTTP statuses worth a bounded retry.

    429 and 5xx are the uncontroversial cases. 401 is deliberately included even
    though a genuinely wrong or revoked token also 401s deterministically and a
    retry will not fix that: verified in production (#2239) — a live D1 cutover hit
    three transient 401s in one session (once at row 54 of a 145-call backfill,
    twice during `get_note` loops), almost certainly because an operator was editing
    the API token in the Cloudflare dashboard, which briefly invalidates it across
    the edge. 20/20 and then 60/60 sequential queries succeeded cleanly immediately
    before and after, so the failures were genuinely transient rather than a wrong
    token surfacing deterministically. A bounded retry costs at most one extra
    backoff step (~1-2s) in the genuinely-wrong-token case, and the final error still
    carries its real status and detail — this is a deliberate bet that the observed
    transient case is common enough on this path to be worth that cost.

    400, 403, 404, 422, and any other 4xx are excluded: they are deterministic client
    errors that an identical second request cannot fix, so retrying would only delay
    a clear error reaching the caller — a 403 from a wrongly-scoped token must fail
    fast, not eat a retry budget first.
    """
    return status == 401 or status == 429 or 500 <= status < 600


def _backoff_seconds(attempt: int) -> float:
    """Delay before the retry following ``attempt`` (1-indexed: the attempt that just failed).

    Exponential (``INITIAL_BACKOFF_SECONDS * BACKOFF_MULTIPLIER ** (attempt - 1)``)
    plus jitter bounded by ``RETRY_JITTER_FRACTION`` — see that constant's comment for
    why growth across attempts stays monotonic despite the jitter.
    """
    base = INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER ** (attempt - 1))
    return base + base * random.random() * RETRY_JITTER_FRACTION


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
        sleep: SleepFn | None = None,
    ) -> None:
        self.database_id = database_id
        self._account_id = account_id
        self._api_token = api_token
        self._post = http_post or _default_http_post
        self._sleep = sleep or _default_sleep

    def _url(self) -> str:
        return f"{API_ROOT}/accounts/{self._account_id}/d1/database/{self.database_id}/query"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_token}"}

    def query(self, sql: str, params: list[Any], *, operation: str) -> list[dict[str, Any]]:
        """Execute one statement and return its rows. Raises ``D1StoreError`` on failure.

        Retries up to ``MAX_ATTEMPTS`` total attempts (see that constant) when the
        failure looks transient: a transport error (``httpx.HTTPError`` — connect,
        read timeout, DNS, remote protocol) or a status ``_is_retryable_status``
        accepts (429, 5xx, and 401 — see that function's docstring for why 401 is
        included). Every other failure — 400, 403, 404, 422, any other 4xx, or a 2xx
        response carrying an application-level ``success: false`` — raises on the
        first attempt: retrying a deterministic client error would only delay a clear
        message the caller could otherwise act on immediately. Backoff between
        retries is exponential with jitter (``_backoff_seconds``); the delay is passed
        to the injected ``sleep`` (constructor arg, defaults to ``time.sleep``) so
        tests can assert on requested durations without actually waiting. Each retry
        is logged at ``warning`` before sleeping, so an operator sees the retries
        happening rather than only their eventual outcome.

        This also retries writes, not just reads — ``scripts/d1_sync.py`` calls this
        same method for schema init, the notes upsert, and the FTS rebuild. That is
        safe because all three are idempotent by construction: ``d1_schema.sql``'s DDL
        is ``CREATE ... IF NOT EXISTS``, the upsert is
        ``... ON CONFLICT(vault_path) DO UPDATE`` (updates in place rather than
        delete-and-reinsert), and ``INSERT INTO notes_fts(notes_fts) VALUES('rebuild')``
        fully rebuilds the FTS index from ``notes`` rather than appending to it — none
        of the three can duplicate rows or corrupt state if D1 actually applied a call
        whose response this store never saw before retrying it.

        The final raised error is identical in shape to what a non-retrying call would
        have raised: still ``D1StoreError``, built the same way (``_rows_or_raise``, or
        the transport-failure message below) regardless of how many attempts preceded
        it, and the API token is never referenced when building it (see the transport
        branch's own note on ``exc.request`` below). Only ``httpx.HTTPError`` is
        treated as a retryable transport failure, not a bare ``Exception`` — a
        programming error inside an injected ``http_post`` (e.g. a ``TypeError``) must
        still propagate as itself on the first attempt, not get relabelled or retried
        as a transport failure.
        """
        import httpx

        start = time.perf_counter()
        body = json.dumps({"sql": sql, "params": params}).encode()
        for attempt in range(1, MAX_ATTEMPTS + 1):
            is_last_attempt = attempt == MAX_ATTEMPTS
            try:
                status, text = self._post(self._url(), self._headers(), body, "application/json")
            except httpx.HTTPError as exc:
                # Deliberately builds the message from `str(exc)` and never touches
                # `exc.request` — httpx attaches the original request, headers
                # included, to its transport exceptions, and that request carries
                # this store's `Authorization: Bearer <token>` header; referencing it
                # here would leak the credential into any log line or error response
                # built from the raised error.
                if not is_last_attempt:
                    logger.warning(
                        "d1 query transport failure, retrying",
                        extra={
                            "operation": f"d1_{operation}",
                            "duration_ms": int((time.perf_counter() - start) * 1000),
                            "outcome": "retry",
                            "database_id": self.database_id,
                            "status_code": None,
                            "attempt": attempt,
                            "error_type": type(exc).__name__,
                        },
                    )
                    self._sleep(_backoff_seconds(attempt))
                    continue
                logger.error(
                    "d1 query transport failure",
                    extra={
                        "operation": f"d1_{operation}",
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "outcome": "error",
                        "database_id": self.database_id,
                        "error_type": type(exc).__name__,
                    },
                )
                raise D1StoreError(f"d1 {operation} transport failure: {exc}") from exc

            if _is_retryable_status(status) and not is_last_attempt:
                logger.warning(
                    "d1 query failed, retrying",
                    extra={
                        "operation": f"d1_{operation}",
                        "duration_ms": int((time.perf_counter() - start) * 1000),
                        "outcome": "retry",
                        "database_id": self.database_id,
                        "status_code": status,
                        "attempt": attempt,
                    },
                )
                self._sleep(_backoff_seconds(attempt))
                continue

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

        # Unreachable: `is_last_attempt` is True exactly when `attempt == MAX_ATTEMPTS`,
        # and every branch above either returns or raises on the last attempt — the
        # loop can never fall through to a `MAX_ATTEMPTS + 1`th iteration. Present only
        # so a type checker sees every path returning or raising.
        raise AssertionError("d1 query retry loop exited without returning or raising")

    def search(
        self, query: str, *, limit: int = 7, path_prefix: str | None = None
    ) -> list[VaultSearchHit]:
        match = build_fts_match(query)
        if not match:
            return []
        prefix = resolve_path_prefix(path_prefix)
        rows = self.query(
            _SEARCH_SQL,
            [match, prefix, prefix, f"{_escape_like(prefix)}/%", limit],
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
        frontmatter = _json_obj(r.get("frontmatter"))
        # segment_label has no column of its own (unlike segment_index) — it is
        # written into a chunked note's frontmatter at ingestion time
        # (scripts/vectorize_sync.py) and lives in the `frontmatter` jsonb blob
        # already parsed above. Mirrored onto its own field so a consumer of the
        # brief's documented shape (vault_path, title, body_markdown, frontmatter,
        # segment_label) finds it without having to know it is also nested inside
        # `frontmatter`.
        segment_label = frontmatter.get("segment_label")
        return NoteDetail(
            vault_path=str(r.get("vault_path") or ""),
            title=str(r.get("title") or ""),
            note_type=str(r.get("note_type") or ""),
            summary=str(r.get("summary") or ""),
            body_markdown=str(r.get("body") or ""),
            frontmatter=frontmatter,
            tags=_json_list(r.get("tags")),
            wikilinks=_json_list(r.get("wikilinks")),
            segment_label=(str(segment_label) if segment_label is not None else None),
            parent_doc=(str(r["parent_doc"]) if r.get("parent_doc") else None),
            segment_index=(int(r["segment_index"]) if r.get("segment_index") is not None else None),
        )

    def list_notes(self, *, path_prefix: str | None = None, page_size: int = 500) -> list[NoteRow]:
        if page_size <= 0:
            raise ValueError(f"page_size must be positive, got {page_size}")
        prefix = resolve_path_prefix(path_prefix)
        escaped_prefix = _escape_like(prefix)
        out: list[NoteRow] = []
        offset = 0
        pages = 0
        while True:
            if pages >= MAX_LIST_PAGES:
                raise D1StoreError(
                    f"list_notes exceeded {MAX_LIST_PAGES} pages (page_size={page_size}) "
                    "without exhausting results; aborting rather than looping "
                    "unbounded against a metered API"
                )
            rows = self.query(
                _LIST_SQL,
                [prefix, prefix, f"{escaped_prefix}/%", page_size, offset],
                operation="list_notes",
            )
            pages += 1
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
