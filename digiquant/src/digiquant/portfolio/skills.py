"""portfolio skill-file loader.

Mirrors :mod:`digiquant.research.skills` but resolves paths under
``digiquant/src/digiquant/portfolio/skills/``. Each engine's ``load_skill()`` only finds
its own skills — research cannot resolve portfolio-side analyst / debate / PM
skills and vice versa. See [ADR-0015](../../../../docs/adr/0015-research-vs-portfolio.md).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

# Re-export the shared exception types from research's loader so callers can
# catch a single class regardless of which engine raised. portfolio's loader
# is a path-only fork; the parser logic is intentionally identical.
from digiquant.research.skills import (
    EDIT_SCHEMA_CONSTRAINTS,
    MalformedFrontmatterError,
    SkillNotFoundError,
    _split_frontmatter,
)

__all__ = [
    "MalformedFrontmatterError",
    "SkillNotFoundError",
    "list_skill_slugs",
    "load_skill",
    "load_skill_edit",
    "load_skill_full",
    "load_skill_with_frontmatter",
]


def _portfolio_data_root() -> Path:
    """Return ``digiquant/src/digiquant/portfolio/`` (the portfolio package dir).

    Skills + templates live alongside the package code so they ship inside
    the wheel via ``[tool.setuptools.package-data]`` (#486).
    """
    return Path(__file__).resolve().parent


def _skill_path(slug: str) -> Path:
    return _portfolio_data_root() / "skills" / slug / "SKILL.md"


def _skill_edit_path(slug: str) -> Path:
    return _portfolio_data_root() / "skills" / slug / f"{slug}-edit.md"


def _skill_full_path(slug: str) -> Path:
    return _portfolio_data_root() / "skills" / slug / f"{slug}-full.md"


def _skill_full_candidates(slug: str) -> tuple[Path, ...]:
    """Resolve ``*-full.md`` for a slug, including nested family files.

    Conventional path is ``skills/<slug>/<slug>-full.md``. Hyphenated slugs may
    also live beside a parent skill: ``deliberation-analyst-response`` reads
    ``skills/deliberation/analyst-response-full.md`` (H6 reply; not H5).
    """
    root = _portfolio_data_root() / "skills"
    paths = [root / slug / f"{slug}-full.md"]
    if "-" in slug:
        family, rest = slug.split("-", 1)
        paths.append(root / family / f"{rest}-full.md")
    paths.append(root / slug / "SKILL.md")
    return tuple(paths)


@lru_cache(maxsize=64)
def load_skill_full(slug: str) -> str:
    """Return the Markdown body of a portfolio full skill (see ``_skill_full_candidates``)."""
    last = _skill_full_path(slug)
    for path in _skill_full_candidates(slug):
        last = path
        if path.is_file():
            raw = path.read_text(encoding="utf-8")
            _, body = _split_frontmatter(raw)
            return body.strip()
    raise SkillNotFoundError(f"full skill not found: {slug!r} (expected at {last})")


@lru_cache(maxsize=64)
def load_skill_edit(slug: str) -> str:
    """Return the Markdown body of ``skills/<slug>/<slug>-edit.md``.

    The shared DocumentPatch limits are appended here too (#1740) — portfolio
    analyst/thesis edit turns emit the same patch schema and hit the same
    240-char ``reason`` cap (it took out the H5 asset-analyst run on 2026-07-24).
    """
    path = _skill_edit_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"edit skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return f"{body.strip()}\n\n{EDIT_SCHEMA_CONSTRAINTS}"


@lru_cache(maxsize=64)
def load_skill(slug: str) -> str:
    """Return the Markdown body of ``digiquant/src/digiquant/portfolio/skills/<slug>/SKILL.md``."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return body.strip()


def load_skill_with_frontmatter(slug: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter, body) for a portfolio-side skill file."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    return _split_frontmatter(raw)


def list_skill_slugs() -> list[str]:
    """Return every slug for which ``digiquant/src/digiquant/portfolio/skills/<slug>/SKILL.md`` exists. Sorted."""
    root = _portfolio_data_root() / "skills"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
