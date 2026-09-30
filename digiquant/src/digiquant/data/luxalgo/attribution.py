"""Attribution + external-link conventions for LuxAlgo-sourced values (#4779 P0).

Canonical attribution is **"Sourced from LuxAlgo Library"** plus the upstream
canonical URL (``url`` / ``md_url``) wherever a value is rendered outside the
agent loop. Deep links are the Library page URLs the upstream returns per row —
there is no URL scheme of our own to construct.

License boundary (scope §P0, guard #4845): the Library search/concept/
indicator-metadata reads are research references. Indicator *source code*
(``library_get_source_code``) is CC BY-NC-SA and is deliberately NOT wrapped —
no Pine source is embedded in a paid product surface. A commercial Library
license is an explicit opt-in (``LUXALGO_COMMERCIAL_LICENSE``, default OFF;
see :mod:`digiquant.data.luxalgo.license_guard`), and every payload states
the flag state it was produced under (``commercial_license`` /
``license_state``) so a rendered payload shows whether source-code use was
licensed.
"""

from __future__ import annotations

from .license_guard import (
    LUXALGO_LICENSE_STATE_NOTE_DISABLED,
    LUXALGO_LICENSE_STATE_NOTE_ENABLED,
    commercial_license_note,
    luxalgo_commercial_license_enabled,
)

__all__ = [
    "LUXALGO_ATTRIBUTION",
    "LUXALGO_LIBRARY_URL",
    "LUXALGO_LICENSE_NOTE",
    "LUXALGO_LICENSE_STATE_NOTE_ENABLED",
    "LUXALGO_LICENSE_STATE_NOTE_DISABLED",
    "commercial_license_note",
    "attribution_fields",
]

LUXALGO_ATTRIBUTION = "Sourced from LuxAlgo Library"
LUXALGO_LIBRARY_URL = "https://luxalgo.com/library/"
LUXALGO_LICENSE_NOTE = (
    "Research reference only: concept/indicator metadata, never indicator "
    "source code (CC BY-NC-SA; not embedded in paid product surfaces)."
)


def attribution_fields(
    canonical_url: str | None = None,
    *,
    commercial_license: bool | None = None,
) -> dict[str, str | bool]:
    """The attribution block appended to every LuxAlgo tool payload.

    Always states the license-flag state the payload was produced under:
    ``commercial_license`` plus the matching ``license_state`` sentence, so a
    rendered payload shows whether source-code use was licensed. ``None``
    (default) resolves the live flag; an explicit bool pins the block (tests,
    licensed renderers).
    """
    enabled = (
        luxalgo_commercial_license_enabled() if commercial_license is None else commercial_license
    )
    fields: dict[str, str | bool] = {
        "attribution": LUXALGO_ATTRIBUTION,
        "license_note": LUXALGO_LICENSE_NOTE,
        "commercial_license": enabled,
        "license_state": commercial_license_note(enabled),
    }
    fields["source_url"] = (
        canonical_url.strip() if canonical_url and canonical_url.strip() else LUXALGO_LIBRARY_URL
    )
    return fields
