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
from typing import Any  # noqa: ANN401 — frontmatter values are arbitrary YAML scalars/maps

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
        self.reindex()

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

    def reindex(self) -> None:
        """Rebuild the note index, link graph, and backlinks from disk."""
        notes: dict[str, Note] = {}
        raw_outlinks: dict[str, list] = {}
        for path in self._iter_markdown():
            text = path.read_text(encoding="utf-8", errors="replace")
            fm, body = _fm.split_frontmatter(text)
            name = path.stem
            links = _wl.parse_links(body)
            raw_outlinks[name] = links
            notes[name] = Note(
                name=name,
                rel_path=path.relative_to(self.root).as_posix(),
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
        return (self.root / note.rel_path).read_text(encoding="utf-8", errors="replace")

    # ── writes ─────────────────────────────────────────────────────────────
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
        clean = name.strip()
        if not clean or "/" in clean or clean.startswith("."):
            raise VaultError(f"Invalid note name: {name!r}")
        if clean in self._notes:
            raise VaultError(f"Note already exists: {clean!r}")
        rel = f"{subdir.strip('/')}/{clean}.md" if subdir.strip("/") else f"{clean}.md"
        path = self._safe_path(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = _fm.dump_frontmatter(frontmatter or {}, body)
        path.write_text(text, encoding="utf-8")
        self.reindex()
        created = self._notes.get(clean)
        if created is None:  # pragma: no cover - defensive
            raise VaultError(f"Failed to create note: {clean!r}")
        return created

    def set_frontmatter(self, name: str, updates: dict[str, Any]) -> Note:
        """Merge ``updates`` into a note's frontmatter and persist."""
        note = self._notes.get(name)
        if note is None:
            raise VaultError(f"No such note: {name!r}")
        path = self.root / note.rel_path
        path.write_text(_fm.set_keys(path.read_text(encoding="utf-8"), updates), encoding="utf-8")
        self.reindex()
        return self._notes[name]

    def rename(self, old_name: str, new_name: str) -> Note:
        """Rename a note and rewrite every inbound ``[[wikilink]]`` to match."""
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
        """Validate the vault: unresolved links, missing frontmatter, orphans, tags."""
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
                                kind="missing_frontmatter",
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
        return LintReport(ok=not issues, note_count=len(self._notes), issues=tuple(issues))
