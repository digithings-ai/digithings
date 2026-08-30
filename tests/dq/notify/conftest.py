"""Shared fakes for notify tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any  # score:allow untyped any — fake Supabase row dicts in tests


@dataclass
class FakeQuery:
    _table: str
    _store: dict[str, list[dict[str, Any]]]
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _select: str = "*"
    _order: tuple[str, bool] | None = None
    _limit: int | None = None

    def select(self, cols: str) -> FakeQuery:
        self._select = cols
        return self

    def eq(self, col: str, val: Any) -> FakeQuery:
        self._filters.append(("eq", col, val))
        return self

    def lt(self, col: str, val: Any) -> FakeQuery:
        self._filters.append(("lt", col, val))
        return self

    def gte(self, col: str, val: Any) -> FakeQuery:
        self._filters.append(("gte", col, val))
        return self

    def in_(self, col: str, vals: list[Any]) -> FakeQuery:
        self._filters.append(("in", col, vals))
        return self

    def order(self, col: str, desc: bool = False) -> FakeQuery:
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> FakeQuery:
        self._limit = n
        return self

    def execute(self) -> Any:
        rows = list(self._store.get(self._table, []))
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "lt":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) < val]
            elif op == "gte":
                rows = [r for r in rows if r.get(col) is not None and r.get(col) >= val]
            elif op == "in":
                rows = [r for r in rows if r.get(col) in val]
        if self._order:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return type("R", (), {"data": rows})()


@dataclass
class FakeSupabase:
    tables: dict[str, list[dict[str, Any]]]
    insert_errors: dict[str, Exception] = field(default_factory=dict)

    def table(self, name: str) -> Any:
        return _FakeTable(name, self)


class _FakeTable:
    def __init__(self, name: str, sb: FakeSupabase) -> None:
        self._name = name
        self._sb = sb
        self._pending_insert: dict[str, Any] | None = None

    def select(self, cols: str) -> FakeQuery:
        return FakeQuery(self._name, self._sb.tables).select(cols)

    def insert(self, row: dict[str, Any]) -> _FakeTable:
        self._pending_insert = row
        return self

    def execute(self) -> Any:
        if self._pending_insert is not None:
            row = dict(self._pending_insert)
            if self._name == "notification_log":
                for existing in self._sb.tables.get(self._name, []):
                    if (
                        existing.get("workspace_id") == row.get("workspace_id")
                        and existing.get("event_key") == row.get("event_key")
                        and existing.get("sent_date") == row.get("sent_date")
                    ):
                        raise Exception("duplicate key value violates unique constraint 23505")
            key = f"{row.get('workspace_id')}:{row.get('event_key')}"
            if key in self._sb.insert_errors:
                raise self._sb.insert_errors[key]
            self._sb.tables.setdefault(self._name, []).append(row)
            self._pending_insert = None
            return type("R", (), {"data": []})()
        raise RuntimeError("unexpected execute")
