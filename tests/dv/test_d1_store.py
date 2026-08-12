"""Unit tests for the D1-backed digivault store (no network)."""

from __future__ import annotations

import json

import pytest
from digivault.d1_errors import D1StoreError
from digivault.d1_store import D1Store, build_fts_match, normalize_vault_path
from digivault.models import NoteRow


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
    assert payload["params"] == ['"hello" "world"', "clients/x", "clients/x", "clients/x/%", 3]
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
