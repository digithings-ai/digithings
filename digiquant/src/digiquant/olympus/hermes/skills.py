"""Hermes skill-file loader.

Mirrors :mod:`digiquant.olympus.atlas.skills` but resolves paths under
``digiquant/src/digiquant/olympus/hermes/skills/``. Each engine's ``load_skill()`` only finds
its own skills — Atlas cannot resolve Hermes-side analyst / debate / PM
skills and vice versa. See [ADR-0015](../../../../docs/adr/0015-atlas-vs-hermes.md).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# Re-export the shared exception types from Atlas's loader so callers can
# catch a single class regardless of which engine raised. Hermes's loader
# is a path-only fork; the parser logic is intentionally identical.
from digiquant.olympus.atlas.skills import (
    MalformedFrontmatterError,
    SkillNotFoundError,
    _split_frontmatter,
)

__all__ = [
    "MalformedFrontmatterError",
    "SkillNotFoundError",
    "list_skill_slugs",
    "load_skill",
    "load_skill_with_frontmatter",
]


def _hermes_data_root() -> Path:
    """Return ``digiquant/src/digiquant/olympus/hermes/`` (the Hermes package dir).

    Skills + templates live alongside the package code so they ship inside
    the wheel via ``[tool.setuptools.package-data]`` (#486).
    """
    return Path(__file__).resolve().parent


def _skill_path(slug: str) -> Path:
    return _hermes_data_root() / "skills" / slug / "SKILL.md"


@lru_cache(maxsize=64)
def load_skill(slug: str) -> str:
    """Return the Markdown body of ``digiquant/src/digiquant/olympus/hermes/skills/<slug>/SKILL.md``."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return body.strip()


def load_skill_with_frontmatter(slug: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter, body) for a Hermes-side skill file."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    return _split_frontmatter(raw)


def list_skill_slugs() -> list[str]:
    """Return every slug for which ``digiquant/src/digiquant/olympus/hermes/skills/<slug>/SKILL.md`` exists. Sorted."""
    root = _hermes_data_root() / "skills"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
