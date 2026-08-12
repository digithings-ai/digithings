"""Unit tests for the D1-backed digivault store.

Most tests inject a canned/recording transport (no network). A handful of tests below
run the *real* SQL strings against a real in-memory SQLite/FTS5 connection (also no
network — SQLite is in-process) via ``_d1_sqlite_post``, because the bugs they guard
(implicit-AND FTS5 matching, unescaped LIKE wildcards) are properties of the SQL text
itself and a canned-fixture test would keep passing even if the SQL regressed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest
from digivault.d1_errors import D1StoreError
from digivault.d1_store import MAX_LIST_PAGES, D1Store, build_fts_match, normalize_vault_path
from digivault.models import NoteRow

from digivault import d1_store as d1_store_module

_SCHEMA_SQL = Path(d1_store_module.__file__).with_name("d1_schema.sql").read_text()


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


def _sqlite_conn_with_schema() -> sqlite3.Connection:
    """A fresh in-memory D1-schema-equivalent connection (the real ``d1_schema.sql``)."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA_SQL)
    return conn


def _insert_note(conn: sqlite3.Connection, **cols: str) -> None:
    """Insert one row into ``notes`` and rebuild the external-content FTS index.

    ``notes_fts`` is external-content (``content='notes'``), so it is not kept in sync
    by plain DML on ``notes`` — the real D1 sync path presumably rebuilds it after a
    write, and 'rebuild' is the simplest equivalent for a test fixture.
    """
    row = {
        "vault_path": "",
        "title": "",
        "note_type": "",
        "summary": "",
        "body": "",
        "frontmatter": "{}",
        "tags": "[]",
        "wikilinks": "[]",
        **cols,
    }
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    conn.execute(f"INSERT INTO notes({columns}) VALUES ({placeholders})", list(row.values()))
    conn.execute("INSERT INTO notes_fts(notes_fts) VALUES ('rebuild')")
    conn.commit()


def _d1_sqlite_post(conn: sqlite3.Connection):
    """An ``HttpPost`` that runs D1's ``{sql, params}`` request body against a real
    SQLite connection and replies with D1's actual response envelope — so tests using
    this exercise the real SQL text (FTS5 MATCH syntax, LIKE ESCAPE semantics), not a
    fixture that would still pass if the SQL itself regressed.
    """

    def _post(url: str, headers: dict[str, str], body: bytes, content_type: str) -> tuple[int, str]:
        payload = json.loads(body)
        cursor = conn.execute(payload["sql"], payload["params"])
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        return 200, json.dumps({"success": True, "errors": [], "result": [{"results": rows}]})

    return _post


@pytest.mark.unit
def test_normalize_strips_exactly_one_md_suffix() -> None:
    assert normalize_vault_path("clients/x/page.md") == "clients/x/page"
    assert normalize_vault_path("clients/x/page") == "clients/x/page"
    assert normalize_vault_path("clients/x/page.md.md") == "clients/x/page.md"
    assert normalize_vault_path("  /clients/x/page.md  ") == "clients/x/page"


@pytest.mark.unit
def test_build_fts_match_quotes_terms_so_punctuation_cannot_break_syntax() -> None:
    # Bare FTS5 MATCH treats " ( * : - as syntax; a raw user question is not valid FTS5.
    # Terms are OR-joined (not FTS5's implicit-AND space join) so a real question full
    # of stopwords doesn't require every one of them to appear in a note — see
    # test_search_or_join_finds_natural_language_questions_missing_some_terms below.
    assert (
        build_fts_match('what is "page 13" (OCC)?') == '"what" OR "is" OR "page" OR "13" OR "OCC"'
    )
    assert build_fts_match("   ") == ""


@pytest.mark.unit
def test_build_fts_match_handles_unicode_terms() -> None:
    # The old [A-Za-z0-9_]+ regex shredded non-ASCII: 'café Müller' matched 0 usable
    # terms and a Romanian-only query normalized to '' (no HTTP call at all — see
    # test_search_with_a_unicode_only_query_still_issues_a_query below). \w+ is
    # Unicode-aware by default, so accented Latin, Romanian diacritics, and CJK all
    # extract as terms.
    assert build_fts_match("café Müller") == '"café" OR "Müller"'
    assert build_fts_match("ș ț ă") == '"ș" OR "ț" OR "ă"'
    assert build_fts_match("中文搜索") == '"中文搜索"'


@pytest.mark.unit
def test_search_posts_to_the_query_endpoint_with_bound_params() -> None:
    store, post = _store(
        [
            _ok(
                [
                    {
                        "vault_path": "clients/x/a",
                        "title": "A",
                        "note_type": "page",
                        "summary": "s",
                        "body": "hello",
                        "tags": "[]",
                        "wikilinks": "[]",
                        "rank": -1.5,
                    }
                ]
            )
        ]
    )
    hits = store.search("hello world", limit=3, path_prefix="clients/x")

    url, headers, body, content_type = post.calls[0]
    assert url == ("https://api.cloudflare.com/client/v4/accounts/acct-1/d1/database/db-123/query")
    assert headers == {"Authorization": "Bearer tok"}
    assert content_type == "application/json"
    payload = json.loads(body)
    assert "notes_fts MATCH ?" in payload["sql"]
    assert payload["params"] == ['"hello" OR "world"', "clients/x", "clients/x", "clients/x/%", 3]
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

    store2, _ = _store(
        [
            _ok(
                [
                    {
                        "vault_path": "clients/x/a",
                        "title": "A",
                        "note_type": "page",
                        "summary": "s",
                        "body": "# hi",
                        "frontmatter": '{"page_class":"pdf_page"}',
                        "tags": '["t"]',
                        "wikilinks": "[]",
                        "parent_doc": "doc-1",
                        "segment_index": 13,
                    }
                ]
            )
        ]
    )
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


@pytest.mark.unit
def test_list_notes_parses_json_frontmatter_and_paginates() -> None:
    # `frontmatter` comes back from D1 as a JSON *string* (TEXT column) — NoteRow.frontmatter
    # is typed `dict`, and pydantic v2 does not auto-parse a string into a dict, so this
    # would raise a ValidationError if the store handed the raw row straight to NoteRow.
    page1 = [
        {
            "vault_path": f"clients/x/n{i}",
            "title": f"n{i}",
            "frontmatter": '{"k": "v"}',
            "body_markdown": "body",
        }
        for i in range(2)
    ]
    store, post = _store([_ok(page1), _ok([])])

    out = store.list_notes(path_prefix="clients/x", page_size=2)

    assert len(out) == 2
    assert all(isinstance(r, NoteRow) for r in out)
    assert out[0].frontmatter == {"k": "v"}
    assert len(post.calls) == 2  # second (empty) page fetched to detect end-of-pagination

    first_payload = json.loads(post.calls[0][2])
    assert first_payload["params"] == ["clients/x", "clients/x", "clients/x/%", 2, 0]
    second_payload = json.loads(post.calls[1][2])
    assert second_payload["params"] == ["clients/x", "clients/x", "clients/x/%", 2, 2]


@pytest.mark.unit
def test_list_notes_rejects_non_positive_page_size() -> None:
    store, post = _store([])
    with pytest.raises(ValueError, match="0"):
        store.list_notes(page_size=0)
    assert post.calls == []


# --- Regression: FTS5 implicit-AND made real questions return zero rows -----------


@pytest.mark.unit
def test_search_or_join_finds_natural_language_questions_missing_some_terms() -> None:
    """Verified against real FTS5: with the old space-joined (implicit AND) MATCH,
    'what is on page 13 of the OCC filing?' and 'tell me about the OCC' both returned
    zero rows against a note that plainly discusses page 13 of an OCC filing, because
    AND requires every one of "what"/"is"/"tell"/"me"/"about" to appear in the note
    too. OR-join plus bm25 ranking fixes this without a stopword list.
    """
    conn = _sqlite_conn_with_schema()
    _insert_note(
        conn,
        vault_path="clients/x/a",
        title="OCC filing notes",
        body="This page discusses the OCC filing found on page 13 of the document.",
    )
    store = D1Store("db", account_id="a", api_token="t", http_post=_d1_sqlite_post(conn))
    note_terms = set(
        re.findall(
            r"\w+",
            "OCC filing notes This page discusses the OCC filing "
            "found on page 13 of the document.".lower(),
        )
    )

    for question in (
        "what is on page 13 of the OCC filing?",
        "tell me about the OCC",
    ):
        query_terms = set(re.findall(r"\w+", question.lower()))
        # Confirms this is a real regression case, not a query that happens to match
        # every one of its own terms in the note (which AND-join would also satisfy).
        assert not query_terms <= note_terms, question
        assert [h.vault_path for h in store.search(question)] == ["clients/x/a"], question


# --- Regression: `_`/`%` in path_prefix are unescaped LIKE wildcards ---------------


@pytest.mark.unit
def test_search_path_prefix_escapes_the_like_underscore_wildcard() -> None:
    """Verified against real SQLite: an unescaped `LIKE ?` bound to 'clients/my_corp/%'
    also matches 'clients/myXcorp/...', because `_` is LIKE's single-character
    wildcard. That leaks a sibling corpus across the tenant-isolation boundary.
    """
    conn = _sqlite_conn_with_schema()
    _insert_note(conn, vault_path="clients/my_corp/e", body="needle")
    _insert_note(conn, vault_path="clients/myXcorp/f", body="needle")
    store = D1Store("db", account_id="a", api_token="t", http_post=_d1_sqlite_post(conn))

    hits = store.search("needle", path_prefix="clients/my_corp")
    assert [h.vault_path for h in hits] == ["clients/my_corp/e"]


@pytest.mark.unit
def test_list_notes_path_prefix_escapes_the_like_percent_wildcard() -> None:
    """Verified against real SQLite: an unescaped `LIKE ?` bound to 'clients/100%off/%'
    also matches 'clients/100-OTHERCLIENT-off/...', because `%` is LIKE's
    any-length wildcard.
    """
    conn = _sqlite_conn_with_schema()
    _insert_note(conn, vault_path="clients/100%off/g")
    _insert_note(conn, vault_path="clients/100-OTHERCLIENT-off/h")
    store = D1Store("db", account_id="a", api_token="t", http_post=_d1_sqlite_post(conn))

    out = store.list_notes(path_prefix="clients/100%off")
    assert [n.vault_path for n in out] == ["clients/100%off/g"]


# --- Regression: an empty-normalizing path_prefix must not fail open ---------------


@pytest.mark.unit
@pytest.mark.parametrize("bad_prefix", ["/", ".md", "   ", "///"])
def test_search_raises_on_a_path_prefix_that_normalizes_to_empty(bad_prefix: str) -> None:
    # Fail-open on the tenant-isolation boundary is the wrong default: a prefix that
    # *was given* but normalizes to '' must raise, not silently match every row.
    store, post = _store([])
    with pytest.raises(ValueError, match="empty"):
        store.search("hello", path_prefix=bad_prefix)
    assert post.calls == []


@pytest.mark.unit
@pytest.mark.parametrize("bad_prefix", ["/", ".md", "   ", "///"])
def test_list_notes_raises_on_a_path_prefix_that_normalizes_to_empty(bad_prefix: str) -> None:
    store, post = _store([])
    with pytest.raises(ValueError, match="empty"):
        store.list_notes(path_prefix=bad_prefix)
    assert post.calls == []


@pytest.mark.unit
def test_search_with_path_prefix_none_means_no_filter_and_does_not_raise() -> None:
    # None is the only spelling of "no prefix requested" — it must not raise, and it
    # must actually issue the (unfiltered) query rather than short-circuiting.
    store, post = _store([_ok([])])
    assert store.search("hello", path_prefix=None) == []
    assert len(post.calls) == 1


# --- Regression: raw httpx transport exceptions escaped as non-D1StoreError --------


@pytest.mark.unit
def test_transport_failure_is_wrapped_without_leaking_the_token() -> None:
    """Verified against a dead port: httpx.ConnectError propagated out of search() with
    isinstance(e, D1StoreError) False, so server.py's 503 handler (which only catches
    D1StoreError) would let a connect/timeout/DNS failure surface as an unhandled 500.
    Also verified the escaping exception's exc.request.headers carries the bearer
    token — the fix must build its message from str(exc), never exc.request.
    """
    import httpx

    def _raise_connect_error(
        url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        request = httpx.Request("POST", url, headers=headers)
        raise httpx.ConnectError("Connection refused", request=request)

    store = D1Store("db-123", account_id="acct-1", api_token="tok", http_post=_raise_connect_error)
    with pytest.raises(D1StoreError) as exc:
        store.search("hello")
    assert "tok" not in str(exc.value)
    assert "Bearer" not in str(exc.value)
    assert isinstance(exc.value.__cause__, httpx.ConnectError)


@pytest.mark.unit
def test_a_programming_error_in_http_post_is_not_masked_as_a_transport_failure() -> None:
    # query() must catch httpx.HTTPError specifically, not Exception broadly — a bug
    # inside a custom http_post (e.g. a TypeError) has to propagate as itself.
    def _raise_type_error(
        url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        raise TypeError("boom")

    store = D1Store("db-123", account_id="acct-1", api_token="tok", http_post=_raise_type_error)
    with pytest.raises(TypeError, match="boom"):
        store.search("hello")


# --- Minor: unbounded list_notes pagination burns metered API calls forever -------


@pytest.mark.unit
def test_list_notes_raises_after_max_pages_instead_of_looping_forever() -> None:
    """A backend that always returns a full page (broken prefix filter, server bug)
    would otherwise loop until the process is killed — a reviewer verified this by
    aborting a real run at 2000 requests. page_size=1 with every page full means the
    loop never sees a short page and must hit the cap.
    """
    page_size = 1
    responses = [
        _ok([{"vault_path": f"clients/x/n{i}", "title": "n", "body_markdown": "b"}])
        for i in range(MAX_LIST_PAGES)
    ]
    store, post = _store(responses)
    with pytest.raises(D1StoreError, match=str(MAX_LIST_PAGES)):
        store.list_notes(path_prefix="clients/x", page_size=page_size)
    assert len(post.calls) == MAX_LIST_PAGES


# --- Minor: non-ASCII query terms used to short-circuit with no HTTP call ----------


@pytest.mark.unit
def test_search_with_a_unicode_only_query_still_issues_a_query() -> None:
    # Before the fix, [A-Za-z0-9_]+ matched nothing in '中文搜索', build_fts_match
    # returned '', and search() short-circuited with no HTTP call at all.
    store, post = _store([_ok([])])
    store.search("中文搜索")
    assert len(post.calls) == 1
    payload = json.loads(post.calls[0][2])
    assert payload["params"][0] == '"中文搜索"'


@pytest.mark.unit
def test_search_finds_a_note_via_accented_terms_against_real_fts5() -> None:
    conn = _sqlite_conn_with_schema()
    _insert_note(
        conn,
        vault_path="clients/x/cafe",
        title="café Müller",
        body="notes about café Müller and coffee shops",
    )
    store = D1Store("db", account_id="a", api_token="t", http_post=_d1_sqlite_post(conn))

    hits = store.search("café Müller")
    assert [h.vault_path for h in hits] == ["clients/x/cafe"]
