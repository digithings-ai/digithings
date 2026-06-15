"""Pydantic v2 models for the DigiVault core.

These are the typed result objects the vault returns — never bare dicts. The
service and MCP layers serialize these directly.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


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
