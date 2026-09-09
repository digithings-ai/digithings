"""Response-language directive for digichat `/language` (#2103 / #3418 / #3733).

Only the mapped display name below ever reaches a prompt — the raw
X-Digi-Language header/request value is never interpolated directly, so an
unrecognized or crafted value can at most be ignored, never inject text.

Keep in exact sync with ``frontend/digichat/src/lib/languages.ts`` ``LANGUAGES``.
"""

from __future__ import annotations

LANGUAGE_NAMES: dict[str, str] = {
    "af": "Afrikaans",
    "ar": "Arabic",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "ca": "Catalan",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "ga": "Irish",
    "he": "Hebrew",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "id": "Indonesian",
    "is": "Icelandic",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "ms": "Malay",
    "nl": "Dutch",
    "no": "Norwegian",
    "pl": "Polish",
    "pt": "Portuguese",
    "ro": "Romanian",
    "ru": "Russian",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sr": "Serbian",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "th": "Thai",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "vi": "Vietnamese",
    "zh": "Chinese",
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


def apply_language_preference(user_content: str, code: str | None) -> str:
    """Prefix *user_content* with the mapped language directive, if any.

    The raw code never appears in the prompt — only ``LANGUAGE_NAMES`` values.
    English / unknown codes leave the query unchanged.
    """
    directive = resolve_language_directive(code)
    if not directive:
        return user_content
    return f"{directive}\n\n{user_content}"
