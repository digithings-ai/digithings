"""VaultStore protocol — pluggable backends for digivault.

Filesystem (default) and Postgres (``knowledge_notes``) both implement this
surface so agents and services can traverse / maintain a vault without caring
where the bytes live (#1142).
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from digivault.models import Note


@runtime_checkable
class VaultStore(Protocol):
    """Common read/write surface for filesystem and Postgres vault backends."""

    def list_notes(self) -> list[Note]:
        """Every indexed note, sorted by name."""
        ...

    def read_text(self, name: str) -> str:
        """Full markdown text (frontmatter + body) for ``name``."""
        ...

    def backlinks(self, name: str) -> tuple[str, ...]:
        """Names of notes that link to ``name``."""
        ...

    def search_by_tag(self, tag: str) -> list[Note]:
        """Notes whose tag set contains ``tag`` (``#`` prefix optional)."""
        ...

    def neighbors(self, name: str) -> tuple[str, ...]:
        """One-hop neighbors: resolved outlinks union backlinks."""
        ...

    def reindex(self) -> None:
        """Rebuild the in-memory index from the backing store."""
        ...

    def create_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
    ) -> Note:
        """Create a new note; raise if the name already exists."""
        ...

    def set_frontmatter(self, name: str, updates: dict[str, Any]) -> Note:
        """Merge ``updates`` into a note's frontmatter and persist."""
        ...

    def rename(self, old_name: str, new_name: str) -> Note:
        """Rename a note and rewrite inbound ``[[wikilink]]`` targets."""
        ...
