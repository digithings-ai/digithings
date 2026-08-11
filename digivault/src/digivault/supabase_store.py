"""Supabase-backed vault store — read an Obsidian vault persisted in Postgres.

Reconstructs digivault notes from a Supabase table (``architecture_notes`` /
``knowledge_notes`` — Obsidian-shaped rows: ``frontmatter`` jsonb + ``body_markdown``
+ ``wikilinks`` []) and feeds them to :meth:`Vault.from_sources`, so the *same*
indexing — frontmatter, ``[[wikilinks]]``, backlinks, tags, lint — applies to a
DB-hosted vault as to an on-disk one (digivault store protocol, #1087).

The vault holds public open-core docs: read with the anon key for agents; the
service role only writes (the sync job). ``supabase`` is imported lazily and lives
behind the optional ``digivault[supabase]`` extra — ``import digivault`` never loads it.
"""

from __future__ import annotations

import os
from typing import (  # score:allow untyped any — Supabase client/response shapes are dynamic
    Any,
    Protocol,
)

from pydantic import BaseModel, Field

from digivault import frontmatter as _fm
from digivault.models import VaultConfig
from digivault.vault import Vault

DEFAULT_TABLE = "architecture_notes"
DEFAULT_SEARCH_RPC = "search_architecture_notes"

# Columns needed to reconstruct a note. body+frontmatter round-trip via
# dump_frontmatter; the Vault re-parses them so tags/wikilinks/backlinks match disk.
_SELECT = "vault_path,title,frontmatter,body_markdown"


class VaultSearchHit(BaseModel):
    """A ranked full-text hit from the ``search_architecture_notes`` RPC (migration 068)."""

    vault_path: str
    title: str
    note_type: str
    summary: str
    body_markdown: str
    tags: tuple[str, ...] = Field(default=())
    wikilinks: tuple[str, ...] = Field(default=())
    rank: float


class SupabaseClientProtocol(Protocol):
    """The slice of a ``supabase.Client`` this store uses (lets tests inject a fake)."""

    def table(self, name: str) -> Any: ...
    def rpc(self, fn: str, params: dict[str, Any]) -> Any: ...


class SupabaseStoreError(RuntimeError):
    """Raised when Supabase credentials are missing or a query fails."""


def _rows(response: Any) -> list[dict[str, Any]]:
    """PostgREST responses expose decoded rows on ``.data``."""
    return list(getattr(response, "data", None) or [])


class SupabaseStore:
    """Read a digivault vault out of a Supabase table.

    Inject a client for tests, or build one from the environment with
    :meth:`from_env`. Read-only — writes go through the sync job (digibase upsert).
    """

    def __init__(
        self,
        client: SupabaseClientProtocol,
        *,
        table: str = DEFAULT_TABLE,
        search_rpc: str = DEFAULT_SEARCH_RPC,
    ) -> None:
        self._client = client
        self._table = table
        self._search_rpc = search_rpc

    @classmethod
    def from_env(
        cls,
        *,
        table: str = DEFAULT_TABLE,
        search_rpc: str = DEFAULT_SEARCH_RPC,
    ) -> SupabaseStore:
        """Build a store from env credentials (ADR-0022 CORE_* names, with fallbacks).

        Reads prefer the anon key (the vault is anon-readable via RLS); the service
        role also works for trusted callers (e.g. the self-hosted MCP server).
        """
        url = _first_env("CORE_SUPABASE_URL", "SUPABASE_URL")
        key = _first_env(
            "CORE_SUPABASE_ANON_KEY",
            "CORE_SUPABASE_SERVICE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
        )
        if not url or not key:
            raise SupabaseStoreError(
                "Supabase not configured: set CORE_SUPABASE_URL + a key "
                "(CORE_SUPABASE_ANON_KEY or CORE_SUPABASE_SERVICE_KEY)."
            )
        try:
            from supabase import create_client  # lazy: optional [supabase] extra
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise SupabaseStoreError(
                "The 'supabase' package is required: install digivault[supabase]."
            ) from exc
        return cls(create_client(url, key), table=table, search_rpc=search_rpc)

    def sources(self) -> list[tuple[str, str]]:
        """Reconstruct ``(rel_path, markdown_text)`` pairs for :meth:`Vault.from_sources`."""
        pairs: list[tuple[str, str]] = []
        for row in _rows(self._client.table(self._table).select(_SELECT).execute()):
            vault_path = str(row.get("vault_path") or "").strip()
            if not vault_path:
                continue
            frontmatter = dict(row.get("frontmatter") or {})
            body = str(row.get("body_markdown") or "")
            pairs.append((f"{vault_path}.md", _fm.dump_frontmatter(frontmatter, body)))
        return pairs

    def list_notes(
        self,
        *,
        path_prefix: str | None = None,
        page_size: int = 500,
    ) -> list[dict[str, Any]]:
        """Every note under ``path_prefix``, paginated.

        ``sources()`` cannot be used for this: it selects the whole table with no
        prefix filter and no pagination, so it silently truncates at PostgREST's
        server-side row cap. This pages explicitly with ``.range()`` and stops on
        the first short page.
        """
        prefix = (path_prefix or "").strip().strip("/")
        out: list[dict[str, Any]] = []
        start = 0
        while True:
            query = self._client.table(self._table).select(_SELECT)
            if prefix:
                query = query.like("vault_path", f"{prefix}%")
            page = query.order("vault_path").range(start, start + page_size - 1).execute()
            rows = list(getattr(page, "data", None) or [])
            for row in rows:
                vault_path = str(row.get("vault_path") or "").strip()
                if not vault_path:
                    continue
                if prefix and vault_path != prefix and not vault_path.startswith(prefix + "/"):
                    continue
                out.append(row)
            if len(rows) < page_size:
                return out
            start += page_size

    def load_vault(self, *, config: VaultConfig | None = None) -> Vault:
        """Materialize a read-only :class:`Vault` from the table."""
        return Vault.from_sources(self.sources(), config=config)

    def search(
        self, query: str, *, limit: int = 7, path_prefix: str | None = None
    ) -> list[VaultSearchHit]:
        """Full-text search via the ``search_architecture_notes`` RPC (ranked hits).

        Always calls the 3-arg RPC (migration 068): ``path_prefix`` is ``None`` when
        unset so Postgres applies the default (unfiltered). Requires 068 applied.
        """
        prefix = (path_prefix or "").strip().strip("/") or None
        response = self._client.rpc(
            self._search_rpc,
            {"query": query, "match_limit": limit, "path_prefix": prefix},
        ).execute()
        hits = [VaultSearchHit.model_validate(row) for row in _rows(response)]
        if prefix is None:
            return hits[:limit]
        return [h for h in hits if h.vault_path == prefix or h.vault_path.startswith(prefix + "/")][
            :limit
        ]


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""
