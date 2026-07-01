"""YAML frontmatter parse/serialize — round-trip safe.

A note file is ``---\\n<yaml>\\n---\\n<body>``. We keep this self-contained (no
``python-frontmatter`` dependency) and lean on PyYAML, which is already a
repo-wide dependency.
"""

from __future__ import annotations

from typing import Any  # noqa: ANN401 — frontmatter values are arbitrary YAML scalars/maps

import yaml

_FENCE = "---"


def split_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Split note text into ``(frontmatter_mapping, body)``.

    Returns an empty mapping and the original text when there is no frontmatter
    block. A frontmatter block must start on the very first line with ``---`` and
    be closed by a line that is exactly ``---``.
    """
    if not text.startswith(_FENCE):
        return {}, text
    lines = text.splitlines(keepends=True)
    # lines[0] is the opening fence; find the closing fence.
    closing_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\n").rstrip("\r") == _FENCE:
            closing_idx = i
            break
    if closing_idx is None:
        # Unterminated fence — treat the whole file as body, no frontmatter.
        return {}, text
    raw_yaml = "".join(lines[1:closing_idx])
    body = "".join(lines[closing_idx + 1 :])
    try:
        loaded = yaml.safe_load(raw_yaml) if raw_yaml.strip() else {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(loaded, dict):
        return {}, text
    return loaded, body


def dump_frontmatter(frontmatter: dict[str, Any], body: str) -> str:
    """Serialize ``frontmatter`` + ``body`` back into note text.

    With an empty mapping, returns the body unchanged (no empty fence block).
    """
    if not frontmatter:
        return body
    yaml_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).rstrip("\n")
    # No extra newline after the closing fence: the body is appended verbatim so
    # that split_frontmatter(dump_frontmatter(fm, body)) == (fm, body) exactly.
    return f"{_FENCE}\n{yaml_text}\n{_FENCE}\n{body}"


def set_keys(text: str, updates: dict[str, Any]) -> str:
    """Return note text with ``updates`` merged into its frontmatter mapping."""
    fm, body = split_frontmatter(text)
    merged = {**fm, **updates}
    return dump_frontmatter(merged, body)
