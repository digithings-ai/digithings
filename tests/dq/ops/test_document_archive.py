"""Documents pointer-per-row archive phase (Task 8, #3766).

Self-contained fakes: documents rows are keyed (workspace_id, document_key,
date); the newest date per key stays live while older payloads move to R2
with an archive_objects pointer row left behind.
"""

from digiquant.ops.checkpoint_archive import archive_documents


class _Result:
    def __init__(self, data):
        self.data = data


class _DocQuery:
    def __init__(self, table):
        self._table = table
        self._filters = []
        self._patch = None
        self._pending_insert = None

    def select(self, *args):
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
            self._table.append(self._pending_insert)
            row, self._pending_insert = self._pending_insert, None
            return _Result([row])
        if self._patch is not None:
            matched = self._matched()
            for row in matched:
                row.update(self._patch)
            return _Result(matched)
        return _Result(list(self._matched()))


class FakeDocClient:
    def __init__(self):
        self.tables = {"documents": [], "archive_objects": []}

    def table(self, name):
        return _DocQuery(self.tables[name])


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
