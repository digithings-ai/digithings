"""Shared in-memory FakeSupabaseClient for unit tests (#1196).

Canonical location for the Atlas/Hermes/overlay PostgREST fake. Prefer::

    from tests.fixtures.fake_supabase import FakeSupabaseClient

``tests.dq.atlas.test_supabase_io`` re-exports the same symbols for older
imports. Simpler upsert-only stubs in ``tests/dq/data/`` and friends stay
local — they intentionally omit filter semantics.

score:allow untyped any — fake-client payload dict shape mirrors PostgREST rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,  # score:allow untyped any — fake-client payload dict shape mirrors PostgREST rows
)

from digiquant.olympus.tenancy import house_workspace_id

# ─── In-memory fake Supabase client ─────────────────────────────────────────


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    """Records calls and returns canned rows, honoring lt/gte/order/limit.

    The previous version of this fake made those methods no-ops, so tests
    that set ``desc=True`` or ``.limit(5)`` were validating Python list
    order, not real filter semantics. Now the fake actually applies them —
    so callers break loudly if the adapter forgets a filter.
    """

    table_name: str
    store: dict[str, list[dict[str, Any]]]
    canned: list[dict[str, Any]] = field(default_factory=list)
    _upsert_row: dict[str, Any] | list[dict[str, Any]] | None = None
    _insert_rows: list[dict[str, Any]] | None = None
    _update_row: dict[str, Any] | None = None
    _delete: bool = False
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order: tuple[str, bool] | None = None
    _limit: int | None = None
    _range: tuple[int, int] | None = None

    def select(self, _cols: str) -> "_FakeQuery":
        return self

    def lt(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lt", col, val))
        return self

    def lte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lte", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def eq(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col: str, vals: list[Any] | tuple[Any, ...]) -> "_FakeQuery":
        # Match the Supabase Python client surface — ``in_`` filters rows whose
        # column value is one of ``vals``.
        self._filters.append(("in_", col, list(vals)))
        return self

    def like(self, col: str, pattern: str) -> "_FakeQuery":
        # PostgREST ``like``; only the trailing-``%`` prefix form is used in-repo.
        self._filters.append(("like", col, pattern))
        return self

    def order(self, col: str, desc: bool = False) -> "_FakeQuery":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def range(self, start: int, end: int) -> "_FakeQuery":
        # PostgREST ``.range`` is inclusive on both ends (0-indexed).
        self._range = (start, end)
        return self

    def insert(self, row: dict[str, Any] | list[dict[str, Any]]) -> "_FakeQuery":
        # PostgREST ``insert()``. Deliberately does **not** stamp ``_on_conflict``
        # the way ``upsert`` below does: the portfolio-ledger tables (migration 069)
        # grant service_role SELECT + INSERT only and are append-only by trigger, so
        # a writer that reaches for ``upsert`` on one of them is a bug. Keeping the
        # two paths distinguishable in ``store`` is what lets a test assert which
        # verb the writer actually used.
        self._insert_rows = [dict(r) for r in row] if isinstance(row, list) else [dict(row)]
        return self

    def upsert(
        self,
        row: dict[str, Any] | list[dict[str, Any]],
        on_conflict: str | None = None,
    ) -> "_FakeQuery":
        if isinstance(row, list):
            self._upsert_row = [{**item, "_on_conflict": on_conflict} for item in row]
        else:
            self._upsert_row = {**row, "_on_conflict": on_conflict}
        return self

    def update(self, payload: dict[str, Any]) -> "_FakeQuery":
        self._update_row = dict(payload)
        return self

    def delete(self) -> "_FakeQuery":
        # PostgREST ``delete().eq(...).execute()``; removes matching rows from the
        # write-side ``store`` (reads come from ``canned``, so a test that exercises
        # a delete seeds the row in both).
        self._delete = True
        return self

    def _matches(self, row: dict[str, Any]) -> bool:
        house = str(house_workspace_id())
        for op, col, val in self._filters:
            row_val = row.get(col)
            if op == "eq" and col == "workspace_id" and row_val is None and val == house:
                # TEST-FAKE courtesy only: legacy house fixtures omit the column.
                # Production PostgREST .eq("workspace_id", house) does not match
                # NULL/missing rows; migration 097 backfill stamps live rows.
                continue
            if op == "eq" and row_val != val:
                return False
            if op == "lt" and str(row.get(col, "")) >= str(val):
                return False
            if op == "lte" and str(row.get(col, "")) > str(val):
                return False
            if op == "gte" and str(row.get(col, "")) < str(val):
                return False
            if op == "in_" and row_val not in val:
                return False
            if op == "like" and not str(row.get(col, "")).startswith(str(val).rstrip("%")):
                return False
        return True

    def execute(self) -> _FakeResponse:
        if self._insert_rows is not None:
            self.store.setdefault(self.table_name, []).extend(self._insert_rows)
            return _FakeResponse(data=[dict(row) for row in self._insert_rows])
        if self._upsert_row is not None:
            rows = self._upsert_row if isinstance(self._upsert_row, list) else [self._upsert_row]
            self.store.setdefault(self.table_name, []).extend(rows)
            return _FakeResponse(data=[dict(row) for row in rows])
        if self._delete is True:
            rows = self.store.get(self.table_name, [])
            removed = [r for r in rows if self._matches(r)]
            self.store[self.table_name] = [r for r in rows if not self._matches(r)]
            return _FakeResponse(data=removed)
        if self._update_row is not None:
            # Apply update to rows in store that match all eq filters. Mirrors
            # PostgREST's ``update().eq(...).execute()`` chain semantics so the
            # ``status='pending'`` idempotency guard in
            # ``update_decision_resolution`` is exercised end-to-end.
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if self._matches(row):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        rows = [r for r in self.canned if self._matches(r)]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._range is not None:
            start, end = self._range
            rows = rows[start : end + 1]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class FakeSupabaseClient:
    """Fake client with per-table canned-read state."""

    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    canned_reads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )
