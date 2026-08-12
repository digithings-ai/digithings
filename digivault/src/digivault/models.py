"""Pydantic v2 models for the digivault core.

These are the typed result objects the vault returns — never bare dicts. The
service and MCP layers serialize these directly.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class LinkRef(BaseModel):
    """A single Obsidian-style ``[[wikilink]]`` occurrence inside a note.

    ``target`` is the note name as written (without the ``[[`` / ``]]``), with any
    ``#heading`` and ``|alias`` stripped off into their own fields.
    """

    model_config = ConfigDict(frozen=True)

    target: str = Field(..., description="Linked note name, e.g. 'digigraph'")
    heading: str | None = Field(default=None, description="Optional #heading fragment")
    alias: str | None = Field(default=None, description="Optional |display alias")
    embed: bool = Field(default=False, description="True for transclusions: ![[note]]")
    raw: str = Field(..., description="The full matched text, e.g. '[[digigraph#api|API]]'")


class Note(BaseModel):
    """A single markdown note in the vault."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Note name (filename stem), e.g. 'digigraph'")
    rel_path: str = Field(..., description="Path relative to the vault root, POSIX form")
    title: str | None = Field(default=None, description="Frontmatter 'title' if present")
    tags: tuple[str, ...] = Field(default=(), description="Frontmatter tags, normalized")
    aliases: tuple[str, ...] = Field(default=(), description="Frontmatter aliases")
    frontmatter: dict = Field(default_factory=dict, description="Raw parsed frontmatter mapping")
    outlinks: tuple[LinkRef, ...] = Field(default=(), description="Wikilinks found in the body")
    backlinks: tuple[str, ...] = Field(
        default=(), description="Names of notes that link to this note"
    )


class NoteRow(BaseModel):
    """A single row read from the Supabase notes table (``architecture_notes`` /
    ``knowledge_notes``), returned by :meth:`SupabaseStore.list_notes` and consumed
    by ``scripts/vectorize_sync.py``.

    Deliberately not named ``Note``: that name is already taken by the on-disk
    vault's note model above, whose shape (``name``, ``rel_path``, ``outlinks``,
    ``backlinks``, ...) is unrelated to a raw Supabase row.

    The table carries columns beyond the four below (``slug``, ``note_type``,
    ``status``, ``tags``, ``summary``, ``wikilinks``, ``sources``, timestamps).
    Extras are ignored rather than forbidden (the default for a bare
    ``BaseModel``, same as :class:`Note` and :class:`LinkRef` above) — a normal
    full-table row must validate, not crash, when it carries columns this model
    doesn't need.
    """

    model_config = ConfigDict(frozen=True)

    vault_path: str = Field(
        default="", description="Table's vault_path column; blank/missing rows are skipped"
    )
    title: str | None = Field(default=None, description="Note title column; may be null")
    frontmatter: dict = Field(
        default_factory=dict, description="Parsed frontmatter jsonb column; may be null"
    )
    body_markdown: str = Field(default="", description="Markdown body column; may be null/empty")

    @model_validator(mode="before")
    @classmethod
    def _null_columns_to_defaults(cls, data: Any) -> Any:
        """Supabase returns SQL NULL, not absence, for an empty jsonb/text column.

        Coerce those to this model's falsy defaults before field validation so a
        null ``frontmatter``/``body_markdown``/``vault_path`` still validates
        instead of raising — mirroring the ``row.get(...) or default`` pattern
        this model replaces.
        """
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for key, default in (("vault_path", ""), ("frontmatter", {}), ("body_markdown", "")):
            if data.get(key) is None:
                data[key] = default
        return data


class VaultSearchHit(BaseModel):
    """A ranked full-text search hit.

    Returned by both :meth:`SupabaseStore.search` (the ``search_architecture_notes``
    RPC, migration 068) and :meth:`D1Store.search` (FTS5 over Cloudflare D1) — the two
    stores share this result shape rather than each defining their own. Lives here,
    not in ``supabase_store.py``, so the D1 path never imports the Supabase module;
    ``supabase_store.py`` re-exports it for existing importers.
    """

    vault_path: str
    title: str
    note_type: str
    summary: str
    body_markdown: str
    tags: tuple[str, ...] = Field(default=())
    wikilinks: tuple[str, ...] = Field(default=())
    rank: float


class NoteDetail(BaseModel):
    """One note, whole: body and frontmatter together.

    ``Note`` has frontmatter but no body; ``NoteRow``/``VaultSearchHit`` have a body but
    no frontmatter. ``digivault_get_note`` needs both, so this model exists.
    """

    model_config = ConfigDict(frozen=True)

    vault_path: str
    title: str = ""
    note_type: str = ""
    summary: str = ""
    body_markdown: str = ""
    frontmatter: dict = Field(default_factory=dict)
    tags: tuple[str, ...] = Field(default=())
    wikilinks: tuple[str, ...] = Field(default=())
    parent_doc: str | None = None
    segment_index: int | None = None


class ValidationIssue(BaseModel):
    """One problem found by ``Vault.lint``."""

    model_config = ConfigDict(frozen=True)

    note: str = Field(
        ..., description="Note rel_path the issue was found in (or '' for vault-wide)"
    )
    kind: str = Field(
        ...,
        description=(
            "unresolved_link | missing_frontmatter | disallowed_tag | orphan_note | duplicate_note"
        ),
    )
    message: str = Field(..., description="Human-readable description")


class LintReport(BaseModel):
    """Result of linting the whole vault."""

    model_config = ConfigDict(frozen=True)

    ok: bool = Field(..., description="True when there are no issues")
    note_count: int = Field(..., description="Number of notes scanned")
    issues: tuple[ValidationIssue, ...] = Field(default=(), description="All issues found")


class VaultConfig(BaseModel):
    """Vault manifest — required frontmatter keys and the tag taxonomy.

    Loaded from ``.digivault.yml`` at the vault root when present; otherwise the
    defaults apply (no required keys, any tags allowed).
    """

    model_config = ConfigDict(extra="forbid")

    required_frontmatter: tuple[str, ...] = Field(
        default=(), description="Frontmatter keys every note must define"
    )
    allowed_tags: tuple[str, ...] | None = Field(
        default=None,
        description="If set, lint flags any tag not in this taxonomy. None = allow all.",
    )
    allow_orphans: bool = Field(
        default=True, description="If False, lint flags notes with no in- or out-links"
    )
