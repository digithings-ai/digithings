"""Shared test doubles for the archive test modules.

The checkpoint archive and document archive suites each carried a hand-rolled
PostgREST fake with the same surface. One fake lives here now: one query
object, one row store, one statement log.

Production only ever calls ``.select()`` with a single comma-joined column
string, so the fake records the columns both ways: the checkpoint tests read
the select log (``client.log``) and the document tests read the recorded
statements (``client.statements``).

score:allow untyped any — fake-client payload dict shape mirrors PostgREST rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import (
    Any,  # score:allow untyped any — fake-client payload dict shape mirrors PostgREST rows
)

from digiquant.ops.checkpoint_archive import decompress_payload


@dataclass
class FakeResult:
    """PostgREST response double: ``.data`` holds the rows."""

    data: list[dict[str, Any]]


@dataclass
class FakeQuery:
    """PostgREST query double: filter, order, page, insert, update, delete."""

    # Mirror PostgREST's default page cap: an unbounded select returns at most
    # 1000 rows. Production code must paginate explicitly (see DOC_SCAN_PAGE_SIZE).
    _DEFAULT_PAGE = 1000

    table_name: str
    store: dict[str, list[dict[str, Any]]]
    _filters: list[tuple[str, Any]] = field(default_factory=list)
    _in_filters: list[tuple[str, tuple[Any, ...]]] = field(default_factory=list)
    _pending_insert: dict[str, Any] | None = None
    _pending_update: dict[str, Any] | None = None
    _pending_delete: bool = False
    _order_cols: list[str] = field(default_factory=list)
    _range: tuple[int, int] | None = None
    fail: bool = False
    unstable: bool = False
    _selected: bool = False
    _cols: tuple[str, ...] = ()
    log: list[tuple[str, tuple[tuple[str, Any], ...], int]] = field(default_factory=list)
    statements: list[dict[str, Any]] = field(default_factory=list)

    def select(self, *cols: str) -> "FakeQuery":
        self._selected = True
        self._cols = cols
        return self

    def order(self, *cols: str) -> "FakeQuery":
        """Mirror postgrest-py's variadic .order(); production orders one at a time."""
        self._order_cols.extend(cols)
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        """Inclusive range, matching supabase-py/PostgREST semantics."""
        self._range = (start, end)
        return self

    def delete(self) -> "FakeQuery":
        self._pending_delete = True
        return self

    def eq(self, col: str, val: Any) -> "FakeQuery":
        self._filters.append((col, val))
        return self

    def in_(self, col: str, values: list[Any]) -> "FakeQuery":
        self._in_filters.append((col, tuple(values)))
        return self

    def insert(self, row: dict[str, Any]) -> "FakeQuery":
        self._pending_insert = dict(row)
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self._pending_update = dict(payload)
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        for col, val in self._filters:
            if col.startswith("source_key->>"):
                sub = col.split("->>", 1)[1]
                if not isinstance(row.get("source_key"), dict):
                    return False
                if row["source_key"].get(sub) != val:
                    return False
            elif row.get(col) != val:
                return False
        for col, values in self._in_filters:
            if col.startswith("source_key->>"):
                sub = col.split("->>", 1)[1]
                if not isinstance(row.get("source_key"), dict):
                    return False
                if row["source_key"].get(sub) not in values:
                    return False
            elif row.get(col) not in values:
                return False
        return True

    def _record(self, op: str) -> None:
        self.statements.append(
            {
                "table": self.table_name,
                "op": op,
                "cols": self._cols if op == "select" else None,
                "filters": list(self._filters),
            }
        )

    def execute(self) -> FakeResult:
        table = self.store.setdefault(self.table_name, [])
        if self._pending_insert is not None:
            if self.fail:
                raise RuntimeError(f"injected failure on {self.table_name}")
            # Simulate httpx encode_json: bodies must be JSON-serializable,
            # or the real PostgREST client raises TypeError on .execute().
            json.dumps(self._pending_insert)
            row = self._pending_insert
            self._pending_insert = None
            table.append(row)
            self._record("insert")
            return FakeResult(data=[row])
        rows = [r for r in table if self._matches(r)]
        if self._order_cols:
            cols = self._order_cols
            rows.sort(key=lambda r: tuple(r.get(c) for c in cols))
        elif self.unstable and self._range is not None:
            # Simulate a source whose row order is not stable across offset
            # pages (Postgres makes no guarantee without ORDER BY): rotate the
            # window by the requested offset so pagination can duplicate/skip.
            start = self._range[0]
            if rows:
                shift = start % len(rows)
                rows = rows[shift:] + rows[:shift]
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        else:
            rows = rows[: self._DEFAULT_PAGE]
        if self._pending_delete:
            for row in rows:
                table.remove(row)
            self._record("delete")
            return FakeResult(data=[])
        if self._pending_update is not None:
            for row in rows:
                row.update(self._pending_update)
            self._record("update")
            return FakeResult(data=[dict(r) for r in rows])
        if not self._selected:
            raise RuntimeError(f"select() required before execute() on {self.table_name}")
        select_cols = ",".join(self._cols)
        if select_cols != "*":
            wanted = [c.strip() for c in select_cols.split(",")]
            rows = [{c: r.get(c) for c in wanted} for r in rows]
        else:
            rows = [dict(r) for r in rows]
        self.log.append((select_cols, tuple(self._filters), len(rows)))
        self._record("select")
        return FakeResult(data=rows)


class FakeArchiveClient:
    """PostgREST client double: one row store, one select log, one statement list."""

    def __init__(
        self,
        store: dict[str, list[dict[str, Any]]] | None = None,
        *,
        fail_tables: set[str] | None = None,
        unstable_pagination: bool = False,
    ) -> None:
        self.store: dict[str, list[dict[str, Any]]] = {} if store is None else store
        self.fail_tables: set[str] = set() if fail_tables is None else fail_tables
        self.unstable_pagination = unstable_pagination
        self.log: list[tuple[str, tuple[tuple[str, Any], ...], int]] = []
        self.statements: list[dict[str, Any]] = []

    @property
    def tables(self) -> dict[str, list[dict[str, Any]]]:
        """The row store under its document-archive name."""
        return self.store

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(
            table_name=name,
            store=self.store,
            fail=name in self.fail_tables,
            unstable=self.unstable_pagination,
            log=self.log,
            statements=self.statements,
        )

    def fail_on_table(self, name: str) -> None:
        self.fail_tables.add(name)


class FakeStore:
    """In-memory StorageBackend double."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.original: dict[str, bytes] = {}

    def put(self, key: str, data: bytes) -> None:
        self.objects[key] = bytes(data)
        # Archiver stores compressed bytes; remember the raw form for asserts.
        self.original[key] = decompress_payload(bytes(data))

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def delete(self, key: str) -> None:
        del self.objects[key]
        self.original.pop(key, None)

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(k for k in self.objects if k.startswith(prefix))


def blob_row(**over: Any) -> dict[str, Any]:
    """A ``checkpoint_blobs`` row as PostgREST hands it back."""
    row = {
        "thread_id": "run1::portfolio",
        "checkpoint_ns": "",
        "channel": "phase_portfolio",
        "version": "v1",
        "type": "json",
        "blob": "\\x0102ff",
    }
    row.update(over)
    return row


def write_row(**over: Any) -> dict[str, Any]:
    """A ``checkpoint_writes`` row as PostgREST hands it back."""
    row = {
        "thread_id": "run1::portfolio",
        "checkpoint_ns": "",
        "checkpoint_id": "c1",
        "task_id": "t1",
        "idx": 0,
        "channel": "writes",
        "type": "json",
        "blob": "\\x00aa",
    }
    row.update(over)
    return row
