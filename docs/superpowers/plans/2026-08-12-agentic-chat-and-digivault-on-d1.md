# Agentic chat + digivault on Cloudflare D1 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move digivault's two chat corpora from Supabase to Cloudflare D1, add a `digivault_get_note` addressing primitive, then delete the retrieval prefetch so the already-working `digillm.run_tools` loop drives retrieval and the model can do locate-then-load.

**Architecture:** `D1Store` is a REST client over `POST /accounts/{id}/d1/database/{db}/query`, built as a near-copy of `VectorizeBackend` — credentials passed in, an injectable `HttpPost` transport seam, and a body-level success check. Search is SQLite FTS5; addressing is a primary-key lookup on `vault_path`. digivault selects it by config presence, ahead of Supabase and the filesystem vault. Part 2 is then almost entirely deletion: removing the prefetch block un-empties the tool list that `run_tools` already receives.

**Tech Stack:** Python 3.12, pydantic v2, httpx, FastAPI, pytest; Cloudflare D1 (SQLite + FTS5) and Vectorize; TypeScript for the Worker.

**Spec:** [2026-08-12-agentic-chat-and-digivault-on-d1-design.md](../specs/2026-08-12-agentic-chat-and-digivault-on-d1-design.md)

## Global Constraints

- **Polars only — never pandas.** Pydantic v2 everywhere; strict typing; ruff-compliant, line length 100.
- **digi names are lowercase in all prose, docs, comments, commit messages and PR text** — `digivault`, not DigiVault. Code identifiers keep language casing.
- **Never hand-edit `.claude/`** — edit `agents/sources/` and run `make agents-init`.
- `make score` must pass on staged changes: Security ≥ 8, Quality ≥ 8, Optimization ≥ 7, Accuracy ≥ 9.
- **Credentials are passed into constructors, never read from `os.environ` inside a store class.** Env reading happens at the call site (the `_stub.py` / `from_env` pattern).
- **The error type lives in its own module.** A failing `from mod import A, B` binds neither name, so an exception class used to wrap that module's own ImportError must not live inside it. Mirror `vectorize_errors.py` exactly.
- **Two databases, never one shared table with a filter.** `digithings_docs` and `occ_help`, matching `DIGI_TENANT_CORPUS_MAP` in `frontend/digithings-stack-cloudflare/wrangler.toml:85` and the two existing Vectorize index names.
- **Canonical `vault_path` carries no `.md` suffix.** Normalise by stripping at most one trailing `.md` at every boundary.
- D1 hard limits to respect: max SQL statement 100,000 bytes; **max 100 bound parameters per query**; max row 2,000,000 bytes.
- `VECTORIZE_*` established the container-config pattern: a new env var must be added to **both** `envVars` (`src/index.ts:41-72`) and the `Env` interface (`src/index.ts:112-139`). They are hand-kept in sync.

## Prerequisite (human, blocking Task 4 onward)

A Cloudflare API token with **D1 edit** permission. Verified 2026-08-12: the current token lists Vectorize indexes fine but returns `{"code": 10000, "message": "Authentication error"}` on `GET /accounts/{id}/d1/database`. Tasks 1–3 are pure code and can proceed without it.

## File Structure

**Created**

| File | Responsibility |
|---|---|
| `digivault/src/digivault/d1_errors.py` | `D1StoreError` only. Its own module so it survives an ImportError of `d1_store`. |
| `digivault/src/digivault/d1_store.py` | `D1Store`: REST transport, `search()` (FTS5), `get_note()` (PK lookup), `list_notes()`. |
| `digivault/src/digivault/d1_schema.sql` | The DDL, one source of truth shared by the sync script and tests. |
| `scripts/d1_sync.py` | Publishes a vault (or a one-time Supabase read) into a D1 database. |
| `tests/dv/test_d1_store.py` | `D1Store` unit tests with an injected transport. |
| `tests/scripts/test_d1_sync.py` | Sync batching, SQL shape, and prefix filtering. |

**Modified**

| File | Change |
|---|---|
| `digivault/src/digivault/server.py:341` | Backend precedence gains D1 ahead of Supabase; new `POST /v1/notes/by-path` route. |
| `digivault/src/digivault/models.py` | New `NoteDetail` response model (body + frontmatter together — no existing model carries both). |
| `digivault/src/digivault/orchestrator_tools.py` | New `digivault_get_note` manifest entry. |
| `scripts/vectorize_sync.py:309-353` | Read notes from D1 instead of Supabase. |
| `frontend/digithings-stack-cloudflare/src/index.ts` | `D1_ACCOUNT_ID`, `D1_API_TOKEN`, `D1_DATABASE_MAP` in `envVars` **and** `Env`. |
| `frontend/digithings-stack-cloudflare/container/entrypoint.sh` | Export the three D1 vars. `DIGIVAULT_ROOT` handling is deliberately untouched. |
| `.github/workflows/docs-onboard-digithings.yml:144-187` | Swap `CORE_SUPABASE_*` secrets and `sync_onboard_vault.py` for `D1_*` and `d1_sync.py`. |
| `digigraph/src/digigraph/graph/research.py` | Delete prefetch (401-429), context injection (469-475), strip (477-479); pass `max_tool_rounds`. |
| `tests/dg/test_research_prefetch.py` | Four of five tests invert or are deleted. |
| `infra/digichat-release/config/digiproject.yaml`, `config/dogfood-digiproject.yaml`, `docs/projects/{digithings,online-compliance-center}/digiproject.yaml` | Add `digivault_get_note`; drop the "already prefetched" prompt line. |
| `digigraph/ARCHITECTURE.md:397` | Documents the strip; must describe the tool loop instead. |
| `digivault/ARCHITECTURE.md` | Document the D1 backend and its precedence. |

**Deleted**

| File | Reason |
|---|---|
| `_format_prefetch_context`, `_tool_definition_name`, `_strip_tools_by_name` in `research.py:265-317` | Only exist to serve the prefetch. |

### Schema deviation from the spec — read this

The spec's schema listed six columns. The real `VaultSearchHit` contract
(`digivault/src/digivault/supabase_store.py:36`) requires `vault_path, title, note_type,
summary, body_markdown, tags, wikilinks, rank`. To return that model without inventing
values, the table carries those columns explicitly rather than digging them out of the
frontmatter JSON at query time. This is a deliberate, documented widening of the spec.

---

## Part 1 — digivault on D1

### Task 1: `D1Store` — REST client, FTS5 search, get-by-path

**Files:**
- Create: `digivault/src/digivault/d1_errors.py`
- Create: `digivault/src/digivault/d1_schema.sql`
- Create: `digivault/src/digivault/d1_store.py`
- Test: `tests/dv/test_d1_store.py`

> **Pre-flight correction (2026-08-12).** `VaultSearchHit` is defined in
> `digivault/src/digivault/supabase_store.py:36`, **not** in `models.py`. Importing it
> from there would make the D1 path depend on the Supabase module — the opposite of this
> spec's goal. **Move `VaultSearchHit` to `digivault/src/digivault/models.py`** and
> re-export it from `supabase_store.py` (`from digivault.models import VaultSearchHit as
> VaultSearchHit`) so existing importers keep working. `d1_store.py` then imports it
> from `models`. There is an existing test importing it from `supabase_store`; the
> re-export must keep that green.

**Interfaces:**
- Consumes: `VaultSearchHit` (moved to `models` — see above) and `NoteRow`.
- Produces: `D1Store(database_id, *, account_id, api_token, http_post=None)`;
  `.search(query: str, *, limit: int = 7, path_prefix: str | None = None) -> list[VaultSearchHit]`;
  `.get_note(vault_path: str) -> NoteDetail | None`;
  `.list_notes(*, path_prefix: str | None = None, page_size: int = 500) -> list[NoteRow]`;
  `D1StoreError`; `HttpPost = Callable[[str, dict[str,str], bytes, str], tuple[int,str]]`;
  `normalize_vault_path(value: str) -> str`.

- [ ] **Step 1: Write `d1_errors.py`**

```python
"""Isolated exception type for D1 store failures.

``D1StoreError`` lives in its own module, decoupled from ``d1_store.py``, so it stays
importable even when importing the heavier ``d1_store`` module itself fails. A failing
``from digivault.d1_store import D1Store, D1StoreError`` binds NEITHER name, so an
``except D1StoreError`` afterwards would raise ``NameError`` instead of the intended
wrapped error. Mirrors ``digisearch/src/digisearch/indexes/backends/vectorize_errors.py``.
"""

from __future__ import annotations


class D1StoreError(RuntimeError):
    """Raised when D1 is unconfigured, or a query fails.

    Subclasses ``RuntimeError`` to match ``SupabaseStoreError`` so
    ``digivault/src/digivault/server.py``'s existing 503 handler covers both stores.
    """
```

- [ ] **Step 2: Write `d1_schema.sql`**

```sql
-- digivault note store for one corpus. Applied by scripts/d1_sync.py --init.
CREATE TABLE IF NOT EXISTS notes (
  vault_path    TEXT PRIMARY KEY,          -- canonical: NO .md suffix
  title         TEXT NOT NULL DEFAULT '',
  note_type     TEXT NOT NULL DEFAULT '',
  summary       TEXT NOT NULL DEFAULT '',
  body          TEXT NOT NULL DEFAULT '',
  frontmatter   TEXT NOT NULL DEFAULT '{}',  -- JSON object
  tags          TEXT NOT NULL DEFAULT '[]',  -- JSON array
  wikilinks     TEXT NOT NULL DEFAULT '[]',  -- JSON array
  parent_doc    TEXT,
  segment_index INTEGER,
  updated_at    TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS notes_parent ON notes(parent_doc, segment_index);

-- External-content FTS5: the index references notes rather than copying its text.
CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts
  USING fts5(title, summary, body, content='notes', content_rowid='rowid');
```

- [ ] **Step 3: Write the failing tests**

```python
"""Unit tests for the D1-backed digivault store (no network)."""

from __future__ import annotations

import json

import pytest
from digivault.d1_errors import D1StoreError
from digivault.d1_store import D1Store, build_fts_match, normalize_vault_path


class _RecordingPost:
    """Injected transport: records calls, replays canned responses."""

    def __init__(self, responses: list[tuple[int, str]]) -> None:
        self.calls: list[tuple[str, dict[str, str], bytes, str]] = []
        self._responses = list(responses)

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        self.calls.append((url, headers, body, content_type))
        return self._responses.pop(0)


def _ok(rows: list[dict]) -> tuple[int, str]:
    return 200, json.dumps({"success": True, "errors": [], "result": [{"results": rows}]})


def _store(responses: list[tuple[int, str]]) -> tuple[D1Store, _RecordingPost]:
    post = _RecordingPost(responses)
    return D1Store("db-123", account_id="acct-1", api_token="tok", http_post=post), post


@pytest.mark.unit
def test_normalize_strips_exactly_one_md_suffix() -> None:
    assert normalize_vault_path("clients/x/page.md") == "clients/x/page"
    assert normalize_vault_path("clients/x/page") == "clients/x/page"
    assert normalize_vault_path("clients/x/page.md.md") == "clients/x/page.md"
    assert normalize_vault_path("  /clients/x/page.md  ") == "clients/x/page"


@pytest.mark.unit
def test_build_fts_match_quotes_terms_so_punctuation_cannot_break_syntax() -> None:
    # Bare FTS5 MATCH treats " ( * : - as syntax; a raw user question is not valid FTS5.
    assert build_fts_match('what is "page 13" (OCC)?') == '"what" "is" "page" "13" "OCC"'
    assert build_fts_match("   ") == ""


@pytest.mark.unit
def test_search_posts_to_the_query_endpoint_with_bound_params() -> None:
    store, post = _store([_ok([{
        "vault_path": "clients/x/a", "title": "A", "note_type": "page",
        "summary": "s", "body": "hello", "tags": "[]", "wikilinks": "[]", "rank": -1.5,
    }])])
    hits = store.search("hello world", limit=3, path_prefix="clients/x")

    url, headers, body, content_type = post.calls[0]
    assert url == (
        "https://api.cloudflare.com/client/v4/accounts/acct-1/d1/database/db-123/query"
    )
    assert headers == {"Authorization": "Bearer tok"}
    assert content_type == "application/json"
    payload = json.loads(body)
    assert "notes_fts MATCH ?" in payload["sql"]
    assert payload["params"] == ['"hello" "world"', "clients/x", "clients/x/%", 3]
    assert len(hits) == 1
    assert hits[0].vault_path == "clients/x/a"
    assert hits[0].body_markdown == "hello"


@pytest.mark.unit
def test_search_with_blank_query_makes_no_http_call() -> None:
    store, post = _store([])
    assert store.search("   ", limit=3) == []
    assert post.calls == []


@pytest.mark.unit
def test_get_note_returns_none_on_empty_result_and_parses_json_columns() -> None:
    store, post = _store([_ok([])])
    assert store.get_note("clients/x/missing") is None

    store2, _ = _store([_ok([{
        "vault_path": "clients/x/a", "title": "A", "note_type": "page", "summary": "s",
        "body": "# hi", "frontmatter": '{"page_class":"pdf_page"}', "tags": '["t"]',
        "wikilinks": "[]", "parent_doc": "doc-1", "segment_index": 13,
    }])])
    note = store2.get_note("clients/x/a.md")  # .md must be normalised away
    assert note is not None
    assert note.vault_path == "clients/x/a"
    assert note.frontmatter == {"page_class": "pdf_page"}
    assert note.tags == ("t",)
    assert note.segment_index == 13


@pytest.mark.unit
def test_non_2xx_raises_d1_store_error_without_leaking_the_token() -> None:
    store, _ = _store([(403, json.dumps({"success": False, "errors": [{"code": 10000}]}))])
    with pytest.raises(D1StoreError) as exc:
        store.search("hello")
    assert "tok" not in str(exc.value)
    assert "(403)" in str(exc.value)


@pytest.mark.unit
def test_http_200_with_success_false_still_raises() -> None:
    # Cloudflare answers 200 with an application-level failure; a status-only check misses it.
    store, _ = _store([(200, json.dumps({"success": False, "errors": [], "result": None}))])
    with pytest.raises(D1StoreError):
        store.search("hello")
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/dv/test_d1_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'digivault.d1_store'`

- [ ] **Step 5: Write `d1_store.py`**

```python
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

_LIST_SQL = """
SELECT vault_path, title, frontmatter, body AS body_markdown
FROM notes
WHERE (? = '' OR vault_path = ? OR vault_path LIKE ?)
ORDER BY vault_path
LIMIT ? OFFSET ?
"""


def normalize_vault_path(value: str) -> str:
    """Canonical form: trimmed, no leading slash, at most one trailing ``.md`` removed."""
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
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _rows_or_raise(operation: str, status: int, text: str) -> list[dict[str, Any]]:
    """Return the first statement's rows, or raise ``D1StoreError``.

    Checks the HTTP status *and* the body-level ``success``/``result`` fields: D1 can
    answer HTTP 200 with an application-level failure, which a status-only check misses.
    The API token is never interpolated into the message.
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

    def list_notes(
        self, *, path_prefix: str | None = None, page_size: int = 500
    ) -> list[NoteRow]:
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
            out.extend(NoteRow.model_validate(r) for r in rows)
            if len(rows) < page_size:
                return out
            offset += page_size
```

- [ ] **Step 6: Add `NoteDetail` to `digivault/src/digivault/models.py`**

Append after `NoteRow` (no existing model carries body *and* frontmatter together):

```python
class NoteDetail(BaseModel):
    """One note, whole: body and frontmatter together.

    ``Note`` has frontmatter but no body; ``NoteRow``/``VaultSearchHit`` have a body but
    no frontmatter. ``digivault_get_note`` needs both, so this model exists.
    """

    model_config = ConfigDict(frozen=True)

    vault_path: str
    title: str = ""
    note_type: str = ""
    summary: str = ""
    body_markdown: str = ""
    frontmatter: dict = Field(default_factory=dict)
    tags: tuple[str, ...] = Field(default=())
    wikilinks: tuple[str, ...] = Field(default=())
    parent_doc: str | None = None
    segment_index: int | None = None
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/dv/test_d1_store.py -v`
Expected: PASS, 7 tests

- [ ] **Step 8: Lint and commit**

```bash
ruff check digivault scripts tests && ruff format --check digivault tests
git add digivault/src/digivault/d1_errors.py digivault/src/digivault/d1_store.py digivault/src/digivault/d1_schema.sql digivault/src/digivault/models.py tests/dv/test_d1_store.py
git commit -m "feat(digivault): D1-backed note store with FTS5 search and get-by-path"
```

---

### Task 2: digivault serves D1 — backend precedence and the by-path route

**Files:**
- Modify: `digivault/src/digivault/server.py:341` (search precedence) and the route block at `:224`
- Test: `tests/dv/test_server.py`

**Interfaces:**
- Consumes: `D1Store`, `D1StoreError`, `NoteDetail`, `normalize_vault_path` from Task 1.
- Produces: `_open_d1_store() -> D1Store`; route `POST /v1/notes/by-path` returning `NoteDetail`; env contract `D1_ACCOUNT_ID`, `D1_API_TOKEN`, `D1_DATABASE_MAP` (JSON `{"<vault-prefix>": "<database id>"}`).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.unit
def test_search_prefers_d1_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIVAULT_ROOT", "/data/vault")   # must NOT win
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", '{"clients/digithings": "db-1"}')
    called: dict = {}

    class _FakeD1:
        def search(self, query, *, limit, path_prefix):
            called["args"] = (query, limit, path_prefix)
            return []

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    body = server_search(query="jwt", limit=3, path_prefix="clients/digithings")
    assert called["args"] == ("jwt", 3, "clients/digithings")
    assert body["hits"] == []


@pytest.mark.unit
def test_open_d1_store_raises_when_prefix_has_no_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    monkeypatch.setenv("D1_DATABASE_MAP", '{"clients/digithings": "db-1"}')
    with pytest.raises(D1StoreError) as exc:
        server._open_d1_store("clients/other")
    assert "clients/other" in str(exc.value)


@pytest.mark.unit
def test_get_note_by_path_returns_404_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeD1:
        def get_note(self, vault_path): return None

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server_get_note_by_path(vault_path="clients/digithings/nope")
    assert exc.value.status_code == 404


@pytest.mark.unit
def test_get_note_by_path_enforces_the_caller_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    # A caller scoped to digithings must not read the OCC corpus.
    class _FakeD1:
        def get_note(self, vault_path):
            raise AssertionError("must not reach the store")

    monkeypatch.setattr(server, "_open_d1_store", lambda prefix: _FakeD1())
    with pytest.raises(HTTPException) as exc:
        server_get_note_by_path(
            vault_path="clients/online-compliance-center/x",
            path_prefix="clients/digithings",
        )
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dv/test_server.py -k "d1 or by_path" -v`
Expected: FAIL — `AttributeError: module 'digivault.server' has no attribute '_open_d1_store'`

- [ ] **Step 3: Add `_open_d1_store` and the precedence branch**

Add near `_open_supabase_store` (`server.py:138`):

```python
def _open_d1_store(path_prefix: str | None) -> D1Store:
    """Build a D1Store for the corpus owning ``path_prefix``.

    Each corpus is a separate database, so tenant isolation is structural: a caller
    scoped to one prefix cannot address another corpus's notes at all.
    """
    account_id = (os.environ.get("D1_ACCOUNT_ID") or "").strip()
    api_token = (os.environ.get("D1_API_TOKEN") or "").strip()
    raw_map = (os.environ.get("D1_DATABASE_MAP") or "").strip()
    if not account_id or not api_token or not raw_map:
        raise D1StoreError(
            "D1 not configured: set D1_ACCOUNT_ID, D1_API_TOKEN and D1_DATABASE_MAP."
        )
    try:
        database_map = json.loads(raw_map)
    except ValueError as exc:
        raise D1StoreError("D1_DATABASE_MAP is not valid JSON") from exc
    prefix = normalize_vault_path(path_prefix or "")
    database_id = database_map.get(prefix)
    if not database_id:
        raise D1StoreError(f"no D1 database configured for vault prefix {prefix!r}")
    return D1Store(str(database_id), account_id=account_id, api_token=api_token)


def _d1_configured() -> bool:
    return bool(
        (os.environ.get("D1_ACCOUNT_ID") or "").strip()
        and (os.environ.get("D1_API_TOKEN") or "").strip()
        and (os.environ.get("D1_DATABASE_MAP") or "").strip()
    )
```

Replace the precedence block at `server.py:341`:

```python
        # D1 first: when the remote corpus is configured it is authoritative, and the
        # baked /data/vault seed must not shadow it (the #2239 bug).
        if _d1_configured():
            hits = _open_d1_store(path_prefix).search(query, limit=limit, path_prefix=path_prefix)
        elif (os.environ.get("DIGIVAULT_ROOT") or "").strip():
            hits = search_local_vault(_open_vault(), query, limit=limit, path_prefix=path_prefix)
        else:
            hits = _open_supabase_store().search(query, limit=limit, path_prefix=path_prefix)
        data = {"hits": [h.model_dump(mode="json") for h in hits]}
```

- [ ] **Step 4: Add the by-path route**

```python
class NoteByPathRequest(BaseModel):
    vault_path: str
    path_prefix: str | None = None


@app.post("/v1/notes/by-path", response_model=NoteDetail)
def server_get_note_by_path(vault_path: str, path_prefix: str | None = None) -> NoteDetail:
    """Load one note whole, addressed by ``vault_path``.

    ``path_prefix`` is enforced, not advisory: without it a caller scoped to one client
    could read another client's notes by guessing a path.
    """
    path = normalize_vault_path(vault_path)
    prefix = normalize_vault_path(path_prefix or "")
    if prefix and path != prefix and not path.startswith(prefix + "/"):
        raise HTTPException(status_code=403, detail="vault_path is outside the caller's prefix")
    note = _open_d1_store(prefix or None).get_note(path)
    if note is None:
        raise HTTPException(status_code=404, detail=f"note not found: {path}")
    return note
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/dv/test_server.py -v`
Expected: PASS (all pre-existing server tests still green)

- [ ] **Step 6: Commit**

```bash
ruff check digivault tests && ruff format --check digivault tests
git add digivault/src/digivault/server.py tests/dv/test_server.py
git commit -m "feat(digivault): serve D1 ahead of the seed vault, add enforced by-path note fetch"
```

---

### Task 3: the `digivault_get_note` tool

**Files:**
- Modify: `digivault/src/digivault/orchestrator_tools.py`
- Test: `tests/dv/test_orchestrator_tools.py`

**Interfaces:**
- Produces: orchestrator tool `digivault_get_note`, argument `vault_path: str` (required); returns `{vault_path, title, body_markdown, frontmatter, segment_label}`.

> **Pre-flight correction (2026-08-12).** An earlier draft of this task invented a
> `TOOLS` list and a `ToolSpec` class. **Neither exists.** The real module uses
> `TOOL_VAULT_*` string constants, an `ORCHESTRATOR_TOOL_NAMES: frozenset[str]`, a
> private `_fn(name, description, params) -> OpenAIToolDict` helper, and
> `build_orchestrator_tool_manifest() -> list[OpenAIToolDict]`. The code below matches
> the real module. Verify against `digivault/src/digivault/orchestrator_tools.py:29-55`
> before writing.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.unit
def test_get_note_tool_is_in_the_manifest_with_a_vault_path_argument() -> None:
    from digivault.orchestrator_tools import (
        ORCHESTRATOR_TOOL_NAMES,
        TOOL_VAULT_GET_NOTE,
        build_orchestrator_tool_manifest,
    )

    assert TOOL_VAULT_GET_NOTE in ORCHESTRATOR_TOOL_NAMES
    tool = next(
        t
        for t in build_orchestrator_tool_manifest()
        if t["function"]["name"] == TOOL_VAULT_GET_NOTE
    )
    params = tool["function"]["parameters"]
    assert "vault_path" in params["properties"]
    assert params["required"] == ["vault_path"]
    # The description must tell the model where a vault_path comes from, or it will
    # invent one instead of reading it off a digisearch hit.
    assert "digisearch" in tool["function"]["description"].lower()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dv/test_orchestrator_tools.py -k get_note -v`
Expected: FAIL — `ImportError: cannot import name 'TOOL_VAULT_GET_NOTE'`

- [ ] **Step 3: Add the constant, register it, and add the manifest entry**

Add the constant beside the others (after `TOOL_VAULT_SEARCH_NOTES`, line 33):

```python
TOOL_VAULT_GET_NOTE = "digivault_get_note"
```

Add it to the `ORCHESTRATOR_TOOL_NAMES` frozenset, then append this `_fn(...)` entry to
the list returned by `build_orchestrator_tool_manifest()`:

```python
        _fn(
            TOOL_VAULT_GET_NOTE,
            "Load one vault note in full by its vault_path. Use this after digisearch "
            "returns a promising chunk: take the vault_path from that hit's metadata "
            "and call this to read the whole note — a complete PDF page or document "
            "section — instead of reasoning from the excerpt. Do not guess a "
            "vault_path; only use one returned by a search.",
            {
                "type": "object",
                "properties": {
                    "vault_path": {
                        "type": "string",
                        "description": (
                            "Canonical note path from a digisearch hit, e.g. "
                            "clients/digithings/security__p003. No .md suffix."
                        ),
                    }
                },
                "required": ["vault_path"],
            },
        ),
```

Also update the `TOOL_VAULT_SEARCH_NOTES` description: it currently claims the search
"uses Supabase FTS when CORE_SUPABASE_URL / CORE_SUPABASE_ANON_KEY are configured",
which is no longer the production path. State D1 first, then Supabase, then the local
filesystem vault — matching the precedence from Task 2.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/dv/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digivault/src/digivault/orchestrator_tools.py tests/dv/test_orchestrator_tools.py
git commit -m "feat(digivault): expose digivault_get_note for locate-then-load"
```

---

### Task 4: `scripts/d1_sync.py` — schema bootstrap and publish

**Files:**
- Create: `scripts/d1_sync.py`
- Test: `tests/scripts/test_d1_sync.py`

**Interfaces:**
- Consumes: `D1Store`, `normalize_vault_path`, `d1_schema.sql` (Task 1).
- Produces: CLI `python scripts/d1_sync.py --prefix <p> --database <id> [--init] [--from-supabase] [--vault <dir>] [--dry-run]`;
  `chunk_statements(rows, *, params_per_row, max_params=100) -> Iterator[list]`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.unit
def test_batches_respect_the_100_bound_parameter_cap() -> None:
    from scripts.d1_sync import chunk_statements

    rows = [object()] * 50
    batches = list(chunk_statements(rows, params_per_row=11))
    # 11 params/row -> at most 9 rows per statement (99 <= 100).
    assert all(len(b) <= 9 for b in batches)
    assert sum(len(b) for b in batches) == 50


@pytest.mark.unit
def test_upsert_sql_uses_insert_or_replace_and_rebuilds_the_fts_index() -> None:
    from scripts.d1_sync import UPSERT_PREFIX, REBUILD_FTS_SQL

    assert UPSERT_PREFIX.startswith("INSERT OR REPLACE INTO notes")
    # External-content FTS5 does not self-populate; 'rebuild' is the canonical refresh.
    assert REBUILD_FTS_SQL == "INSERT INTO notes_fts(notes_fts) VALUES('rebuild')"


@pytest.mark.unit
def test_publish_normalises_vault_paths_and_extracts_segment_columns() -> None:
    from scripts.d1_sync import row_params

    params = row_params(
        vault_path="clients/x/doc__p013.md",
        title="Page 13",
        frontmatter={"type": "page", "summary": "s", "parent_doc": "doc",
                     "segment_index": 13, "tags": ["a"]},
        body="body text",
    )
    assert params[0] == "clients/x/doc__p013"     # .md stripped
    assert params[8] == "doc"                     # parent_doc column
    assert params[9] == 13                        # segment_index column
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scripts/test_d1_sync.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.d1_sync'`

- [ ] **Step 3: Write `scripts/d1_sync.py`**

```python
"""Publish a digivault corpus into a Cloudflare D1 database.

Reads notes from an onboard vault directory (the normal path) or, with
``--from-supabase``, from ``architecture_notes`` for the one-time backfill. Writes are
batched under D1's 100-bound-parameter cap. Run by an operator or CI, never in the
container — production only reads.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

from digivault.d1_store import D1Store, normalize_vault_path

#: notes table column count — keep in step with digivault/src/digivault/d1_schema.sql
PARAMS_PER_ROW = 11

UPSERT_PREFIX = (
    "INSERT OR REPLACE INTO notes "
    "(vault_path, title, note_type, summary, body, frontmatter, tags, wikilinks, "
    "parent_doc, segment_index, updated_at) VALUES "
)

REBUILD_FTS_SQL = "INSERT INTO notes_fts(notes_fts) VALUES('rebuild')"


def chunk_statements(
    rows: Sequence[Any], *, params_per_row: int, max_params: int = 100
) -> Iterator[list[Any]]:
    """Split rows so no statement exceeds D1's bound-parameter cap."""
    if params_per_row <= 0:
        raise ValueError(f"params_per_row must be positive, got {params_per_row}")
    per_batch = max(1, max_params // params_per_row)
    for start in range(0, len(rows), per_batch):
        yield list(rows[start : start + per_batch])


def row_params(
    *, vault_path: str, title: str, frontmatter: dict[str, Any], body: str
) -> list[Any]:
    """Flatten one note into positional params matching UPSERT_PREFIX's column order."""
    segment_index = frontmatter.get("segment_index")
    return [
        normalize_vault_path(vault_path),
        title or str(frontmatter.get("title") or ""),
        str(frontmatter.get("type") or ""),
        str(frontmatter.get("summary") or ""),
        body or "",
        json.dumps(frontmatter, sort_keys=True),
        json.dumps(list(frontmatter.get("tags") or [])),
        json.dumps(list(frontmatter.get("wikilinks") or [])),
        (str(frontmatter["parent_doc"]) if frontmatter.get("parent_doc") else None),
        (int(segment_index) if isinstance(segment_index, int) else None),
        str(frontmatter.get("ingested_at") or ""),
    ]


def _read_vault(vault_root: Path, prefix: str) -> list[list[Any]]:
    from digivault import frontmatter as fm

    out: list[list[Any]] = []
    for path in sorted(vault_root.rglob("*.md")):
        rel = normalize_vault_path(str(path.relative_to(vault_root)))
        if prefix and rel != prefix and not rel.startswith(prefix + "/"):
            continue
        meta, body = fm.parse_frontmatter(path.read_text(encoding="utf-8"))
        out.append(row_params(
            vault_path=rel, title=str(meta.get("title") or ""), frontmatter=meta, body=body
        ))
    return out


def _read_supabase(prefix: str) -> list[list[Any]]:
    from digivault.supabase_store import SupabaseStore

    notes = SupabaseStore.from_env().list_notes(path_prefix=prefix)
    return [
        row_params(
            vault_path=n.vault_path,
            title=n.title or "",
            frontmatter=dict(n.frontmatter),
            body=n.body_markdown,
        )
        for n in notes
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", required=True, help="vault_path prefix, e.g. clients/digithings")
    parser.add_argument(
        "--database",
        required=True,
        help=(
            "D1 database id for this corpus. MUST be the id mapped to --prefix in "
            "D1_DATABASE_MAP (see frontend/digithings-stack-cloudflare/wrangler.toml); "
            "a mismatch means digivault reads a different corpus than this wrote."
        ),
    )
    parser.add_argument("--vault", help="onboard vault root to publish from")
    parser.add_argument(
        "--from-supabase",
        action="store_true",
        help="one-time backfill: read architecture_notes instead of a vault directory",
    )
    parser.add_argument("--init", action="store_true", help="apply d1_schema.sql first")
    parser.add_argument("--dry-run", action="store_true", help="read and count; write nothing")
    args = parser.parse_args(argv)

    if not args.from_supabase and not args.vault:
        parser.error("one of --vault or --from-supabase is required")

    store = D1Store(
        args.database,
        account_id=os.environ.get("D1_ACCOUNT_ID", ""),
        api_token=os.environ.get("D1_API_TOKEN", ""),
    )
    prefix = normalize_vault_path(args.prefix)

    if args.init and not args.dry_run:
        schema = (
            Path(__file__).resolve().parent.parent
            / "digivault/src/digivault/d1_schema.sql"
        ).read_text(encoding="utf-8")
        for statement in [s.strip() for s in schema.split(";") if s.strip()]:
            store.query(statement, [], operation="init")
        print("schema applied", file=sys.stderr)

    rows = _read_supabase(prefix) if args.from_supabase else _read_vault(Path(args.vault), prefix)
    print(f"{len(rows)} notes under {prefix!r}", file=sys.stderr)
    if args.dry_run:
        print(json.dumps({"prefix": prefix, "notes": len(rows), "written": 0}))
        return 0

    written = 0
    for batch in chunk_statements(rows, params_per_row=PARAMS_PER_ROW):
        placeholders = ", ".join(["(" + ", ".join(["?"] * PARAMS_PER_ROW) + ")"] * len(batch))
        params = [value for row in batch for value in row]
        store.query(UPSERT_PREFIX + placeholders, params, operation="upsert")
        written += len(batch)
        print(f"  {written}/{len(rows)}", file=sys.stderr)

    store.query(REBUILD_FTS_SQL, [], operation="rebuild_fts")
    print(json.dumps({"prefix": prefix, "notes": len(rows), "written": written}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/scripts/test_d1_sync.py -v`
Expected: PASS, 3 tests

- [ ] **Step 5: Commit**

```bash
ruff check scripts tests && ruff format --check scripts tests
git add scripts/d1_sync.py tests/scripts/test_d1_sync.py
git commit -m "feat(scripts): d1_sync publishes a corpus into a D1 database"
```

---

### Task 5: repoint `vectorize_sync.py` from Supabase to D1

**Files:**
- Modify: `scripts/vectorize_sync.py:284-353`
- Test: `tests/scripts/test_vectorize_sync.py`

**Interfaces:**
- Consumes: `D1Store.list_notes` (Task 1), which returns the same `list[NoteRow]` that
  `SupabaseStore.list_notes` returned — so only the reader construction changes.
- Produces: `vectorize_sync` CLI gains `--database <d1-id>`.

- [ ] **Step 1: Update the test that pins the reader**

```python
@pytest.mark.unit
def test_reads_notes_from_d1_not_supabase(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict = {}

    class _FakeD1:
        def __init__(self, database_id, **kw): seen["database_id"] = database_id
        def list_notes(self, *, path_prefix): 
            seen["prefix"] = path_prefix
            return []

    monkeypatch.setattr("digivault.d1_store.D1Store", _FakeD1)
    monkeypatch.setattr(
        "digivault.supabase_store.SupabaseStore.from_env",
        lambda: (_ for _ in ()).throw(AssertionError("Supabase must not be read")),
    )
    rc = vectorize_sync.main(
        ["--prefix", "clients/x", "--index", "x_docs", "--database", "db-9", "--dry-run"]
    )
    assert rc == 0
    assert seen == {"database_id": "db-9", "prefix": "clients/x"}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/scripts/test_vectorize_sync.py -k d1 -v`
Expected: FAIL — `error: unrecognized arguments: --database`

- [ ] **Step 3: Add the flag and swap the reader**

Add to the argparse block (after `--index`):

```python
    parser.add_argument(
        "--database",
        required=True,
        help=(
            "D1 database id holding this corpus' notes — the same id d1_sync.py wrote "
            "to for --prefix. Vectors are derived from D1, so a mismatch silently "
            "embeds a different corpus than digivault serves."
        ),
    )
```

Replace the Supabase read (`scripts/vectorize_sync.py:309-317`):

```python
    import os

    from digisearch.embedding.providers.minilm import MINILM_MODEL_ID, MiniLMEmbedder
    from digisearch.indexes.backends.vectorize import DEFAULT_BATCH_SIZE, VectorizeBackend
    from digisearch.ingestion.chunkers.segment_aware import SegmentAwareChunker
    from digivault.d1_store import D1Store

    notes = D1Store(
        args.database,
        account_id=os.environ.get("D1_ACCOUNT_ID", ""),
        api_token=os.environ.get("D1_API_TOKEN", ""),
    ).list_notes(path_prefix=args.prefix)
    print(f"{len(notes)} notes under {args.prefix!r}", file=sys.stderr)
```

- [ ] **Step 4: Update the module docstring**

Change every "Supabase" mention in `scripts/vectorize_sync.py`'s docstring and in the
`--dry-run` help text to "D1". The `--dry-run` help currently reads *"Read notes from
Supabase, chunk, and report the vector count"*.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/scripts/test_vectorize_sync.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add scripts/vectorize_sync.py tests/scripts/test_vectorize_sync.py
git commit -m "refactor(scripts): vectorize_sync reads notes from D1, not Supabase"
```

---

### Task 6: container and CI wiring

**Files:**
- Modify: `frontend/digithings-stack-cloudflare/src/index.ts:41-72` and `:112-139`
- Modify: `frontend/digithings-stack-cloudflare/container/entrypoint.sh`
- Modify: `.github/workflows/docs-onboard-digithings.yml:144-187`
- Test: `frontend/digithings-stack-cloudflare/src/ports.test.ts`

**Interfaces:**
- Consumes: the env contract from Task 2 (`D1_ACCOUNT_ID`, `D1_API_TOKEN`, `D1_DATABASE_MAP`).

- [ ] **Step 1: Add the three vars to `envVars`**

In `src/index.ts`, immediately after the `VECTORIZE_API_TOKEN` line (`:61`):

```ts
    D1_ACCOUNT_ID: env.D1_ACCOUNT_ID ?? "",
    D1_API_TOKEN: env.D1_API_TOKEN ?? "",
    D1_DATABASE_MAP: env.D1_DATABASE_MAP ?? "",
```

- [ ] **Step 2: Add the same three to the `Env` interface**

After `VECTORIZE_API_TOKEN?: string;` (`:130`):

```ts
  D1_ACCOUNT_ID?: string;
  D1_API_TOKEN?: string;
  D1_DATABASE_MAP?: string;
```

**These two lists are hand-kept in sync — a var in `envVars` but not `Env` fails
typecheck; a var in `Env` but not `envVars` silently never reaches the container.**
That second failure is exactly the trap #2239 blocker 3 describes.

- [ ] **Step 3: Export them from `entrypoint.sh`**

Alongside the existing `VECTORIZE_*` exports. Do **not** touch the `DATA_VAULT` /
`DIGIVAULT_ROOT` lines (`entrypoint.sh:10-13`) or the seed loop (`:105-129`) — D1 is
selected by presence, so the filesystem vault stays as the offline fallback:

```sh
export D1_ACCOUNT_ID="${D1_ACCOUNT_ID:-}"
export D1_API_TOKEN="${D1_API_TOKEN:-}"
export D1_DATABASE_MAP="${D1_DATABASE_MAP:-}"
```

- [ ] **Step 4: Repoint the onboarding workflow**

In `.github/workflows/docs-onboard-digithings.yml`, replace the "Require CORE_SUPABASE_*
secrets" step with a D1 guard, and replace the "Sync onboard vault →
public.architecture_notes" step:

```yaml
      - name: Require D1 secrets
        env:
          D1_ACCOUNT_ID: ${{ secrets.D1_ACCOUNT_ID }}
          D1_API_TOKEN: ${{ secrets.D1_API_TOKEN }}
        run: |
          missing=0
          if [ -z "$D1_ACCOUNT_ID" ]; then
            echo "::error::D1_ACCOUNT_ID is not set in the production environment"
            missing=1
          fi
          if [ -z "$D1_API_TOKEN" ]; then
            echo "::error::D1_API_TOKEN is not set in the production environment"
            missing=1
          fi
          exit "$missing"

      - name: Publish onboard vault → D1
        env:
          D1_ACCOUNT_ID: ${{ secrets.D1_ACCOUNT_ID }}
          D1_API_TOKEN: ${{ secrets.D1_API_TOKEN }}
        run: |
          uv run --frozen --no-sync python scripts/d1_sync.py \
            --prefix clients/digithings \
            --database "${{ secrets.D1_DATABASE_DIGITHINGS }}" \
            --vault "$ONBOARD_VAULT"
```

- [ ] **Step 5: Typecheck and test the Worker**

Run: `cd frontend/digithings-stack-cloudflare && npm run typecheck && npm test`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/digithings-stack-cloudflare/src/index.ts frontend/digithings-stack-cloudflare/container/entrypoint.sh .github/workflows/docs-onboard-digithings.yml
git commit -m "feat(stack): forward D1 config to the container and publish onboarding to D1"
```

---

### Task 7: cutover (operator, not code)

**Files:** none — this is a runbook, recorded so the steps are reviewable.

- [ ] **Step 1: Create the two databases**

```bash
npx wrangler d1 create digithings_docs
npx wrangler d1 create occ_help
```

Record each returned `database_id`.

- [ ] **Step 2: Apply schema and backfill from Supabase**

`--from-supabase` needs more than the `D1_*` pair below: it reads the *existing*
corpus out of Supabase before it can write it into D1, so it also needs the
`digivault[supabase]` extra installed (`uv pip install -e 'digivault[supabase]'` or
equivalent) **and** `CORE_SUPABASE_URL` plus a key (`CORE_SUPABASE_ANON_KEY` or
`CORE_SUPABASE_SERVICE_KEY`) exported. Without them this now fails fast with a clean
`error: Supabase not configured: ...` and exit 1 — before this task's fix it raised an
unhandled `SupabaseStoreError` traceback, which is what an operator following just the
`D1_*` exports below would have hit first.

```bash
export D1_ACCOUNT_ID=... D1_API_TOKEN=...
export CORE_SUPABASE_URL=... CORE_SUPABASE_SERVICE_KEY=...
uv run python scripts/d1_sync.py --prefix clients/digithings --database <id> --init --from-supabase
uv run python scripts/d1_sync.py --prefix clients/online-compliance-center --database <id> --init --from-supabase
```

Expected: `{"prefix": "clients/digithings", "notes": 1279, "written": 1279}` and
`{"prefix": "clients/online-compliance-center", "notes": 328, "written": 328}`.
**If either count differs from 1279 / 328, stop** — that is the duplication class of bug
#2138, and it must be understood before the index is trusted.

- [ ] **Step 3: Verify a round-trip**

```bash
uv run python -c "
import os
from digivault.d1_store import D1Store
s = D1Store('<id>', account_id=os.environ['D1_ACCOUNT_ID'], api_token=os.environ['D1_API_TOKEN'])
hits = s.search('compliance archive', limit=3, path_prefix='clients/online-compliance-center')
print([(h.vault_path, round(h.rank, 3)) for h in hits])
print(s.get_note(hits[0].vault_path).frontmatter)
"
```

Expected: three `clients/online-compliance-center/...` paths and a frontmatter dict
containing `segment_label` / `page_class`.

- [ ] **Step 4: Re-run the vector sync from D1 and confirm counts are unchanged**

```bash
uv run python scripts/vectorize_sync.py --prefix clients/digithings --index digithings_docs --database <id>
uv run python scripts/vectorize_sync.py --prefix clients/online-compliance-center --index occ_help --database <id>
```

- [ ] **Step 5: Set container secrets and redeploy**

```bash
cd frontend/digithings-stack-cloudflare
val() { grep -E "^$1=" ../../.env | head -1 | cut -d= -f2- | tr -d '"'"'"'; }

printf '%s' "$(val CLOUDFLARE_ACCOUNT_ID)" | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put CLOUDFLARE_ACCOUNT_ID
printf '%s' "$(val CLOUDFLARE_API_TOKEN)"  | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put CLOUDFLARE_API_TOKEN
printf '%s' '{"clients/digithings":"<id>","clients/online-compliance-center":"<id>"}' | env -u CLOUDFLARE_API_TOKEN npx wrangler secret put D1_DATABASE_MAP
env -u CLOUDFLARE_API_TOKEN npx wrangler deploy
```

**The `env -u CLOUDFLARE_API_TOKEN` is load-bearing, not decoration.** That variable
is *also* wrangler's own authentication variable. If it is exported — which sourcing
`.env` does — wrangler abandons your `wrangler login` OAuth session and authenticates
as that token instead. It carries Vectorize and D1 permissions but not Workers, so
every command above fails with `Authentication error [code: 10000]` against
`/workers/scripts/...`, which reads like a broken token but is actually the wrong
identity. Observed live on 2026-08-12. Piping the value on stdin keeps it reaching
wrangler while the environment stays clean. Leave `CLOUDFLARE_ACCOUNT_ID` exported —
wrangler uses it to pick the account, and the fallback lookup needs a
`User -> Memberships` scope this token does not have.

**Do not delete the legacy `VECTORIZE_*` Worker secrets until after this deploy is
verified.** They serve vector search today; the fallback makes every ordering safe
except removing them first.

These are **Worker** secrets — a separate store from GitHub Actions. The
`.github/workflows/docs-onboard-digithings.yml` `apply` job also reads
`D1_ACCOUNT_ID` / `D1_API_TOKEN` / `D1_DATABASE_MAP` from the repo's `production`
**environment secrets**, and must hold the *same* `D1_DATABASE_MAP` value as the
Worker (it derives `--database` from `map["clients/digithings"]`) — one map, so
CI publishing and the container reading can never point at different databases
for the same prefix:

```bash
gh secret set D1_ACCOUNT_ID --env production
gh secret set D1_API_TOKEN --env production
gh secret set D1_DATABASE_MAP --env production   # same JSON map as the Worker secret above
```

- [ ] **Step 6: Confirm the #2239 acceptance criterion**

Ask the OCC chat a question whose answer lives in the corpus. Vault citations must be
`clients/online-compliance-center/...`, **not** `seed-*.md`.

**Part 1 is independently shippable here.** digivault serves the real corpus; the chat
is behaviourally unchanged. If Part 2 is deferred, #2239 still closes.

---

## Part 2 — the chat becomes agentic

### Task 8: delete the prefetch so the tool loop runs

**Files:**
- Modify: `digigraph/src/digigraph/graph/research.py` — delete `:265-284`, `:287-301`, `:304-317`, `:401-429`, `:469-479`; edit the `run_tools` call at `:481-491`
- Modify: `tests/dg/test_research_prefetch.py`

**Interfaces:**
- Consumes: `run_tools(model, messages, tools, execute_tool, *, max_tool_rounds=5, on_tool_step=None, ...)` from `digigraph.llm_client` — **already called today**; only its `tools` argument changes from `[]` to a populated list.

- [ ] **Step 1: Rewrite the tests first**

Delete `test_format_prefetch_context_dict_and_truncate` and
`test_strip_tools_by_name_openai_and_summary` (both test deleted functions). Replace
`test_document_rag_injects_prefetch_and_strips_tools` and
`test_document_rag_empty_tools_still_calls_run_tools` with:

```python
@pytest.mark.unit
def test_document_rag_hands_tools_to_the_model_and_does_not_prefetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = DigiProjectConfig({"agents": {"enabled": ["research"]}})
    state = {"prompt": "How is digichat built?", "session_id": "sess-1", "stored_datasets": {}}
    captured: dict = {}

    def fake_run_tools(*, model, messages, tools, execute_tool, on_tool_step=None, **kw):
        captured["tools"] = tools
        captured["user"] = messages[1]["content"]
        captured["max_tool_rounds"] = kw.get("max_tool_rounds")
        return "answer"

    def exploding_execute(name, args):
        raise AssertionError(f"no retrieval may run before the model asks: {name}")

    with patch.object(research_mod, "run_tools", fake_run_tools), patch(
        "digigraph.orchestration.registry.execute", exploding_execute
    ):
        research_mod.research_node(state, cfg)

    names = [research_mod._tool_name(t) for t in captured["tools"]]
    assert "digisearch" in names
    assert "digivault_search_notes" in names
    assert "digivault_get_note" in names
    # The prefetch used to paste results into the user turn; nothing may do that now.
    assert "already fetched" not in captured["user"]
    assert captured["max_tool_rounds"] == 4
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dg/test_research_prefetch.py -v`
Expected: FAIL — `AssertionError: no retrieval may run before the model asks: digisearch`

- [ ] **Step 3: Delete the prefetch block**

Remove `research.py:403-429` entirely (the `prefetch_names` / `prefetch_blocks` /
`prefetched` locals and the whole `if prefetch_names and str(prompt).strip():` body), and
remove `:469-479` (the "Retrieved context (already fetched …)" injection and the
`_strip_tools_by_name` call). Delete `_format_prefetch_context` (`:265-284`) and
`_strip_tools_by_name` (`:304-317`).

Keep `_tool_definition_name` (`:287-301`) but rename it `_tool_name` and export it — the
new test uses it and it is the only code that understands both the DETAILED dict and
SUMMARY string tool shapes.

- [ ] **Step 4: Pass an explicit round budget**

Replace `research.py:481-491`:

```python
    # The model drives retrieval: it chooses whether to search, writes its own query,
    # and may follow a digisearch hit with digivault_get_note to read the whole note.
    # 4 rounds is enough for locate -> load -> answer with one retry, and bounds the
    # per-turn completion count (this used to be exactly 1).
    content = run_tools(
        model=get_model_for_mode(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        tools=tools_for_llm,
        execute_tool=execute_search,
        max_tool_rounds=4,
        on_tool_step=stream_callback,
    )
```

- [ ] **Step 5: Run the digigraph suite**

Run: `uv run pytest tests/dg/ -v`
Expected: PASS. `tests/dg/test_nodes.py::test_rag_stream_callback_called_for_tool_call_and_result` must still pass untouched — it already exercised this path.

- [ ] **Step 6: Commit**

```bash
ruff check digigraph tests && ruff format --check digigraph tests
git add digigraph/src/digigraph/graph/research.py tests/dg/test_research_prefetch.py
git commit -m "feat(digigraph): let the model drive retrieval — remove the prefetch and tool strip"
```

---

### Task 9: widen the tool allowlists and fix the prompts

**Files:**
- Modify: `infra/digichat-release/config/digiproject.yaml:21-37`
- Modify: `config/dogfood-digiproject.yaml:15-37`
- Modify: `docs/projects/digithings/digiproject.yaml:13-35`
- Modify: `docs/projects/online-compliance-center/digiproject.yaml:14-26`

- [ ] **Step 1: Add the tool to every allowlist**

In each file's `agents.allowed_tools`, add `digivault_get_note` alongside `digisearch`
and `digivault_search_notes`. `infra/digichat-release/config/digiproject.yaml` is the one
**baked into the container image** (`Dockerfile.digithings-stack-cloudflare:59`) — missing
it there means the tool is invisible in production however the others are set.

- [ ] **Step 2: Remove `always_retrieve_tools` from every file**

The key is now dead configuration. Leaving it would imply behaviour that no longer exists.

- [ ] **Step 3: Fix the system prompts**

Delete the line *"Those tools were prefetched — do not ask to re-run them"* from
`config/dogfood-digiproject.yaml:42-43` and its twin in
`infra/digichat-release/config/digiproject.yaml`. Replace with:

```yaml
    - "Search before answering questions about the docs. Use digisearch to find
       relevant passages, then digivault_get_note with a hit's vault_path when you
       need the full page rather than the excerpt. If a question needs no
       documentation, answer directly without searching."
```

- [ ] **Step 4: Verify config parses**

Run: `uv run pytest tests/dg/ -k project_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add infra/digichat-release/config/digiproject.yaml config/dogfood-digiproject.yaml docs/projects/digithings/digiproject.yaml docs/projects/online-compliance-center/digiproject.yaml
git commit -m "feat(config): allow digivault_get_note, drop always_retrieve_tools and its prompt"
```

---

### Task 10: make every tool call visible in the activity UI

**Files:**
- Modify: `digigraph/src/digigraph/graph/research.py:369-380` (the `execute_search` closure)
- Test: `tests/dg/test_nodes.py`

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.unit
def test_a_zero_hit_search_still_emits_a_trace() -> None:
    """A search that finds nothing must be visible, not silent.

    Today only rag_sources produces a span, so 'searched and found nothing' and
    'never searched' look identical in the UI — which is exactly the confusion this
    change is meant to remove.
    """
    events: list[tuple[str, object]] = []
    # ... drive research_node with a tool call returning {"results": [], "rag_sources": []}
    assert ("tool_result", {"name": "digisearch", "hit_count": 0, "query": "jwt"}) in events
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/dg/test_nodes.py -k zero_hit -v`
Expected: FAIL

- [ ] **Step 3: Include hit count and query in the tool_result payload**

In `execute_search`, after `execute(name, args, context)` returns, attach the two fields
the digichat activity mapper already has slots for:

```python
        if isinstance(result, dict):
            result.setdefault("hit_count", len(result.get("rag_sources") or []))
            query_arg = args.get("query") or args.get("vault_path")
            if query_arg:
                result.setdefault("query", str(query_arg))
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/dg/ -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digigraph/src/digigraph/graph/research.py tests/dg/test_nodes.py
git commit -m "feat(digigraph): surface hit count and query on every tool result"
```

---

### Task 11: documentation and issue corrections

**Files:**
- Modify: `digigraph/ARCHITECTURE.md:397`
- Modify: `digivault/ARCHITECTURE.md`
- Modify: `docs/superpowers/specs/2026-08-11-vectorize-remote-index-design.md`

- [ ] **Step 1: Rewrite `digigraph/ARCHITECTURE.md:397`**

It currently documents the prefetch-and-strip and states the model receives no tools.
Replace with the tool-loop description: tools are passed to the model, `run_tools` drives
up to 4 rounds, and retrieval is model-initiated.

- [ ] **Step 2: Document the D1 backend in `digivault/ARCHITECTURE.md`**

Record the precedence (D1 → Supabase → filesystem), the two-database tenant split, the
`vault_path` normalisation rule, and that `POST /v1/notes/by-path` enforces `path_prefix`
rather than treating it as advisory.

- [ ] **Step 3: Correct the superseded claim in the Vectorize spec**

`docs/superpowers/specs/2026-08-11-vectorize-remote-index-design.md` says keyword search
"continues to read Supabase" — true when written, now false. Point it at the new spec.
(This is #2239's fifth acceptance criterion.)

- [ ] **Step 4: Correct issue #2240**

```bash
gh issue comment 2240 --body "Correction: this issue states \`DIGI_ALLOWED_TOOLS\` decides the production allowlist. It does not — the mounted project YAML outranks it. The conclusion (an empty tool list reaches the model) is correct; the mechanism named is wrong."
```

- [ ] **Step 5: Run doc checks and commit**

```bash
make doc-check
git add digigraph/ARCHITECTURE.md digivault/ARCHITECTURE.md docs/superpowers/specs/2026-08-11-vectorize-remote-index-design.md
git commit -m "docs: record the D1 backend and the model-driven retrieval loop"
```

---

## Self-review

**Spec coverage.** Every spec section maps to a task: D1 rationale and limits → Task 1;
two databases and tenant isolation → Tasks 1–2; schema → Task 1 (widened, flagged above);
backend selection by presence → Task 2; `vault_path` normalisation → Task 1;
ingest and the `vectorize_sync` repoint → Tasks 4–5; container wiring → Task 6; cutover →
Task 7; prefetch deletion, tool surface, round budget, activity UI, tests → Tasks 8–10;
docs and the #2240 correction → Task 11.

**Two gaps found while reviewing, and closed.** (1) The spec's six-column schema could not
produce a `VaultSearchHit`, which needs `note_type`, `summary`, `tags`, `wikilinks` — the
table now carries them, recorded as a deliberate deviation. (2) The spec never said how a
raw user question becomes a valid FTS5 expression; `what is "page 13"?` is a syntax error,
not a search, so `build_fts_match` and its test were added.

**Deliberately not covered:** Profile A (no digisearch — spec declares it out of scope);
a whole-document `get_document` tool; removing `SupabaseStore`; migrating the 29 legacy
root notes.

**Risks carried into execution:** latency and cost of up to 4 completions per turn where
there is now 1 (measure at Task 8); free-tier model tool-calling reliability; the
`orchestrator_invoke` 10 req/min cap, which a locate-then-load loop can hit inside one
turn.
