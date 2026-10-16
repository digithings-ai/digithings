"""Reasoning-effort directive for digichat ``X-Digi-Effort`` (#3736).

Only curated labels reach a prompt — unknown values are ignored.
"""

from __future__ import annotations

EFFORTS = frozenset({"low", "medium", "high"})

_DIRECTIVES: dict[str, str] = {
    "low": "Work at low reasoning effort: keep the answer short and direct.",
    "high": (
        "Work at high reasoning effort: check edge cases and prefer a careful, complete answer."
    ),
}


def resolve_effort_directive(raw: str | None) -> str | None:
    """Return a short prompt-append directive, or None for medium/unknown."""
    if not raw:
        return None
    key = str(raw).strip().lower()
    if key not in EFFORTS:
        return None
    return _DIRECTIVES.get(key)
