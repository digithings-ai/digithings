"""Skill-file loader.

A skill is a ``skills/<slug>/SKILL.md`` under ``digiquant/src/digiquant/atlas/skills/``.
The file has YAML frontmatter (``name``, ``description``) followed by Markdown
instructions. Only the Markdown body is relevant at inference time; the
frontmatter exists for human catalog tooling.

Design:
- One function, ``load_skill(slug)``, returns the body as a string.
- Optional ``load_skill_with_frontmatter`` returns (frontmatter_dict, body)
  for code paths that need both (e.g. the skills catalog CI check in #176's
  commit 9).
- Skills directory is resolved relative to the ``digiquant/``
  package root so tests + production use the same path.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml


class SkillNotFoundError(FileNotFoundError):
    """Raised when ``skills/<slug>/SKILL.md`` is missing.

    Separate exception type so callers (triage, phase wiring) can distinguish
    'skill missing' from other I/O errors and fail loudly with a usable message.
    """


def _atlas_data_root() -> Path:
    """Return the directory holding Atlas skills + templates + config.

    Skills, templates, and config live alongside the Atlas package code
    (``digiquant/src/digiquant/atlas/{skills,templates,config}/``) so they
    ship inside the wheel via ``[tool.setuptools.package-data]``. See
    [#486](https://github.com/digithings-ai/digithings/issues/486).
    """
    return Path(__file__).resolve().parent


def _skill_path(slug: str) -> Path:
    return _atlas_data_root() / "skills" / slug / "SKILL.md"


class MalformedFrontmatterError(ValueError):
    """Raised when a SKILL.md starts with ``---`` but has a broken YAML block."""


def _split_frontmatter(raw: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter_dict, body).

    - No frontmatter (no leading ``---``) → ``({}, raw)``.
    - Well-formed YAML frontmatter → parsed dict + body.
    - Opening ``---`` but missing closing fence, or non-dict YAML → raise
      :class:`MalformedFrontmatterError`. Silent fallback would mask
      authoring errors in skill files, so the loader now fails loud.
    """
    text = raw.lstrip()
    if not text.startswith("---"):
        return {}, raw
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise MalformedFrontmatterError("frontmatter starts with '---' but no closing fence found")
    frontmatter_src = parts[1]
    body = parts[2].lstrip("\n")
    meta = yaml.safe_load(frontmatter_src) or {}
    if not isinstance(meta, dict):
        raise MalformedFrontmatterError(
            f"frontmatter must be a YAML mapping, got {type(meta).__name__}"
        )
    return meta, body


@lru_cache(maxsize=64)
def load_skill(slug: str) -> str:
    """Return the Markdown body of ``skills/<slug>/SKILL.md``.

    Cached — skill bodies are static per process.
    """
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    _, body = _split_frontmatter(raw)
    return body.strip()


def load_skill_with_frontmatter(slug: str) -> tuple[dict[str, object], str]:
    """Return (frontmatter, body). Used by catalog / drift-check tooling."""
    path = _skill_path(slug)
    if not path.is_file():
        raise SkillNotFoundError(f"skill not found: {slug!r} (expected at {path})")
    raw = path.read_text(encoding="utf-8")
    return _split_frontmatter(raw)


def list_skill_slugs() -> list[str]:
    """Return every slug for which ``skills/<slug>/SKILL.md`` exists. Sorted."""
    root = _atlas_data_root() / "skills"
    if not root.is_dir():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file())
