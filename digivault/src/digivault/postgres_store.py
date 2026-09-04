"""Postgres-backed :class:`~digivault.store.VaultStore` over ``knowledge_notes``.

Reads/writes rows filtered by a ``vault`` namespace column. The in-memory link
graph, backlinks, and tag index are built from the ``wikilinks`` / ``tags``
columns — no markdown parse at serve time (#1142). Writes still parse the body
once so those columns stay consistent with the stored markdown.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import (  # score:allow untyped any — Supabase client/response shapes are dynamic
    Any,
    Protocol,
)

from digivault import frontmatter as _fm
from digivault import wikilinks as _wl
from digivault.models import LinkRef, Note
from digivault.vault import VaultError

DEFAULT_TABLE = "knowledge_notes"
DEFAULT_VAULT = "finance"

_SELECT = (
    "slug,vault_path,title,note_type,status,tags,relevance,summary,"
    "body_markdown,frontmatter,sources,wikilinks,vault"
)


class PostgresClientProtocol(Protocol):
    """The slice of a ``supabase.Client`` this store uses (lets tests inject a fake)."""

    def table(self, name: str) -> Any: ...


class PostgresStoreError(RuntimeError):
    """Raised when Postgres/Supabase credentials are missing or a query fails."""


def _rows(response: Any) -> list[dict[str, Any]]:
    return list(getattr(response, "data", None) or [])


def _normalize_tags(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple)):
        parts = [str(v) for v in value]
    else:
        return ()
    return tuple(p.strip().lstrip("#") for p in parts if str(p).strip())


def _normalize_aliases(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v).strip() for v in value if str(v).strip())
    return ()


def _wikilink_refs(targets: Any) -> tuple[LinkRef, ...]:
    """Synthesize :class:`LinkRef` rows from the stored ``wikilinks`` text[] column."""
    if not targets:
        return ()
    refs: list[LinkRef] = []
    for raw in targets:
        target = str(raw).strip()
        if not target:
            continue
        refs.append(LinkRef(target=target, raw=f"[[{target}]]"))
    return tuple(refs)


def _vault_path_for(name: str, subdir: str = "") -> str:
    clean_subdir = _safe_subdir(subdir)
    return f"{clean_subdir}/{name}" if clean_subdir else name


def _safe_subdir(subdir: str) -> str:
    """Normalize ``subdir`` and refuse path-escape segments (parity with Vault._safe_path)."""
    clean = subdir.strip().strip("/")
    if not clean:
        return ""
    parts = Path(clean).parts
    if any(part in ("", ".", "..") or part.startswith("/") for part in parts):
        raise VaultError(f"Path escapes vault root: {subdir!r}")
    if Path(clean).is_absolute() or clean.startswith("\\"):
        raise VaultError(f"Path escapes vault root: {subdir!r}")
    return "/".join(parts)


def _normalize_str_list(value: Any) -> list[str]:
    """Coerce a frontmatter list-or-string into a list of non-empty strings.

    A bare string becomes a single element (never character-split).
    """
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return []


class PostgresStore:
    """:class:`~digivault.store.VaultStore` over ``public.knowledge_notes``.

    Inject a client for tests, or build one from the environment with
    :meth:`from_env`. Graph indexes come from ``wikilinks`` / ``tags`` columns.

    ``rename`` issues multiple PostgREST calls and is not transactional — a
    mid-flight failure can leave rewritten backlinks with a partially moved
    note. Phase-1 callers should retry ``reindex`` / repair rather than assume
    atomic rename (#1142).
    """

    def __init__(
        self,
        client: PostgresClientProtocol,
        *,
        vault: str = DEFAULT_VAULT,
        table: str = DEFAULT_TABLE,
    ) -> None:
        clean = vault.strip()
        if not clean:
            raise PostgresStoreError("vault namespace must be a non-empty string")
        self._client = client
        self._vault = clean
        self._table = table
        self._notes: dict[str, Note] = {}
        self._bodies: dict[str, str] = {}
        self._rows_by_name: dict[str, dict[str, Any]] = {}
        self.reindex()

    @classmethod
    def from_env(
        cls,
        *,
        vault: str = DEFAULT_VAULT,
        table: str = DEFAULT_TABLE,
    ) -> PostgresStore:
        """Build a store from ADR-0022 CORE_* credentials (service key preferred for writes)."""
        url = _first_env("CORE_SUPABASE_URL", "SUPABASE_URL")
        key = _first_env(
            "CORE_SUPABASE_SERVICE_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "CORE_SUPABASE_ANON_KEY",
            "SUPABASE_ANON_KEY",
        )
        if not url or not key:
            raise PostgresStoreError(
                "Postgres not configured: set CORE_SUPABASE_URL + CORE_SUPABASE_SERVICE_KEY "
                "(or SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY)."
            )
        try:
            from supabase import create_client  # lazy: optional [supabase] extra
        except ImportError as exc:  # pragma: no cover - exercised only without the extra
            raise PostgresStoreError(
                "The 'supabase' package is required: install digivault[supabase]."
            ) from exc
        return cls(create_client(url, key), vault=vault, table=table)

    @property
    def vault(self) -> str:
        return self._vault

    def _scoped(self) -> Any:
        return self._client.table(self._table).eq("vault", self._vault)

    def reindex(self) -> None:
        """Rebuild the note / backlink / tag indexes from ``wikilinks`` and ``tags``."""
        response = (
            self._client.table(self._table)
            .select(_SELECT)
            .eq("vault", self._vault)
            .order("vault_path")
            .execute()
        )
        rows = _rows(response)
        notes: dict[str, Note] = {}
        bodies: dict[str, str] = {}
        rows_by_name: dict[str, dict[str, Any]] = {}
        raw_outlinks: dict[str, tuple[LinkRef, ...]] = {}

        for row in rows:
            slug = str(row.get("slug") or "").strip()
            vault_path = str(row.get("vault_path") or "").strip()
            if not slug or not vault_path:
                continue
            if slug in notes:
                continue
            frontmatter = dict(row.get("frontmatter") or {})
            raw_tags = row.get("tags")
            if raw_tags is None:
                raw_tags = frontmatter.get("tags")
            tags = _normalize_tags(raw_tags)
            aliases = _normalize_aliases(frontmatter.get("aliases"))
            outlinks = _wikilink_refs(row.get("wikilinks"))
            body = str(row.get("body_markdown") or "")
            text = _fm.dump_frontmatter(frontmatter, body)
            notes[slug] = Note(
                name=slug,
                rel_path=f"{vault_path}.md",
                title=row.get("title") or frontmatter.get("title"),
                tags=tags,
                aliases=aliases,
                frontmatter=frontmatter,
                outlinks=outlinks,
            )
            bodies[slug] = text
            rows_by_name[slug] = row
            raw_outlinks[slug] = outlinks

        backlinks: dict[str, set[str]] = {n: set() for n in notes}
        for src, links in raw_outlinks.items():
            for link in links:
                if link.target in backlinks:
                    backlinks[link.target].add(src)

        self._notes = {
            name: note.model_copy(update={"backlinks": tuple(sorted(backlinks[name]))})
            for name, note in notes.items()
        }
        self._bodies = bodies
        self._rows_by_name = rows_by_name

    def list_notes(self) -> list[Note]:
        return [self._notes[n] for n in sorted(self._notes)]

    def get_note(self, name: str) -> Note | None:
        return self._notes.get(name)

    def read_text(self, name: str) -> str:
        if name not in self._bodies:
            raise VaultError(f"No such note: {name!r}")
        return self._bodies[name]

    def backlinks(self, name: str) -> tuple[str, ...]:
        note = self._notes.get(name)
        return note.backlinks if note else ()

    def search_by_tag(self, tag: str) -> list[Note]:
        want = tag.strip().lstrip("#")
        return [self._notes[n] for n in sorted(self._notes) if want in self._notes[n].tags]

    def neighbors(self, name: str) -> tuple[str, ...]:
        note = self._notes.get(name)
        if note is None:
            return ()
        found = {link.target for link in note.outlinks if link.target in self._notes}
        found.update(note.backlinks)
        return tuple(sorted(found))

    def create_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
    ) -> Note:
        clean = name.strip()
        if not clean or "/" in clean or clean.startswith("."):
            raise VaultError(f"Invalid note name: {name!r}")
        if clean in self._notes:
            raise VaultError(f"Note already exists: {clean!r}")
        fm = dict(frontmatter or {})
        vault_path = _vault_path_for(clean, subdir)
        if any(
            (n.rel_path[:-3] if n.rel_path.endswith(".md") else n.rel_path) == vault_path
            for n in self._notes.values()
        ):
            raise VaultError(f"Note path already exists: {vault_path!r}")
        row = self._row_payload(clean, vault_path, fm, body)
        # Insert (not upsert): create must fail if (vault, vault_path) or
        # (vault, slug) already exists — never silently overwrite another slug.
        self._client.table(self._table).insert(row).execute()
        self.reindex()
        created = self._notes.get(clean)
        if created is None:  # pragma: no cover - defensive
            raise VaultError(f"Failed to write note: {clean!r}")
        return created

    def set_frontmatter(self, name: str, updates: dict[str, Any]) -> Note:
        note = self._notes.get(name)
        if note is None:
            raise VaultError(f"No such note: {name!r}")
        text = _fm.set_keys(self.read_text(name), updates)
        fm, body = _fm.split_frontmatter(text)
        vault_path = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
        row = self._row_payload(name, vault_path, fm, body)
        (
            self._client.table(self._table)
            .update(row)
            .eq("vault", self._vault)
            .eq("vault_path", vault_path)
            .execute()
        )
        self.reindex()
        return self._notes[name]

    def rename(self, old_name: str, new_name: str) -> Note:
        note = self._notes.get(old_name)
        if note is None:
            raise VaultError(f"No such note: {old_name!r}")
        clean_new = new_name.strip()
        if not clean_new or "/" in clean_new or clean_new.startswith("."):
            raise VaultError(f"Invalid new note name: {new_name!r}")
        if clean_new in self._notes:
            raise VaultError(f"Target note already exists: {clean_new!r}")

        old_path = note.rel_path[:-3] if note.rel_path.endswith(".md") else note.rel_path
        new_path = str(Path(old_path).with_name(clean_new))

        # Rewrite inbound bodies + wikilinks arrays, then move the note row.
        for src in note.backlinks:
            src_note = self._notes.get(src)
            if src_note is None:
                continue
            rewritten = _wl.rewrite_target(self.read_text(src), old_name, clean_new)
            fm, body = _fm.split_frontmatter(rewritten)
            src_path = (
                src_note.rel_path[:-3] if src_note.rel_path.endswith(".md") else src_note.rel_path
            )
            src_row = self._row_payload(src, src_path, fm, body)
            (
                self._client.table(self._table)
                .update(src_row)
                .eq("vault", self._vault)
                .eq("vault_path", src_path)
                .execute()
            )

        fm, body = _fm.split_frontmatter(self.read_text(old_name))
        new_row = self._row_payload(clean_new, new_path, fm, body)
        self._client.table(self._table).upsert(new_row, on_conflict="vault,vault_path").execute()
        (
            self._client.table(self._table)
            .delete()
            .eq("vault", self._vault)
            .eq("vault_path", old_path)
            .execute()
        )
        self.reindex()
        return self._notes[clean_new]

    def _row_payload(
        self,
        slug: str,
        vault_path: str,
        frontmatter: dict[str, Any],
        body: str,
    ) -> dict[str, Any]:
        links = _wl.parse_links(body)
        tags = _normalize_tags(frontmatter.get("tags"))
        return {
            "vault": self._vault,
            "slug": slug,
            "vault_path": vault_path,
            "title": str(frontmatter.get("title") or slug),
            "note_type": str(frontmatter.get("type", frontmatter.get("note_type", "reference"))),
            "status": str(frontmatter.get("status", "stub")),
            "tags": list(tags),
            "relevance": _normalize_str_list(frontmatter.get("relevance")),
            "summary": str(frontmatter.get("summary") or ""),
            "body_markdown": body,
            "frontmatter": frontmatter,
            "sources": frontmatter.get("sources") or [],
            "wikilinks": sorted({link.target for link in links}),
        }


def _first_env(*names: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""
