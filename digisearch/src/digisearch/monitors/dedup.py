"""Phase C monitor dedup — changedetection.io + Huginn semantics (#4065, Task 3).

changedetection.io (Apache-2.0) contributes the per-watch content fingerprint
and the "notify only on change" behavior; Huginn (MIT) contributes the
event-with-memory agents and seen-ID dedup memory. Neither is a dependency,
sidecar, or vendored code — the described behavior is reimplemented here on the
stdlib only (``hashlib`` + ``difflib``), deterministic and offline: no
embeddings, no network, no page fetches.

URL identity is the landed Phase B citation identity (R2): ``normalize_url``
from :mod:`digisearch.web_search.citation` is imported, never redefined, so a
monitor's dedup key equals the citation key Phase B web research uses.

A fingerprint is ``"<normalized title>\\x1f<sha256>"``. The digest is sha256
over ``title.strip().lower()`` + ``"\\n"`` + whitespace-collapsed text; the
normalized title component rides along so the near-duplicate leg can compare a
new title against previously seen titles — the memory handed to
:func:`dedup_results` is otherwise opaque fingerprints only.
"""

from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
from typing import Any

from digisearch.monitors.models import DedupRule
from digisearch.web_search.citation import normalize_url

__all__ = ["dedup_results", "fingerprint"]

_COMPONENT_SEPARATOR = "\x1f"


def fingerprint(title: str, text: str) -> str:
    """Deterministic content fingerprint over a normalized title + text.

    The digest is sha256 over ``title.strip().lower()`` + ``"\\n"`` + the
    whitespace-collapsed ``text``. ``text`` extraction (result ``text`` → EXA
    ``highlights`` → OSS ``snippet``, R7) happens in :func:`dedup_results`
    before this is called.
    """
    normalized_title = title.strip().lower()
    collapsed_text = " ".join(text.split())
    digest = hashlib.sha256(f"{normalized_title}\n{collapsed_text}".encode("utf-8")).hexdigest()
    return f"{normalized_title}{_COMPONENT_SEPARATOR}{digest}"


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def _seen_title(stored_fingerprint: str) -> str:
    """Recover the normalized title component of a stored fingerprint."""
    return _normalize_title(stored_fingerprint.split(_COMPONENT_SEPARATOR, 1)[0])


def _result_title(result: dict[str, Any]) -> str:
    return str(result.get("title") or "")


def _result_text(result: dict[str, Any]) -> str:
    """R7 multi-key text extraction: ``text`` → EXA ``highlights`` → ``snippet``."""
    text = result.get("text")
    if isinstance(text, str) and text.strip():
        return text
    highlights = result.get("highlights")
    if isinstance(highlights, list):
        joined = " ".join(str(item) for item in highlights).strip()
        if joined:
            return joined
    snippet = result.get("snippet")
    if isinstance(snippet, str):
        return snippet
    return ""


def _result_fingerprint(result: dict[str, Any]) -> str:
    return fingerprint(_result_title(result), _result_text(result))


def _is_near_duplicate_title(title: str, seen_titles: list[str], threshold: float) -> bool:
    candidate = _normalize_title(title)
    if not candidate:
        return False
    return any(
        SequenceMatcher(None, candidate, seen_title).ratio() >= threshold
        for seen_title in seen_titles
        if seen_title
    )


def dedup_results(
    current: list[dict[str, Any]],
    seen: dict[str, str],
    rule: DedupRule,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Split *current* search results into new/changed survivors vs. already-known.

    ``seen`` maps normalized URL → fingerprint (the Huginn-style memory).
    Unseen URLs are new — unless (``match="url_content"``) their title is a
    near-duplicate (``difflib.SequenceMatcher`` ratio ≥
    ``rule.similarity_threshold``) of a seen title, in which case they collapse
    to unchanged. A seen URL is unchanged with ``match="url"`` (content
    ignored); with ``match="url_content"`` it is unchanged when its fingerprint
    matches the memory and changed — reported as new content — when it does not.
    Stats keys are exactly ``seen``, ``new``, ``changed`` and ``unchanged``;
    ``seen`` counts current results whose normalized URL was already in the
    memory, and collapsed near-duplicates land in ``unchanged``.
    """
    stats = {"seen": 0, "new": 0, "changed": 0, "unchanged": 0}
    survivors: list[dict[str, Any]] = []
    seen_titles = [_seen_title(value) for value in seen.values()]
    for result in current:
        key = normalize_url(str(result.get("url") or ""))
        stored = seen.get(key)
        if stored is not None:
            stats["seen"] += 1
            if rule.match == "url" or _result_fingerprint(result) == stored:
                stats["unchanged"] += 1
                continue
            stats["changed"] += 1
            survivors.append(result)
            continue
        if rule.match == "url_content" and _is_near_duplicate_title(
            _result_title(result), seen_titles, rule.similarity_threshold
        ):
            stats["unchanged"] += 1
            continue
        stats["new"] += 1
        survivors.append(result)
    return survivors, stats
