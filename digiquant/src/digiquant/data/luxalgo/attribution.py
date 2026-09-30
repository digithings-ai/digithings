"""Attribution + external-link conventions for LuxAlgo-sourced values (#4779 P0).

Canonical attribution is **"Sourced from LuxAlgo Library"** plus the upstream
canonical URL (``url`` / ``md_url``) wherever a value is rendered outside the
agent loop. Deep links are the Library page URLs the upstream returns per row —
there is no URL scheme of our own to construct.

License boundary (scope §P0): the Library search/concept/indicator-metadata
reads are research references. Indicator *source code*
(``library_get_source_code``) is CC BY-NC-SA and is deliberately NOT wrapped —
no Pine source is embedded in a paid product surface.
"""

from __future__ import annotations

__all__ = [
    "LUXALGO_ATTRIBUTION",
    "LUXALGO_LIBRARY_URL",
    "LUXALGO_LICENSE_NOTE",
    "attribution_fields",
]

LUXALGO_ATTRIBUTION = "Sourced from LuxAlgo Library"
LUXALGO_LIBRARY_URL = "https://luxalgo.com/library/"
LUXALGO_LICENSE_NOTE = (
    "Research reference only: concept/indicator metadata, never indicator "
    "source code (CC BY-NC-SA; not embedded in paid product surfaces)."
)


def attribution_fields(canonical_url: str | None = None) -> dict[str, str]:
    """The attribution block appended to every LuxAlgo tool payload."""
    fields = {
        "attribution": LUXALGO_ATTRIBUTION,
        "license_note": LUXALGO_LICENSE_NOTE,
    }
    fields["source_url"] = (
        canonical_url.strip() if canonical_url and canonical_url.strip() else LUXALGO_LIBRARY_URL
    )
    return fields
