"""The Vault — load, index, validate, and maintain a folder of markdown notes.

A vault is a directory of ``*.md`` notes. ``Vault`` builds an in-memory index
(note-by-name), a link graph with backlinks, and a tag index, and exposes the
maintenance operations that keep the vault consistent (create, rename with
inbound-link rewrite, set frontmatter, lint, reindex).

Storage is the local filesystem in v1. Everything is recomputed from disk on
``reindex``; there is no hidden cache to fall out of sync.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import (
    Any,  # score:allow untyped any — frontmatter values are arbitrary YAML scalars/maps
)

import yaml

from digivault import frontmatter as _fm
from digivault import wikilinks as _wl
from digivault.models import LintReport, Note, ValidationIssue, VaultConfig

MANIFEST_NAME = ".digivault.yml"


def _normalize_tags(value: Any) -> tuple[str, ...]:
    """Coerce a frontmatter 'tags' value into a normalized tuple of tag strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        parts: Iterable[str] = value.replace(",", " ").split()
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


class VaultError(ValueError):
    """Raised on invalid vault operations (e.g. path escape, duplicate note)."""


class Vault:
    """An in-memory index over a directory of markdown notes."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise VaultError(f"Vault root is not a directory: {self.root}")
        self.config = self._load_config()
        self._notes: dict[str, Note] = {}
        self._duplicates: dict[str, list[str]] = {}
        # Populated only for store-backed (read-only) vaults built via from_sources,
        # where note bodies cannot be re-read from disk. None => filesystem-backed.
        self._raw_text: dict[str, str] | None = None
        self.reindex()

    @classmethod
    def from_sources(
        cls,
        sources: Iterable[tuple[str, str]],
        *,
        config: VaultConfig | None = None,
    ) -> Vault:
        """Build a **read-only** vault from ``(rel_path, markdown_text)`` pairs.

        Lets a non-filesystem backend (e.g. the Supabase-backed vault in
        ``digivault.supabase_store``) reuse the exact same indexing — frontmatter,
        wikilinks, backlinks, tags, lint — as the on-disk ``Vault``. Writes
        (``create_note``/``rename``/``set_frontmatter``) raise ``VaultError``.
        """
        obj = cls.__new__(cls)
        obj.root = None  # type: ignore[assignment]  # read-only sentinel; writes guarded
        obj.config = config or VaultConfig()
        obj._notes = {}
        obj._duplicates = {}
        obj._raw_text = {}
        obj._build_index(sorted(sources, key=lambda pair: pair[0]))
        return obj

    # ── loading ────────────────────────────────────────────────────────────
    def _load_config(self) -> VaultConfig:
        manifest = self.root / MANIFEST_NAME
        if not manifest.is_file():
            return VaultConfig()
        try:
            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise VaultError(f"Invalid {MANIFEST_NAME}: {exc}") from exc
        if not isinstance(data, dict):
            raise VaultError(f"{MANIFEST_NAME} must be a mapping")
        return VaultConfig.model_validate(data)

    def _iter_markdown(self) -> Iterable[Path]:
        for p in sorted(self.root.rglob("*.md")):
            if any(part.startswith(".") for part in p.relative_to(self.root).parts):
                continue
            yield p

    def _iter_sources(self) -> Iterable[tuple[str, str]]:
        """Yield ``(rel_path, text)`` for every markdown note (filesystem backend)."""
        for path in self._iter_markdown():
            rel = path.relative_to(self.root).as_posix()
            yield rel, path.read_text(encoding="utf-8", errors="replace")

    def reindex(self) -> None:
        """Rebuild the note index, link graph, and backlinks from disk."""
        self._build_index(self._iter_sources())

    def _build_index(self, sources: Iterable[tuple[str, str]]) -> None:
        """Build the note index, link graph, backlinks, and tag index from sources."""
        notes: dict[str, Note] = {}
        raw_outlinks: dict[str, list] = {}
        duplicates: dict[str, list[str]] = {}
        for rel, text in sources:
            fm, body = _fm.split_frontmatter(text)
            name = Path(rel).stem
            if name in notes:
                # Two notes share a filename stem in different folders. Keep the
                # first (deterministic via sorted iteration) and surface the
                # collision through lint instead of silently dropping a note.
                duplicates.setdefault(name, [notes[name].rel_path]).append(rel)
                continue
            if self._raw_text is not None:
                self._raw_text[name] = text
            links = _wl.parse_links(body)
            raw_outlinks[name] = links
            notes[name] = Note(
                name=name,
                rel_path=rel,
                title=fm.get("title"),
                tags=_normalize_tags(fm.get("tags")),
                aliases=_normalize_aliases(fm.get("aliases")),
                frontmatter=fm,
                outlinks=tuple(links),
            )
        # Compute backlinks: name -> names that link to it.
        backlinks: dict[str, set[str]] = {n: set() for n in notes}
        for src, links in raw_outlinks.items():
            for link in links:
                if link.target in backlinks:
                    backlinks[link.target].add(src)
        self._notes = {
            name: note.model_copy(update={"backlinks": tuple(sorted(backlinks[name]))})
            for name, note in notes.items()
        }
        self._duplicates = duplicates

    # ── reads ──────────────────────────────────────────────────────────────
    def list_notes(self) -> list[Note]:
        return [self._notes[n] for n in sorted(self._notes)]

    def get_note(self, name: str) -> Note | None:
        return self._notes.get(name)

    def backlinks(self, name: str) -> tuple[str, ...]:
        note = self._notes.get(name)
        return note.backlinks if note else ()

    def search_by_tag(self, tag: str) -> list[Note]:
        want = tag.strip().lstrip("#")
        return [self._notes[n] for n in sorted(self._notes) if want in self._notes[n].tags]

    def read_text(self, name: str) -> str:
        note = self._notes.get(name)
        if note is None:
            raise VaultError(f"No such note: {name!r}")
        if self._raw_text is not None:  # store-backed: body lives in the cache, not on disk
            return self._raw_text[name]
        return (self.root / note.rel_path).read_text(encoding="utf-8", errors="replace")

    # ── writes ─────────────────────────────────────────────────────────────
    def _require_writable(self) -> None:
        """Read-only (store-backed) vaults from ``from_sources`` cannot be mutated."""
        if self._raw_text is not None:
            raise VaultError("read-only (store-backed) vault: writes are not supported")

    def _safe_path(self, rel: str) -> Path:
        """Resolve ``rel`` under the vault root, refusing escapes (path traversal)."""
        candidate = (self.root / rel).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise VaultError(f"Path escapes vault root: {rel!r}")
        return candidate

    def create_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
    ) -> Note:
        """Create a new note ``<subdir>/<name>.md``. Fails if the name exists."""
        return self.write_note(
            name,
            frontmatter=frontmatter,
            body=body,
            subdir=subdir,
            overwrite=False,
        )

    def write_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
        overwrite: bool = False,
    ) -> Note:
        """Create or optionally overwrite a note ``<subdir>/<name>.md``.

        When ``overwrite`` is False (default), behaves like :meth:`create_note`
        and raises if the stem already exists. When True, replaces the on-disk
        file (and reindexes) so idempotent ingest re-runs can upsert by slug.
        """
        self._require_writable()
        clean = name.strip()
        if not clean or "/" in clean or clean.startswith("."):
            raise VaultError(f"Invalid note name: {name!r}")
        if clean in self._notes and not overwrite:
            raise VaultError(f"Note already exists: {clean!r}")
        if clean in self._notes and overwrite:
            # Prefer the existing relative path so a re-run does not create a
            # duplicate stem under a different subdir.
            rel = self._notes[clean].rel_path
        else:
            rel = f"{subdir.strip('/')}/{clean}.md" if subdir.strip("/") else f"{clean}.md"
        path = self._safe_path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = _fm.dump_frontmatter(frontmatter or {}, body)
        path.write_text(text, encoding="utf-8")
        self.reindex()
        created = self._notes.get(clean)
        if created is None:  # pragma: no cover - defensive
            raise VaultError(f"Failed to write note: {clean!r}")
        return created

    def set_frontmatter(self, name: str, updates: dict[str, Any]) -> Note:
        """Merge ``updates`` into a note's frontmatter and persist."""
        self._require_writable()
        note = self._notes.get(name)
        if note is None:
            raise VaultError(f"No such note: {name!r}")
        path = self.root / note.rel_path
        path.write_text(_fm.set_keys(path.read_text(encoding="utf-8"), updates), encoding="utf-8")
        self.reindex()
        return self._notes[name]

    def prune_children(self, parent_doc: str, keep_names: set[str], subdir: str = "") -> list[str]:
        """Delete stale segment children for one parent note inside ``subdir``.

        A note is removable only if its name begins with the exact parent prefix,
        its frontmatter identifies that same parent, and its resolved path remains
        under the supplied subdirectory. This narrow operation intentionally cannot
        remove a hub note or another document's children.
        """
        self._require_writable()
        parent = parent_doc.strip()
        if not parent or "/" in parent or parent.startswith("."):
            raise VaultError(f"Invalid parent note name: {parent_doc!r}")
        prefix = f"{parent}__"
        if any(not name.startswith(prefix) for name in keep_names):
            raise VaultError("keep_names must contain only children of parent_doc")
        clean_subdir = subdir.strip("/")
        subdir_path = self._safe_path(clean_subdir or ".")
        deleted: list[str] = []
        for name, note in self._notes.items():
            path = self._safe_path(note.rel_path)
            if (
                name.startswith(prefix)
                and name not in keep_names
                and note.frontmatter.get("parent_doc") == parent
                and (path == subdir_path or subdir_path in path.parents)
            ):
                path.unlink()
                deleted.append(name)
        if deleted:
            self.reindex()
        return sorted(deleted)

    def rename(self, old_name: str, new_name: str) -> Note:
        """Rename a note and rewrite every inbound ``[[wikilink]]`` to match."""
        self._require_writable()
        note = self._notes.get(old_name)
        if note is None:
            raise VaultError(f"No such note: {old_name!r}")
        clean_new = new_name.strip()
        if not clean_new or "/" in clean_new or clean_new.startswith("."):
            raise VaultError(f"Invalid new note name: {new_name!r}")
        if clean_new in self._notes:
            raise VaultError(f"Target note already exists: {clean_new!r}")
        old_path = self.root / note.rel_path
        new_rel = note.rel_path[: -len(f"{old_name}.md")] + f"{clean_new}.md"
        new_path = self._safe_path(new_rel)
        old_path.rename(new_path)
        # Rewrite inbound links in every other note.
        for src in note.backlinks:
            src_note = self._notes.get(src)
            if src_note is None:
                continue
            src_path = self.root / src_note.rel_path
            src_path.write_text(
                _wl.rewrite_target(src_path.read_text(encoding="utf-8"), old_name, clean_new),
                encoding="utf-8",
            )
        self.reindex()
        return self._notes[clean_new]

    # ── validation ─────────────────────────────────────────────────────────
    def lint(self) -> LintReport:
        """Validate: unresolved links, missing frontmatter, disallowed tags, orphans, dup stems."""
        issues: list[ValidationIssue] = []
        names = set(self._notes)
        for name in sorted(self._notes):
            note = self._notes[name]
            for link in note.outlinks:
                if link.target not in names:
                    issues.append(
                        ValidationIssue(
                            note=note.rel_path,
                            kind="unresolved_link",
                            message=f"[[{link.target}]] does not resolve to a note",
                        )
                    )
            for key in self.config.required_frontmatter:
                if key not in note.frontmatter:
                    issues.append(
                        ValidationIssue(
                            note=note.rel_path,
                            kind="missing_frontmatter",
                            message=f"required frontmatter key '{key}' is missing",
                        )
                    )
            if self.config.allowed_tags is not None:
                for tag in note.tags:
                    if tag not in self.config.allowed_tags:
                        issues.append(
                            ValidationIssue(
                                note=note.rel_path,
                                kind="disallowed_tag",
                                message=f"tag '{tag}' is not in the vault taxonomy",
                            )
                        )
            if not self.config.allow_orphans and not note.outlinks and not note.backlinks:
                issues.append(
                    ValidationIssue(
                        note=note.rel_path,
                        kind="orphan_note",
                        message="note has no inbound or outbound links",
                    )
                )
        for stem, paths in sorted(self._duplicates.items()):
            issues.append(
                ValidationIssue(
                    note=paths[0],
                    kind="duplicate_note",
                    message=(
                        f"note stem '{stem}' is shared by {len(paths)} files "
                        f"({', '.join(paths)}); only the first is indexed"
                    ),
                )
            )
        return LintReport(ok=not issues, note_count=len(self._notes), issues=tuple(issues))
