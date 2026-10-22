"""Documents pointer-per-row archive phase (Task 8, #3766).

Documents rows are keyed (workspace_id, document_key, date); the newest date
per key stays live while older payloads move to R2 with an archive_objects
pointer row left behind. The PostgREST and R2 doubles live in
``tests/dq/ops/archive_fakes.py``.
"""

import datetime
import uuid

import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import archive_documents  # noqa: E402

from tests.dq.ops.archive_fakes import FakeArchiveClient, FakeStore  # noqa: E402


def _doc_client() -> FakeArchiveClient:
    """A client double holding the two tables the document phase touches."""
    return FakeArchiveClient(store={"documents": [], "archive_objects": []})


def seed_documents(
    client, workspace="house", key="olympus-thesis", versions=("2026-09-07", "2026-09-08")
):
    for date in versions:
        client.tables["documents"].append(
            {
                "workspace_id": workspace,
                "document_key": key,
                "date": date,
                "payload": {"body": f"{key} {date}"},
            }
        )


def test_archive_documents_keeps_latest_per_key():
    client, store = _doc_client(), FakeStore()
    seed_documents(
        client, workspace="house", key="olympus-thesis", versions=["2026-09-07", "2026-09-08"]
    )
    archive_documents(client, store, workspace="house")
    rows = client.table("documents").select("*").execute().data
    live = [r for r in rows if r["payload"] is not None]
    assert [(r["document_key"], r["date"]) for r in live] == [("olympus-thesis", "2026-09-08")]
    pointers = (
        client.table("archive_objects").select("*").eq("source_table", "documents").execute().data
    )
    assert len(pointers) == 1


def test_archive_documents_key_scan_then_single_row_fetches():
    """The 58MB documents table must never be pulled via one select('*').

    Expected shape (PostgREST 8s cap): one key-only scan first, then one
    full-row select per older version keyed by the full row key.
    """
    client, store = _doc_client(), FakeStore()
    seed_documents(
        client,
        versions=["2026-09-07", "2026-09-08", "2026-09-09"],
    )
    archive_documents(client, store, workspace="house")
    selects = [s for s in client.statements if s["table"] == "documents" and s["op"] == "select"]
    first_cols = ",".join(selects[0]["cols"])
    assert "payload" not in first_cols, selects[0]
    assert set(first_cols.split(",")) == {"workspace_id", "document_key", "date"}
    full = [s for s in selects[1:] if s["cols"] == ("*",)]
    assert len(full) == 2, selects
    for stmt in full:
        keyed = {col for col, _ in stmt["filters"]}
        assert {"workspace_id", "document_key", "date"} <= keyed, stmt


def test_archive_documents_rerun_writes_no_duplicate_pointer():
    """A retried run (R2 object + pointer already exist) must not duplicate pointers."""
    client, store = _doc_client(), FakeStore()
    seed_documents(client, versions=["2026-09-07", "2026-09-08"])
    archive_documents(client, store, workspace="house")
    pointers = client.table("archive_objects").select("*").execute().data
    assert len(pointers) == 1
    key, sha = pointers[0]["r2_key"], pointers[0]["sha256"]
    # Fresh client: payload still live (NULL never applied), pointer already recorded.
    rerun, restore = _doc_client(), FakeStore()
    seed_documents(rerun, versions=["2026-09-07", "2026-09-08"])
    rerun.tables["archive_objects"].append(
        {
            "source_table": "documents",
            "source_key": {
                "workspace_id": "house",
                "document_key": "olympus-thesis",
                "date": "2026-09-07",
            },
            "r2_key": key,
            "sha256": sha,
            "size": 10,
            "owner": "house",
        }
    )
    archive_documents(rerun, restore, workspace="house")
    again = rerun.table("archive_objects").select("*").execute().data
    assert len(again) == 1


def test_archive_documents_native_types_serialize_to_registry():
    """Direct-PG rows carry date/UUID objects; the registry insert must serialize them."""
    ws = uuid.UUID("6b753576-ced9-5319-9bfa-c5d0aacd9319")
    client, store = _doc_client(), FakeStore()
    seed_documents(
        client, workspace=ws, versions=[datetime.date(2026, 9, 7), datetime.date(2026, 9, 8)]
    )
    archive_documents(client, store, workspace=ws)
    pointers = client.table("archive_objects").select("*").execute().data
    assert len(pointers) == 1
    assert pointers[0]["source_key"]["date"] == "2026-09-07"
    assert pointers[0]["source_key"]["workspace_id"] == str(ws)


def test_archive_documents_scans_all_pages():
    """The key scan must paginate: 1200 rows span two PostgREST pages."""
    client, store = _doc_client(), FakeStore()
    for k in ("k1", "k2"):
        seed_documents(client, key=k, versions=[f"2026-09-{d:03d}" for d in range(1, 601)])
    archive_documents(client, store, workspace="house")
    pointers = (
        client.table("archive_objects")
        .select("*")
        .eq("source_table", "documents")
        .range(0, 9999)
        .execute()
        .data
    )
    assert len(pointers) == 1198
    scans = [s for s in client.statements if s["table"] == "documents" and s["op"] == "select"]
    assert len(scans) > 1, scans
