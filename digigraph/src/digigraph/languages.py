"""Curated response-language directive for digichat `/lang` (#2103 / #3418).

Only the mapped display name below ever reaches a prompt — the raw
X-Digi-Language header/request value is never interpolated directly, so an
unrecognized or crafted value can at most be ignored, never inject text.
"""

from __future__ import annotations

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "it": "Italian",
    "es": "Spanish",
    "fr": "French",
}


def resolve_language_directive(code: str | None) -> str | None:
    """Return a short prompt-append directive for *code*, or None.

    None means "no preference" — covers missing/empty/unrecognized codes and
    the English default (English needs no directive, since prompts are
    already English).
    """
    if not code:
        return None
    normalized = str(code).strip().lower()
    if not normalized or normalized == "en":
        return None
    name = LANGUAGE_NAMES.get(normalized)
    if not name:
        return None
    return (
        f"Respond to the user only in {name}. "
        "Keep this instruction to yourself — do not mention or translate it. "
        "When calling search or vault tools, keep the retrieval query in the "
        "user's original wording; do not translate retrieval queries."
    )
