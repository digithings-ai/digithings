"""Crossref API: resolve DOI → structured metadata for DigiSearch sidecars."""

from __future__ import annotations

from typing import Any

import httpx

from digisearch.core.evidence_metadata import (
    EVIDENCE_TIER_PEER_REVIEWED,
    EVIDENCE_TIER_WORKING_PAPER,
)

_USER_AGENT = (
    "DigiSearch/0.1 (https://github.com/digithings-ai/digithings; research indexing; +https://digithings.ai)"
)


def _normalize_doi(doi: str) -> str:
    d = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix.lower()):
            d = d[len(prefix) :].strip()
    return d


def fetch_crossref_work(doi: str, timeout: float = 30.0) -> dict[str, Any]:
    """GET Crossref ``/works/{doi}``. Raises ``httpx.HTTPError`` on failure."""
    nid = _normalize_doi(doi)
    url = f"https://api.crossref.org/works/{nid}"
    with httpx.Client(timeout=timeout) as client:
        r = client.get(url, headers={"User-Agent": _USER_AGENT})
        r.raise_for_status()
    body = r.json()
    msg = body.get("message")
    return msg if isinstance(msg, dict) else {}


def work_to_evidence_metadata(msg: dict[str, Any]) -> dict[str, Any]:
    """Map Crossref work JSON to DigiSearch normative metadata keys."""
    title = msg.get("title")
    if isinstance(title, list) and title:
        title = str(title[0])
    elif title is not None:
        title = str(title)
    else:
        title = None

    year: int | None = None
    issued = msg.get("issued")
    if isinstance(issued, dict):
        parts = issued.get("date-parts")
        if isinstance(parts, list) and parts:
            inner = parts[0]
            if isinstance(inner, list) and inner and isinstance(inner[0], int):
                year = inner[0]

    venue: str | None = None
    ct = msg.get("container-title")
    if isinstance(ct, list) and ct:
        venue = str(ct[0])
    elif isinstance(ct, str):
        venue = ct

    doi = msg.get("DOI")
    if doi:
        doi_str = str(doi)
    else:
        doi_str = None

    typ = (msg.get("type") or "").lower()
    if typ in ("journal-article", "proceedings-article"):
        tier = EVIDENCE_TIER_PEER_REVIEWED
        peer = True
    elif typ in ("posted-content", "report", "dissertation", "book", "book-chapter"):
        tier = EVIDENCE_TIER_WORKING_PAPER
        peer = False
    else:
        tier = EVIDENCE_TIER_WORKING_PAPER
        peer = False

    out: dict[str, Any] = {
        "evidence_tier": tier,
        "peer_reviewed": peer,
        "title": title,
        "venue": venue,
        "publication_year": year,
        "doi_or_arxiv": doi_str,
        "language": (str(msg["language"]) if msg.get("language") else None),
    }
    return {k: v for k, v in out.items() if v is not None}
