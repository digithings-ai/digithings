"""Deterministic document and chunk identifiers for idempotent ingest."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path


def stable_doc_id(*, source: str, content: str | None = None) -> str:
    """Return a deterministic ``Document.id`` from a source path or inline payload.

    File-backed ingest keys off the resolved filesystem path so re-running ingest
    against the same corpus yields the same document id. Inline ``<bytes>`` /
    ``<string>`` sources fall back to a SHA-256 of the extracted content.
    """
    if source in ("<bytes>", "<string>"):
        if content is None:
            seed_source = source
        else:
            seed_source = hashlib.sha256(content.encode("utf-8")).hexdigest()
    else:
        try:
            path = Path(source)
            seed_source = str(path.resolve()) if path.exists() else source
        except (OSError, ValueError):
            seed_source = source
    seed = f"digisearch::{seed_source}"
    return f"doc-{uuid.uuid5(uuid.NAMESPACE_URL, seed)}"
