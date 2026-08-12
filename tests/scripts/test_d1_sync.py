"""Tests for scripts/d1_sync.py -- the digivault D1 publisher.

Unit tests never hit the network: D1Store takes an injectable ``http_post``, and the
tests below reuse the ``_RecordingPost`` pattern from ``tests/dv/test_d1_store.py`` for
call-count assertions, plus a real in-memory SQLite/FTS5 connection (also no network)
for anything touching SQL semantics -- the FTS rebuild, canonical path storage, and
idempotence tests all run the actual schema and the actual UPSERT_PREFIX/REBUILD_FTS_SQL
text, so a regression in the SQL itself fails the test, not a canned fixture.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any  # score:allow untyped any -- row params are heterogeneous SQL values

import pytest
from digivault.d1_store import D1Store

from scripts import d1_sync
from scripts.d1_sync import (
    MAX_BOUND_PARAMS,
    MAX_ROW_BYTES,
    PARAMS_PER_ROW,
    REBUILD_FTS_SQL,
    UPSERT_CONFLICT_SUFFIX,
    UPSERT_PREFIX,
    _assert_rows_within_byte_cap,
    _ensure_unique_vault_paths,
    _split_to_fit,
    chunk_statements,
    main,
    row_params,
)

pytestmark = pytest.mark.unit


# --- Recording transport (no network) ----------------------------------------------


class _RecordingPost:
    """Injected transport: records calls, replays canned responses."""

    def __init__(self, responses: list[tuple[int, str]] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str], bytes, str]] = []
        self._responses = list(responses or [])

    def __call__(
        self, url: str, headers: dict[str, str], body: bytes, content_type: str
    ) -> tuple[int, str]:
        self.calls.append((url, headers, body, content_type))
        if self._responses:
            return self._responses.pop(0)
        return 200, json.dumps({"success": True, "errors": [], "result": [{"results": []}]})


def _d1_sqlite_post(conn: sqlite3.Connection):
    """An ``HttpPost`` that runs D1's ``{sql, params}`` body against real SQLite.

    Unlike ``tests/dv/test_d1_store.py``'s helper of the same name (SELECT-only),
    this also executes DDL/DML (``CREATE TABLE``, ``INSERT``) -- sqlite3's
    ``cursor.description`` is ``None`` for those, so it must not be indexed blindly.
    """

    def _post(url: str, headers: dict[str, str], body: bytes, content_type: str) -> tuple[int, str]:
        payload = json.loads(body)
        cursor = conn.execute(payload["sql"], payload["params"])
        conn.commit()
        if cursor.description is None:
            rows: list[dict[str, Any]] = []
        else:
            columns = [d[0] for d in cursor.description]
            rows = [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
        return 200, json.dumps({"success": True, "errors": [], "result": [{"results": rows}]})

    return _post


def _store_factory(post: Any):
    """Matches ``D1Store(database_id, *, account_id, api_token)`` -- ``main()``'s call
    shape -- but binds a fixed injected transport, so monkeypatching
    ``d1_sync.D1Store`` with this makes ``main()`` hit no network."""

    def factory(database_id: str, *, account_id: str, api_token: str) -> D1Store:
        return D1Store(database_id, account_id=account_id, api_token=api_token, http_post=post)

    return factory


def _fake_supabase_store_class(rows: list[dict[str, Any]]):
    """Fakes ``SupabaseStore`` as ``_read_supabase`` actually uses it: via
    ``list_raw`` (a select list local to the backfill path, #2239 review Important
    I2), not ``list_notes``/``NoteRow`` -- so the fake's raw dict rows can carry
    ``note_type``/``summary``/``wikilinks`` as top-level keys the way
    ``architecture_notes`` itself does."""

    class _FakeSupabaseStore:
        @classmethod
        def from_env(cls) -> "_FakeSupabaseStore":
            return cls()

        def list_raw(self, *, select: str, path_prefix: str) -> list[dict[str, Any]]:
            return rows

    return _FakeSupabaseStore


def _supabase_row(
    path: str,
    body: str = "body",
    *,
    frontmatter: dict[str, Any] | None = None,
    note_type: str | None = None,
    summary: str | None = None,
    wikilinks: list[str] | None = None,
) -> dict[str, Any]:
    """A raw ``architecture_notes`` row shape -- ``note_type``/``summary``/
    ``wikilinks`` are top-level columns there (``scripts/sync_architecture_vault.py``),
    not frontmatter keys, unlike the on-disk vault's ``_write_note`` shape below."""
    return {
        "vault_path": path,
        "title": path,
        "frontmatter": frontmatter or {},
        "body_markdown": body,
        "note_type": note_type,
        "summary": summary,
        "wikilinks": wikilinks,
    }


def _write_note(vault_dir: Path, rel_path: str, *, frontmatter: dict[str, Any], body: str) -> None:
    import yaml

    file_path = vault_dir / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    fence = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True)
    file_path.write_text(f"---\n{fence}---\n{body}", encoding="utf-8")


# --- Step 1: brief's given tests -----------------------------------------------------


def test_batches_respect_the_100_bound_parameter_cap() -> None:
    rows = [object()] * 50
    batches = list(chunk_statements(rows, params_per_row=11))
    # 11 params/row -> at most 9 rows per statement (99 <= 100).
    assert all(len(b) <= 9 for b in batches)
    assert sum(len(b) for b in batches) == 50


def test_upsert_sql_conflict_updates_in_place_and_rebuilds_the_fts_index() -> None:
    """#2239 review Important I1: this replaces the brief's original assertion that
    UPSERT_PREFIX started with `INSERT OR REPLACE INTO notes` -- REPLACE deletes and
    reinserts the conflicting row on a TEXT PRIMARY KEY, assigning it a *new* rowid,
    which dangles the FTS index's `n.rowid = notes_fts.rowid` join. `ON
    CONFLICT(vault_path) DO UPDATE` updates the row in place instead, preserving its
    rowid (see test_search_survives_a_resync_even_when_the_fts_rebuild_fails for the
    end-to-end proof this fixes)."""
    assert UPSERT_PREFIX.startswith("INSERT INTO notes")
    assert "ON CONFLICT(vault_path) DO UPDATE SET" in UPSERT_CONFLICT_SUFFIX
    # External-content FTS5 does not self-populate; 'rebuild' is the canonical refresh.
    assert REBUILD_FTS_SQL == "INSERT INTO notes_fts(notes_fts) VALUES('rebuild')"


def test_publish_normalises_vault_paths_and_extracts_segment_columns() -> None:
    params = row_params(
        vault_path="clients/x/doc__p013.md",
        title="Page 13",
        frontmatter={
            "type": "page",
            "summary": "s",
            "parent_doc": "doc",
            "segment_index": 13,
            "tags": ["a"],
        },
        body="body text",
    )
    assert params[0] == "clients/x/doc__p013"  # .md stripped
    assert params[8] == "doc"  # parent_doc column
    assert params[9] == 13  # segment_index column


# --- chunk_statements: batch size is derived from column count, not hardcoded ------


def test_chunk_statements_defaults_to_the_max_bound_params_constant() -> None:
    """Re-adding MAX_BOUND_PARAMS as the real default -- not a bare 100 literal --
    so a future change to the constant reaches chunk_statements automatically."""
    assert MAX_BOUND_PARAMS == 100
    rows = list(range(20))
    default_batches = list(chunk_statements(rows, params_per_row=11))
    explicit_batches = list(chunk_statements(rows, params_per_row=11, max_params=100))
    assert default_batches == explicit_batches


def test_chunk_statements_rejects_non_positive_params_per_row() -> None:
    with pytest.raises(ValueError, match="positive"):
        list(chunk_statements([object()], params_per_row=0))


# --- Byte caps: the 100,000-byte statement / 2,000,000-byte row limits -------------


def test_split_to_fit_leaves_a_small_batch_untouched() -> None:
    batch = [
        row_params(vault_path=f"x/{i}", title="t", frontmatter={}, body="hi") for i in range(5)
    ]
    assert list(_split_to_fit(batch)) == [batch]


def test_split_to_fit_breaks_an_oversized_batch_into_pieces_that_fit() -> None:
    big_body = "x" * 20_000
    batch = [
        row_params(vault_path=f"x/{i}", title="t", frontmatter={}, body=big_body) for i in range(9)
    ]
    pieces = list(_split_to_fit(batch, max_bytes=50_000))
    assert sum(len(p) for p in pieces) == 9
    from scripts.d1_sync import _statement_bytes

    assert all(_statement_bytes(p) <= 50_000 for p in pieces)


def test_assert_rows_within_byte_cap_raises_for_an_oversized_row() -> None:
    huge = row_params(
        vault_path="x/huge", title="t", frontmatter={}, body="x" * (MAX_ROW_BYTES + 1)
    )
    with pytest.raises(ValueError, match="x/huge"):
        _assert_rows_within_byte_cap([huge])


def test_assert_rows_within_byte_cap_allows_normal_rows() -> None:
    normal = row_params(vault_path="x/normal", title="t", frontmatter={}, body="short body")
    _assert_rows_within_byte_cap([normal])  # must not raise


def test_assert_rows_within_byte_cap_raises_for_a_row_between_the_statement_and_row_caps() -> None:
    """#2239 review Minor M1: a single row between the 100,000-byte statement cap
    and the 2,000,000-byte row cap used to pass this pre-flight check (well under
    2 MB) and then pass through ``_split_to_fit``'s single-row base case
    unconditionally, reaching D1 as a lone-row statement over the 100 KB statement
    cap -- failing mid-run with any earlier batches already committed. 150,000
    bytes of body text alone, plus the UPSERT SQL text and JSON envelope,
    comfortably clears the 100,000-byte statement cap while staying far under the
    2,000,000-byte row cap.
    """
    outlier = row_params(vault_path="x/outlier", title="t", frontmatter={}, body="x" * 150_000)
    with pytest.raises(ValueError, match="x/outlier"):
        _assert_rows_within_byte_cap([outlier])


def test_assert_rows_within_byte_cap_allows_a_multi_row_batch_under_both_caps() -> None:
    """The pre-flight check is per-row (as it would be sent alone), not per-batch --
    a batch of several small rows that together exceed the statement cap is still
    fine here; ``_split_to_fit`` is what reduces an over-cap multi-row batch."""
    rows = [
        row_params(vault_path=f"x/{i}", title="t", frontmatter={}, body="x" * 5_000)
        for i in range(9)
    ]
    _assert_rows_within_byte_cap(rows)  # must not raise


# --- Duplication guard (#2138 signature) --------------------------------------------


def test_ensure_unique_vault_paths_raises_on_duplicates() -> None:
    rows = [
        row_params(vault_path="clients/x/a", title="A", frontmatter={}, body="1"),
        row_params(vault_path="clients/x/a", title="A again", frontmatter={}, body="2"),
    ]
    with pytest.raises(ValueError, match="clients/x/a"):
        _ensure_unique_vault_paths(rows)


def test_ensure_unique_vault_paths_allows_a_clean_read() -> None:
    rows = [
        row_params(vault_path="clients/x/a", title="A", frontmatter={}, body="1"),
        row_params(vault_path="clients/x/b", title="B", frontmatter={}, body="2"),
    ]
    _ensure_unique_vault_paths(rows)  # must not raise


# --- row_params: defensive frontmatter serialization --------------------------------


def test_row_params_serializes_non_json_frontmatter_values_defensively() -> None:
    """A hand-edited note with an unquoted YAML date parses to datetime.date via
    PyYAML's implicit resolver; plain json.dumps can't serialize that. default=str
    must degrade the field instead of raising and failing the whole batch."""
    import datetime

    params = row_params(
        vault_path="x/a", title="A", frontmatter={"weird": datetime.date(2026, 8, 1)}, body="b"
    )
    frontmatter_json = params[5]
    assert json.loads(frontmatter_json) == {"weird": "2026-08-01"}


# --- _read_vault (via main --vault): canonical paths + prefix scoping --------------


def test_dry_run_reads_vault_and_reports_canonical_counts_with_no_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="hello\n")
    _write_note(tmp_path, "clients/x/b.md", frontmatter={"title": "B"}, body="world\n")
    _write_note(tmp_path, "clients/other/c.md", frontmatter={"title": "C"}, body="skip me\n")

    exit_code = main(
        ["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path), "--dry-run"]
    )

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"prefix": "clients/x", "notes": 2, "written": 0}


def test_dry_run_makes_zero_d1_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """#2239 review lesson from a sibling script: --dry-run must not perform the
    writes it promises to skip. Assert zero calls against the injected transport,
    not just a zero 'written' number in the printed summary."""
    post = _RecordingPost()
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="hello\n")

    exit_code = main(
        [
            "--prefix",
            "clients/x",
            "--database",
            "db",
            "--vault",
            str(tmp_path),
            "--init",
            "--dry-run",
        ]
    )

    assert exit_code == 0
    assert post.calls == []


def test_main_requires_exactly_one_of_vault_or_from_supabase() -> None:
    with pytest.raises(SystemExit):
        main(["--prefix", "clients/x", "--database", "db"])


def test_main_rejects_both_vault_and_from_supabase(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        main(
            [
                "--prefix",
                "clients/x",
                "--database",
                "db",
                "--vault",
                str(tmp_path),
                "--from-supabase",
            ]
        )


def test_main_rejects_a_prefix_that_normalizes_to_empty(tmp_path: Path) -> None:
    exit_code = main(["--prefix", "/", "--database", "db", "--vault", str(tmp_path)])
    assert exit_code == 1


def test_main_requires_credentials_for_a_real_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="hello\n")

    exit_code = main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path)])

    assert exit_code == 1


def test_main_exits_nonzero_when_the_vault_read_finds_zero_notes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """#2239 review Important I3: ``Path.rglob`` on a missing/empty directory yields
    nothing rather than raising, so a typo'd ``--vault`` (or a ``--prefix`` that
    matches nothing) used to be a clean exit 0 reporting `written: 0` -- a green CI
    run that published nothing, with no D1 credentials needed to trigger it. Matches
    the guard ``scripts/sync_onboard_vault.py`` already has for the same mistake on
    its sibling read path.
    """
    monkeypatch.delenv("D1_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("D1_API_TOKEN", raising=False)
    missing = tmp_path / "does-not-exist"

    exit_code = main(["--prefix", "clients/x", "--database", "db", "--vault", str(missing)])

    assert exit_code == 1


def test_main_exits_nonzero_when_the_supabase_read_finds_zero_notes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same guard (#2239 review Important I3), exercised on the ``--from-supabase``
    read path: an empty/wrong-prefix result set must also refuse to publish
    nothing, before any D1 call."""
    post = _RecordingPost()
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    import digivault.supabase_store as supabase_store_module

    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _fake_supabase_store_class([]))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    exit_code = main(["--prefix", "clients/x", "--database", "db", "--from-supabase"])

    assert exit_code == 1
    assert post.calls == []


# --- End-to-end against real SQLite/FTS5: publish, then search must actually work --


def test_publish_then_search_works_end_to_end_after_sync(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Proves search works after a sync, not merely that rows were inserted --
    external-content FTS5 does not self-populate without the rebuild."""
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    _write_note(
        tmp_path,
        "clients/x/occ-archive.md",
        frontmatter={"title": "OCC filing notes"},
        body="This page discusses the compliance archive found on page 13.\n",
    )

    exit_code = main(
        ["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path), "--init"]
    )
    assert exit_code == 0

    store = D1Store("db", account_id="acct", api_token="tok", http_post=post)
    hits = store.search("compliance archive", path_prefix="clients/x")
    assert [h.vault_path for h in hits] == ["clients/x/occ-archive"]  # canonical, no .md

    note = store.get_note("clients/x/occ-archive")
    assert note is not None
    assert note.title == "OCC filing notes"


def test_publish_stores_canonical_vault_paths_without_the_md_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="hello\n")

    main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path), "--init"])

    row = conn.execute("SELECT vault_path FROM notes").fetchone()
    assert row[0] == "clients/x/a"


def test_running_sync_twice_leaves_the_same_row_count_not_doubled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="hello\n")
    _write_note(tmp_path, "clients/x/b.md", frontmatter={"title": "B"}, body="world\n")

    first = main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path), "--init"])
    second = main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path)])

    assert first == 0
    assert second == 0
    count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    assert count == 2  # not 4 -- ON CONFLICT(vault_path) DO UPDATE on the primary key

    store = D1Store("db", account_id="acct", api_token="tok", http_post=post)
    hits = store.search("hello", path_prefix="clients/x")
    assert [h.vault_path for h in hits] == ["clients/x/a"]  # exactly one, not duplicated


def test_d1_notes_readback_surfaces_an_orphaned_row_the_source_no_longer_has(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """#2239 review Minor M3: ``written``/``notes`` are both source-side (rows this
    run read and sent) and were never read back from D1 -- so a note deleted from
    the vault (or renamed by a re-chunk that changes segment slugs, the #2138
    accumulation shape one level down) leaves an orphaned row that neither number
    can ever surface. ``d1_notes`` is a real ``SELECT COUNT(*)`` against the table
    after the rebuild, so a runbook's "halt unless exactly N" check means something.
    This does not delete the orphan -- it only makes the discrepancy visible.
    """
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="alpha\n")
    _write_note(tmp_path, "clients/x/b.md", frontmatter={"title": "B"}, body="beta\n")
    main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path), "--init"])
    capsys.readouterr()  # discard the first run's stdout

    (tmp_path / "clients" / "x" / "b.md").unlink()  # b is gone from the source now
    exit_code = main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path)])

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    # notes/written correctly reflect this run's one-note source; d1_notes reveals
    # the orphaned row from the first run that this run's source no longer has.
    assert out == {"prefix": "clients/x", "notes": 1, "written": 1, "d1_notes": 2}
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 2


# --- --from-supabase: exact counts, parent_doc/segment_index from frontmatter -------


def test_from_supabase_reports_exact_matching_notes_and_written_counts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rows = [_supabase_row(f"clients/x/n{i}") for i in range(5)]
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    import digivault.supabase_store as supabase_store_module

    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _fake_supabase_store_class(rows))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    exit_code = main(["--prefix", "clients/x", "--database", "db", "--from-supabase", "--init"])

    assert exit_code == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"prefix": "clients/x", "notes": 5, "written": 5, "d1_notes": 5}
    assert conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 5


def test_from_supabase_extracts_parent_doc_and_segment_index_from_frontmatter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = [
        _supabase_row(
            "clients/x/doc__p001",
            "page one body",
            frontmatter={"parent_doc": "doc", "segment_index": 1, "type": "page"},
        )
    ]
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    import digivault.supabase_store as supabase_store_module

    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _fake_supabase_store_class(rows))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    main(["--prefix", "clients/x", "--database", "db", "--from-supabase", "--init"])

    row = conn.execute("SELECT parent_doc, segment_index FROM notes").fetchone()
    assert row == ("doc", 1)


def test_from_supabase_carries_top_level_summary_wikilinks_and_note_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#2239 review Important I2: ``architecture_notes`` stores ``summary``,
    ``wikilinks`` and ``note_type`` as top-level table columns
    (``scripts/sync_architecture_vault.py``'s ``build_rows``), not frontmatter keys.
    ``SupabaseStore.list_notes``/``NoteRow`` only carry the four columns on-disk-
    vault-shaped callers need, so reading the backfill through them silently
    dropped all three -- ``wikilinks`` would be ``[]`` for 100% of backfilled notes.
    Frontmatter here deliberately has none of the three keys, so this only passes
    if the top-level columns are the ones actually read.
    """
    row = _supabase_row(
        "clients/x/a",
        "The full body.",
        frontmatter={},
        note_type="reference",
        summary="The tagline summary.",
        wikilinks=["other-note"],
    )
    conn = sqlite3.connect(":memory:")
    post = _d1_sqlite_post(conn)
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    import digivault.supabase_store as supabase_store_module

    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _fake_supabase_store_class([row]))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    main(["--prefix", "clients/x", "--database", "db", "--from-supabase", "--init"])

    stored = conn.execute("SELECT note_type, summary, wikilinks FROM notes").fetchone()
    assert stored[0] == "reference"
    assert stored[1] == "The tagline summary."
    assert json.loads(stored[2]) == ["other-note"]


def test_from_supabase_duplication_is_rejected_before_any_d1_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression shape of #2138: a source read that yields the same vault_path
    twice must abort loudly rather than let the upsert's ON CONFLICT DO UPDATE
    mask it."""
    rows = [_supabase_row("clients/x/a"), _supabase_row("clients/x/a")]
    post = _RecordingPost()
    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(post))
    import digivault.supabase_store as supabase_store_module

    monkeypatch.setattr(supabase_store_module, "SupabaseStore", _fake_supabase_store_class(rows))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    exit_code = main(["--prefix", "clients/x", "--database", "db", "--from-supabase"])

    assert exit_code == 1
    assert post.calls == []


# --- #2239 review, Important I1: INSERT OR REPLACE churns rowids, dangling the FTS index --


def test_search_survives_a_resync_even_when_the_fts_rebuild_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`vault_path` is a TEXT PRIMARY KEY, not a rowid alias, so `INSERT OR REPLACE`
    deletes-and-reinserts on conflict, assigning the row a *new* rowid.
    `D1Store`'s `_SEARCH_SQL` joins `n.rowid = notes_fts.rowid`; if a rebuild then
    fails (a transient D1 500, simulated here) after a re-sync that churned rowids,
    the external-content FTS index is left pointing rowids nowhere and search on
    every previously-indexed note goes dark until some later sync reaches a
    successful rebuild. Fix under test: `ON CONFLICT(vault_path) DO UPDATE`
    preserves the rowid across the re-sync, so the FTS mapping stays valid (worst
    case ranked on stale text) even when the rebuild that would refresh that text
    outright fails.
    """
    conn = sqlite3.connect(":memory:")
    base_post = _d1_sqlite_post(conn)
    rebuild_calls = 0

    def flaky_post(url: str, headers: dict[str, str], body: bytes, content_type: str):
        nonlocal rebuild_calls
        payload = json.loads(body)
        if payload["sql"] == REBUILD_FTS_SQL:
            rebuild_calls += 1
            if rebuild_calls == 2:  # fail only the second sync's rebuild
                return 500, json.dumps({"success": False, "errors": [{"message": "boom"}]})
        return base_post(url, headers, body, content_type)

    monkeypatch.setattr(d1_sync, "D1Store", _store_factory(flaky_post))
    monkeypatch.setenv("D1_ACCOUNT_ID", "acct")
    monkeypatch.setenv("D1_API_TOKEN", "tok")

    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="unicorn\n")
    _write_note(tmp_path, "clients/x/b.md", frontmatter={"title": "B"}, body="zebra\n")
    first = main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path), "--init"])
    assert first == 0

    store = D1Store("db", account_id="acct", api_token="tok", http_post=flaky_post)
    assert [h.vault_path for h in store.search("unicorn", path_prefix="clients/x")] == [
        "clients/x/a"
    ]
    assert [h.vault_path for h in store.search("zebra", path_prefix="clients/x")] == ["clients/x/b"]

    # Edit both notes (still containing their original searched-for term), then
    # re-sync -- this run's rebuild is the one rigged to fail.
    _write_note(tmp_path, "clients/x/a.md", frontmatter={"title": "A"}, body="unicorn v2\n")
    _write_note(tmp_path, "clients/x/b.md", frontmatter={"title": "B"}, body="zebra v2\n")
    second = main(["--prefix", "clients/x", "--database", "db", "--vault", str(tmp_path)])
    assert second == 1  # the rebuild failure is still surfaced as an error

    # Search must still resolve to the correct (still-existing) notes -- not [] --
    # because the rowid the FTS index maps each term to was never churned.
    assert [h.vault_path for h in store.search("unicorn", path_prefix="clients/x")] == [
        "clients/x/a"
    ]
    assert [h.vault_path for h in store.search("zebra", path_prefix="clients/x")] == ["clients/x/b"]


# --- #2239 review, Minor M2: PARAMS_PER_ROW has nothing tying it to the schema -----


def _upsert_prefix_column_count(prefix: str) -> int:
    """Parse the column list out of ``UPSERT_PREFIX``'s ``INSERT ... (a, b, c) VALUES``
    text -- the ground truth ``PARAMS_PER_ROW`` must never silently drift from."""
    match = re.search(r"\((.*?)\)", prefix)
    assert match is not None, f"no column list found in {prefix!r}"
    return len(match.group(1).split(","))


def test_params_per_row_matches_upsert_prefix_columns_and_row_params_length() -> None:
    """PARAMS_PER_ROW is a hand-maintained literal with nothing tying it to the
    schema. Simulating a 12th column while leaving the constant at 11 produced 108
    bound params against D1's 100-param cap -- unguarded by anything, since it only
    failed loudly because the column/value counts also happened to mismatch. Ties
    PARAMS_PER_ROW to two things that must never drift from it: the actual column
    list parsed out of UPSERT_PREFIX's SQL text, and the length of a real
    row_params() call.
    """
    assert _upsert_prefix_column_count(UPSERT_PREFIX) == PARAMS_PER_ROW
    params = row_params(vault_path="x/a", title="A", frontmatter={}, body="b")
    assert len(params) == PARAMS_PER_ROW
