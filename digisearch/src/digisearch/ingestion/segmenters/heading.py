"""Generic markdown heading segmenter. Used for markdown, converted HTML, and OpenAPI."""

from __future__ import annotations

import re

from digisearch.core.models import Segment

# ATX headings only ("# Title"). Setext ("Title\n===") is not used by this pipeline's
# html_to_markdown output or by any repo doc, so it is deliberately unsupported.
_HEADING = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*$", re.MULTILINE)

INTRO_LABEL = "heading:(intro)"


def heading_segments(markdown_text: str, *, max_split_level: int = 3) -> list[Segment]:
    """Split markdown at headings of level <= ``max_split_level``.

    Returns an empty list when the text contains no qualifying heading, which callers
    treat as "no known structure" and fall back to whole-document handling.
    """
    if not markdown_text.strip():
        return []
    matches = [m for m in _HEADING.finditer(markdown_text) if len(m.group(1)) <= max_split_level]
    if not matches:
        return []

    segments: list[Segment] = []
    preamble = markdown_text[: matches[0].start()].strip()
    if preamble:
        segments.append(Segment(index=0, label=INTRO_LABEL, text=preamble))

    stack: list[tuple[int, str]] = []  # (level, heading text) ancestor chain
    for position, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        breadcrumb = " > ".join(text for _, text in stack)
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown_text)
        body = markdown_text[match.start() : end].strip()
        if not body:
            continue
        segments.append(
            Segment(
                index=len(segments),
                label=f"heading:{breadcrumb}",
                text=body,
                metadata={"heading": heading, "level": level},
            )
        )
    return segments
