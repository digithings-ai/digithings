"""OData filter string validator. Prevents injection into Azure AI Search queries."""

from __future__ import annotations

import re

# Allowlist of OData comparison and logical operators (case-insensitive)
_ALLOWED_OPS = re.compile(
    r"\b(eq|ne|lt|le|gt|ge|and|or|not|in|any|all|add|sub|mul|div|mod)\b",
    re.IGNORECASE,
)

# Block anything that looks like code injection or system access
_BLOCKED = re.compile(
    r"(exec\s*\(|eval\s*\(|system\s*\(|__\w+__|<script|javascript:|data:)",
    re.IGNORECASE,
)

# Only allow characters legal in OData: word chars, spaces (space/tab only — not newlines),
# quotes, parens, comparison symbols, slashes (nav properties), commas, dots, colons, dashes.
# Newlines (\n, \r) and other control characters are explicitly excluded.
_SAFE_CHARS = re.compile(r"^[\w \t'\"<>=!(),./\\:\-\+\*\?%@]+$")


def validate_odata_filter(filter_str: str) -> str:
    """Validate an OData filter string before passing it to the Azure backend.

    Raises ``ValueError`` if the filter contains injection patterns or
    characters that are not legal in OData expressions.

    Returns the original string unchanged when valid.
    """
    if not filter_str or not filter_str.strip():
        return filter_str

    if _BLOCKED.search(filter_str):
        raise ValueError(
            f"OData filter contains blocked pattern: {filter_str!r}. "
            "Use structured filters (filters=[]) for complex queries."
        )

    if not _SAFE_CHARS.match(filter_str):
        raise ValueError(
            f"OData filter contains unsupported characters: {filter_str!r}. "
            "Allowed: word chars, spaces, quotes, comparison operators, parens."
        )

    return filter_str
