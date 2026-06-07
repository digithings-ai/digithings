"""Supabase connector — thin wrapper around the ``supabase`` Python client.

Consolidates the hand-rolled Supabase access scattered across services
(twelve-x ``nodes/store.py`` / ``history.py`` / ``fx_calendar/calendar_db.py``;
digiquant ``atlas/supabase_io.py`` / ``data/prices/supabase_writer.py``) into a
single ``digibase[supabase]`` optional extra so consumers stop re-implementing
``client.table(T).upsert(...)`` / ``.select(...).eq(...)`` chains.

Design (mirrors the existing connectors):
- The ``supabase`` package is an *optional* extra. The import is deferred into
  :meth:`SupabaseConnector.from_env` so ``import digibase.connectors.supabase``
  and the base connector types stay usable on a lightweight base install.
- The client is dependency-injected via a :class:`SupabaseClient` Protocol
  (same shape as ``digiquant.atlas.supabase_io.SupabaseClient``) so unit tests
  pass an in-memory fake without a live DB or the optional dependency.
- Writes are idempotent upserts on schema-declared unique keys
  (``on_conflict=...``); replays of the same node are safe. Write failures are
  caught and returned as ``SupabaseWriteResult(success=False, error=...)``,
  mirroring ``NotionConnector``'s ``UpsertResult`` contract.
- Every write emits a redacted audit line via ``digibase.audit.redact_mapping``.
  Only non-sensitive *metadata* (table, operation, row count, on_conflict) is
  audited — never row bodies, which may carry PII/licensed data the shallow,
  key-name-based redactor cannot scrub. This matches the explicit warnings in
  both digiquant Supabase modules.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

from digibase.audit import redact_mapping

logger = logging.getLogger(__name__)


class SupabaseClient(Protocol):
    """Minimal surface used from the ``supabase`` Python client.

    Defined as a Protocol so tests inject a fake without pulling the optional
    ``supabase`` dependency. Production callers pass the real ``Client`` (whose
    ``table()`` returns a PostgREST query builder).
    """

    def table(self, name: str) -> Any: ...  # noqa: D102, E704


class SupabaseNotConfiguredError(RuntimeError):
    """Raised when ``SUPABASE_URL`` / ``SUPABASE_SERVICE_KEY`` are missing."""


@dataclass
class SupabaseWriteResult:
    """Result of an upsert. ``rows`` is the number of rows sent (not the count
    PostgREST echoes back, which depends on ``returning=`` and is not always
    available). Mirrors ``digiquant...supabase_writer.UpsertResult`` plus the
    ``success``/``error`` shape of ``NotionConnector``'s result.
    """

    success: bool
    table: str = ""
    rows: int = 0
    error: str = ""


@dataclass
class SupabaseReadResult:
    """Result of a select. ``rows`` is the decoded ``response.data`` list;
    ``count`` is the server-side total when ``count=`` is requested, else None.
    """

    success: bool
    rows: list[dict[str, Any]] = field(default_factory=list)
    count: int | None = None
    error: str = ""


class SupabaseConnector:
    """Supabase data-store connector for upserts and filtered reads.

    Construct from an injected client (tests, or callers that already hold a
    ``supabase.Client``) or from the environment via :meth:`from_env`.
    """

    # Default batch size for chunked upserts — matches the value both twelve-x
    # (calendar_db: 200) and digiquant (supabase_writer: 500) settled on; 500 is
    # comfortably under PostgREST's default request-size limits for JSON rows.
    DEFAULT_CHUNK = 500

    def __init__(self, client: SupabaseClient) -> None:
        self._client = client

    @classmethod
    def from_env(
        cls,
        *,
        url_var: str = "SUPABASE_URL",
        key_var: str = "SUPABASE_SERVICE_KEY",
    ) -> SupabaseConnector:
        """Build a connector from environment variables.

        Resolves ``SUPABASE_URL`` and the service-role key (``SUPABASE_SERVICE_KEY``
        by default), then constructs a live client. The ``supabase`` package is
        an optional extra, so its import is deferred to here — importing this
        module never requires the dependency.

        Raises:
            SupabaseNotConfiguredError: if either variable is unset/blank.
        """
        url = os.environ.get(url_var, "").strip()
        key = os.environ.get(key_var, "").strip()
        missing = [name for name, val in ((url_var, url), (key_var, key)) if not val]
        if missing:
            raise SupabaseNotConfiguredError(f"missing required env var(s): {', '.join(missing)}")

        from supabase import create_client  # deferred — supabase is an optional dep

        return cls(create_client(url, key))

    @property
    def client(self) -> SupabaseClient:
        """The underlying Supabase client (escape hatch for unwrapped calls)."""
        return self._client

    def upsert(
        self,
        table: str,
        rows: dict[str, Any] | list[dict[str, Any]],
        *,
        on_conflict: str | None = None,
        chunk: int = DEFAULT_CHUNK,
    ) -> SupabaseWriteResult:
        """Upsert one row or a list of rows into ``table``.

        Idempotent when ``on_conflict`` names the row's unique key(s) — replays
        update in place instead of duplicating. Large lists are sent in batches
        of ``chunk`` rows so a single request never exceeds PostgREST limits.

        Args:
            table:       Target table name.
            rows:        A single row dict or a list of row dicts.
            on_conflict: Comma-separated unique-key columns, e.g. ``"file_id,run_date"``.
            chunk:       Max rows per request (default :data:`DEFAULT_CHUNK`).

        Returns:
            SupabaseWriteResult with the total rows sent, or ``success=False``
            and the error string if any batch raised.
        """
        batch = [rows] if isinstance(rows, dict) else list(rows)
        if not batch:
            return SupabaseWriteResult(success=True, table=table, rows=0)

        # Only pass on_conflict when set, so a no-conflict upsert is byte-identical
        # to the bare ``client.table(t).upsert(rows)`` form used in production
        # (e.g. digiquant price_history writes) rather than relying on the
        # client's handling of an explicit ``on_conflict=None``.
        extra = {"on_conflict": on_conflict} if on_conflict else {}
        try:
            total = 0
            for start in range(0, len(batch), max(1, chunk)):
                payload = batch[start : start + chunk]
                query = self._client.table(table).upsert(payload, **extra)
                query.execute()
                total += len(payload)
            self._audit(table, "upsert", total, on_conflict)
            return SupabaseWriteResult(success=True, table=table, rows=total)
        except Exception as exc:  # noqa: BLE001 — surface any client/transport error
            logger.error("supabase: upsert failed for %s: %s", table, exc)
            return SupabaseWriteResult(success=False, table=table, error=str(exc))

    def select(
        self,
        table: str,
        columns: str = "*",
        *,
        eq: dict[str, Any] | None = None,
        gte: dict[str, Any] | None = None,
        lte: dict[str, Any] | None = None,
        in_: dict[str, list[Any] | tuple[Any, ...]] | None = None,
        order: str | None = None,
        desc: bool = False,
        limit: int | None = None,
        count: str | None = None,
    ) -> SupabaseReadResult:
        """Run a filtered ``select`` and return decoded rows.

        Filters compose as PostgREST does (logical AND). Each filter dict maps
        ``column -> value``; ``in_`` maps ``column -> iterable of values``.

        Args:
            table:   Source table name.
            columns: Comma-separated column list (``"*"`` for all).
            eq:      Equality filters, e.g. ``{"status": "pending"}``.
            gte:     ``>=`` filters, e.g. ``{"run_date": "2026-01-01"}``.
            lte:     ``<=`` filters.
            in_:     Membership filters, e.g. ``{"country": ["US", "EU"]}``.
            order:   Column to sort by (applied server-side).
            desc:    Sort descending when ``order`` is set.
            limit:   Max rows to return.
            count:   PostgREST count strategy (``"exact"``/``"planned"``/
                     ``"estimated"``) to populate :attr:`SupabaseReadResult.count`.

        Returns:
            SupabaseReadResult with ``rows`` (``response.data`` or ``[]``) and
            ``count`` when requested, or ``success=False`` with the error.
        """
        try:
            query = (
                self._client.table(table).select(columns, count=count)
                if count is not None
                else self._client.table(table).select(columns)
            )
            for col, val in (eq or {}).items():
                query = query.eq(col, val)
            for col, val in (gte or {}).items():
                query = query.gte(col, val)
            for col, val in (lte or {}).items():
                query = query.lte(col, val)
            for col, vals in (in_ or {}).items():
                query = query.in_(col, list(vals))
            if order is not None:
                query = query.order(order, desc=desc)
            if limit is not None:
                query = query.limit(limit)

            response = query.execute()
            data = list(getattr(response, "data", None) or [])
            total = getattr(response, "count", None)
            return SupabaseReadResult(success=True, rows=data, count=total)
        except Exception as exc:  # noqa: BLE001 — surface any client/transport error
            logger.error("supabase: select failed for %s: %s", table, exc)
            return SupabaseReadResult(success=False, error=str(exc))

    # ── Private helpers ───────────────────────────────────────────────────────

    def _audit(self, table: str, operation: str, rows: int, on_conflict: str | None) -> None:
        """Emit a redacted audit line with metadata only.

        Contract — important: ``digibase.audit.redact_mapping`` redacts VALUES of
        keys whose names contain ``password|api_key|token|secret``; it does not
        recurse and does not pattern-match values. We therefore audit ONLY
        non-sensitive metadata (table, operation, row count, on_conflict) and
        never row bodies, which may contain PII or licensed data the shallow
        redactor cannot scrub. The ``redact_mapping`` call guarantees the
        invariant at the call site even though no secret-keyed field is present.
        """
        logger.info(
            "supabase audit: %s",
            redact_mapping(
                {
                    "table": table,
                    "operation": operation,
                    "rows": rows,
                    "on_conflict": on_conflict,
                }
            ),
        )
