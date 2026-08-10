"""Prior-loader protocol and document-key helpers."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from digiquant.olympus.edit_mode.models import ArtifactKey, PriorPublished


class PriorLoader(Protocol):
    def load(self, artifact_key: ArtifactKey, run_date: date) -> PriorPublished | None:
        """Return latest materialized row with ``date < run_date`` for *artifact_key*."""


def artifact_document_key(artifact_key: ArtifactKey) -> str:
    namespace, slug = artifact_key
    if namespace == "segment":
        return slug
    return f"{namespace}/{slug}"
