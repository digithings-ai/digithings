"""HTML to clean markdown for #3853. trafilatura primary, readability fallback."""

from __future__ import annotations


def _via_trafilatura(html: str, url: str) -> str | None:
    try:
        from trafilatura import extract
    except Exception:
        return None
    try:
        out = extract(
            html,
            output_format="markdown",
            include_tables=True,
            include_links=True,
            include_images=False,
            url=url,
            favor_precision=True,
            deduplicate=True,
        )
    except Exception:
        return None
    return out if out and out.strip() else None


def _via_readability(html: str) -> str | None:
    try:
        from markdownify import markdownify as md
        from readability import Document
    except Exception:
        return None
    try:
        summary = Document(html).summary()
        if not summary or not summary.strip():
            return None
        return md(summary, heading_style="ATX").strip() or None
    except Exception:
        return None


def extract_markdown(html: str, url: str = "") -> str:
    if not html or not html.strip():
        return ""
    return _via_trafilatura(html, url) or _via_readability(html) or ""
