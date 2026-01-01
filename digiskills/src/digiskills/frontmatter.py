"""Render/parse the SKILL.md YAML-frontmatter format.

A SKILL.md file is ``---\\n<yaml frontmatter>\\n---\\n\\n<markdown body>``,
matching Anthropic's Agent Skills format. Only ``name`` and ``description``
are required frontmatter fields.
"""

from __future__ import annotations

import yaml

from digiskills.models import SkillManifest

_DELIMITER = "---\n"


def render_skill_md(manifest: SkillManifest, body: str) -> str:
    """Render a complete ``SKILL.md`` file from a manifest + markdown body."""
    frontmatter = yaml.safe_dump(
        {"name": manifest.name, "description": manifest.description},
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    stripped_body = body.strip("\n")
    return f"{_DELIMITER}{frontmatter}{_DELIMITER}\n{stripped_body}\n"


def parse_skill_md(text: str) -> tuple[SkillManifest, str]:
    """Parse a ``SKILL.md`` file back into ``(manifest, body)``.

    Raises:
        ValueError: when the file has no well-formed ``---``-delimited frontmatter block.
    """
    if not text.startswith(_DELIMITER):
        raise ValueError("SKILL.md must start with a '---' frontmatter delimiter")
    _, _, rest = text.partition(_DELIMITER)
    raw_frontmatter, sep, body = rest.partition(_DELIMITER)
    if not sep:
        raise ValueError("SKILL.md frontmatter block is not closed with a second '---'")
    data = yaml.safe_load(raw_frontmatter) or {}
    manifest = SkillManifest.model_validate(data)
    return manifest, body.lstrip("\n")
