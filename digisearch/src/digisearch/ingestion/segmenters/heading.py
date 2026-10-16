"""Generic markdown heading segmenter. Used for markdown, converted HTML, and OpenAPI."""

from __future__ import annotations

import re

from digisearch.core.models import Segment

# ATX headings only ("# Title"). Setext ("Title\n===") is not used by this pipeline's
# html_to_markdown output or by any repo doc, so it is deliberately unsupported.
_HEADING = re.compile(r"^(#{1,6})[ \t]+(\S.*?)[ \t]*$", re.MULTILINE)

# Fenced code blocks: ``` or ~~~, three or more of the same character, optionally
# followed by an info string (e.g. "python"). A closing fence must use the same
# character and be at least as long as the opener (CommonMark rule); we only need to
# detect *a* matching close to know we've left the fence, so "same char, len >= open"
# is sufficient here.
_FENCE = re.compile(r"^(`{3,}|~{3,})")

INTRO_LABEL = "heading:(intro)"


def _fenced_line_mask(markdown_text: str) -> list[bool]:
    """Return, per line, whether that line falls inside a fenced code block.

    A line consisting of an opening fence itself counts as "inside" (it is not a
    heading candidate), and so does its matching closing fence line.
    """
    lines = markdown_text.split("\n")
    mask = [False] * len(lines)
    fence_char = ""
    fence_len = 0
    in_fence = False
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if in_fence:
            mask[i] = True
            candidate = _FENCE.match(stripped)
            closes_fence = (
                candidate is not None
                and candidate.group(1)[0] == fence_char
                and len(candidate.group(1)) >= fence_len
            )
            if closes_fence:
                in_fence = False
                fence_char = ""
                fence_len = 0
            continue
        opener = _FENCE.match(stripped)
        if opener:
            mask[i] = True
            in_fence = True
            fence_char = opener.group(1)[0]
            fence_len = len(opener.group(1))
    return mask


def _heading_matches(markdown_text: str, max_split_level: int) -> list[re.Match[str]]:
    fenced = _fenced_line_mask(markdown_text)
    # Precompute the start offset of each line so we can map a match's start position
    # back to a line index and check whether that line sits inside a fence.
    line_starts: list[int] = [0]
    for line in markdown_text.split("\n")[:-1]:
        line_starts.append(line_starts[-1] + len(line) + 1)

    def line_index_for(offset: int) -> int:
        # line_starts is sorted; find the last start <= offset via linear scan from the
        # matches themselves (headings are sparse relative to lines, so this stays cheap
        # in practice, but we binary-search for safety on large documents).
        lo, hi = 0, len(line_starts) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if line_starts[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    matches = []
    for m in _HEADING.finditer(markdown_text):
        if len(m.group(1)) > max_split_level:
            continue
        if fenced[line_index_for(m.start())]:
            continue
        matches.append(m)
    return matches


def heading_segments(markdown_text: str, *, max_split_level: int = 3) -> list[Segment]:
    """Split markdown at headings of level <= ``max_split_level``.

    Lines inside fenced code blocks (``` or ~~~, any length >= 3) are never treated as
    heading split points, even if they start with ``#`` — the segment text still
    contains those lines verbatim, they just cannot start a new section.

    A heading whose section has no content beyond the heading line itself (i.e. another
    qualifying heading follows immediately) is skipped as a segment *boundary* — it does
    not become its own stub segment — but its heading line is never dropped. It is
    carried forward and prepended to the next emitted segment's text; a trailing stub
    with no following segment is appended to the previously emitted segment instead, or
    becomes its own segment if there is no previous segment either. ``index`` stays
    sequential over the segments that ARE emitted.

    Returns an empty list when the text contains no qualifying heading, which callers
    treat as "no known structure" and fall back to whole-document handling.
    """
    if not markdown_text.strip():
        return []
    matches = _heading_matches(markdown_text, max_split_level)
    if not matches:
        return []

    segments: list[Segment] = []
    preamble = markdown_text[: matches[0].start()].strip()
    if preamble:
        segments.append(Segment(index=0, label=INTRO_LABEL, text=preamble))

    stack: list[tuple[int, str]] = []  # (level, heading text) ancestor chain
    # Stub headings skipped so far, not yet surfaced anywhere: (level, heading, breadcrumb,
    # heading_line). Carried forward onto the next emitted segment's text; flushed at the
    # end if the document's last heading(s) are stubs with no following segment.
    pending_stubs: list[tuple[int, str, str, str]] = []
    for position, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, heading))
        breadcrumb = " > ".join(text for _, text in stack)
        end = matches[position + 1].start() if position + 1 < len(matches) else len(markdown_text)
        body = markdown_text[match.start() : end].strip()
        # A stub heading's body is exactly its own heading line (nothing follows before
        # the next qualifying heading or end of document) — skip it as a segment so it
        # doesn't become its own vault note, but remember its heading line so it can be
        # carried into whichever segment ends up surfacing next.
        heading_line = match.group(0).strip()
        if body == heading_line:
            pending_stubs.append((level, heading, breadcrumb, heading_line))
            continue
        if pending_stubs:
            body = "\n".join([*(stub[3] for stub in pending_stubs), body])
            pending_stubs = []
        segments.append(
            Segment(
                index=len(segments),
                label=f"heading:{breadcrumb}",
                text=body,
                metadata={"heading": heading, "level": level},
            )
        )

    if pending_stubs:
        carried = "\n".join(stub[3] for stub in pending_stubs)
        if segments:
            segments[-1].text = f"{segments[-1].text}\n{carried}"
        else:
            level, heading, breadcrumb, _ = pending_stubs[-1]
            segments.append(
                Segment(
                    index=0,
                    label=f"heading:{breadcrumb}",
                    text=carried,
                    metadata={"heading": heading, "level": level},
                )
            )
    return segments
