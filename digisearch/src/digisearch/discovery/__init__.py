"""Optional bibliography discovery helpers (Crossref, etc.)."""

from digisearch.discovery.crossref import fetch_crossref_work, work_to_evidence_metadata

__all__ = ["fetch_crossref_work", "work_to_evidence_metadata"]
