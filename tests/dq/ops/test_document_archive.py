"""Documents pointer-per-row archive phase (Task 8, #3766).

Self-contained fakes: documents rows are keyed (workspace_id, document_key,
date); the newest date per key stays live while older payloads move to R2
with an archive_objects pointer row left behind.
"""

import datetime
import json
import uuid

from digiquant.ops.checkpoint_archive import archive_documents


class _Result:
    def __init__(self, data):
        self.data = data


class _DocQuery:
    def __init__(self, client, name):
        self._client = client
        self._table = client.tables[name]
        self._name = name
        self._cols = None
        self._filters = []
        self._patch = None
        self._pending_insert = None

    def select(self, *args):
        self._cols = args
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def insert(self, row):
        self._pending_insert = dict(row)
        return self

    def update(self, patch):
        self._patch = patch
        return self

    def _matched(self):
        out = []
        for row in self._table:
            hit = True
            for col, val in self._filters:
                if col.startswith("source_key->>"):
                    field = col.split("->>")[1]
                    if (row.get("source_key") or {}).get(field) != val:
                        hit = False
                        break
                elif row.get(col) != val:
                    hit = False
                    break
            if hit:
                out.append(row)
        return out

    def execute(self):
        if self._pending_insert is not None:
            # Simulate httpx encode_json: bodies must be JSON-serializable,
            # or the real PostgREST client raises TypeError on .execute().
            json.dumps(self._pending_insert)
            self._table.append(self._pending_insert)
            row, self._pending_insert = self._pending_insert, None
            self._client.statements.append(
                {"table": self._name, "op": "insert", "cols": None, "filters": []}
            )
            return _Result([row])
        if self._patch is not None:
            matched = self._matched()
            for row in matched:
                row.update(self._patch)
            self._client.statements.append(
                {
                    "table": self._name,
                    "op": "update",
                    "cols": None,
                    "filters": list(self._filters),
                }
            )
            return _Result(matched)
        self._client.statements.append(
            {
                "table": self._name,
                "op": "select",
                "cols": self._cols,
                "filters": list(self._filters),
            }
        )
        return _Result(list(self._matched()))


class FakeDocClient:
    def __init__(self):
        self.tables = {"documents": [], "archive_objects": []}
        self.statements = []

    def table(self, name):
        return _DocQuery(self, name)


class FakeDocStore:
    def __init__(self):
        self.objects = {}
        self.original = {}

    def put(self, key, data):
        self.objects[key] = bytes(data)

    def get(self, key):
        return self.objects[key]


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
    client, store = FakeDocClient(), FakeDocStore()
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
    client, store = FakeDocClient(), FakeDocStore()
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
    client, store = FakeDocClient(), FakeDocStore()
    seed_documents(client, versions=["2026-09-07", "2026-09-08"])
    archive_documents(client, store, workspace="house")
    pointers = client.table("archive_objects").select("*").execute().data
    assert len(pointers) == 1
    key, sha = pointers[0]["r2_key"], pointers[0]["sha256"]
    # Fresh client: payload still live (NULL never applied), pointer already recorded.
    rerun, restore = FakeDocClient(), FakeDocStore()
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
    client, store = FakeDocClient(), FakeDocStore()
    seed_documents(
        client, workspace=ws, versions=[datetime.date(2026, 9, 7), datetime.date(2026, 9, 8)]
    )
    archive_documents(client, store, workspace=ws)
    pointers = client.table("archive_objects").select("*").execute().data
    assert len(pointers) == 1
    assert pointers[0]["source_key"]["date"] == "2026-09-07"
    assert pointers[0]["source_key"]["workspace_id"] == str(ws)
