from __future__ import annotations

from pathlib import Path

import pytest
from digivault.local_search import search_local_vault
from digivault.vault import Vault


@pytest.mark.unit
def test_search_local_vault_ranks_title_and_body(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "alpha-guide",
        frontmatter={"title": "Alpha onboarding", "tags": ["docs"]},
        body="Welcome to Alpha. Reset your password here.",
    )
    v.create_note(
        "beta-pricing",
        frontmatter={"title": "Beta pricing", "tags": ["sales"]},
        body="Unrelated commercial terms.",
    )
    hits = search_local_vault(v, "alpha password", limit=5)
    assert hits
    assert hits[0].vault_path.endswith("alpha-guide.md")
    assert hits[0].rank > 0


@pytest.mark.unit
def test_search_local_vault_empty_query_returns_nothing(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note("only", frontmatter={"title": "Only"}, body="content")
    assert search_local_vault(v, "   ", limit=5) == []
    assert search_local_vault(v, "", limit=5) == []


@pytest.mark.unit
def test_search_local_vault_path_prefix_isolates_tenants(tmp_path: Path) -> None:
    """OCC / digithings corpora under one vault root must not bleed across prefixes."""
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "faq-password",
        subdir="clients/online-compliance-center",
        frontmatter={"title": "OCC password FAQ"},
        body="OCC help: reset your portal password.",
    )
    v.create_note(
        "architecture",
        subdir="clients/digithings",
        frontmatter={"title": "digithings architecture"},
        body="digigraph LangGraph orchestration hub password notes.",
    )
    hits = search_local_vault(
        v, "password", limit=10, path_prefix="clients/online-compliance-center"
    )
    assert hits
    assert all("online-compliance-center" in h.vault_path for h in hits)
    assert not any("clients/digithings" in h.vault_path for h in hits)


@pytest.mark.unit
def test_search_local_vault_path_prefix_requires_segment_boundary(tmp_path: Path) -> None:
    """Prefix ``clients/occ`` must not match sibling ``clients/occasion``."""
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "occ-faq",
        subdir="clients/occ",
        frontmatter={"title": "OCC password"},
        body="portal password reset",
    )
    v.create_note(
        "occasion-faq",
        subdir="clients/occasion",
        frontmatter={"title": "Occasion password"},
        body="unrelated password guide",
    )
    hits = search_local_vault(v, "password", limit=10, path_prefix="clients/occ")
    assert len(hits) == 1
    assert "clients/occ/" in hits[0].vault_path.replace("\\", "/")
    assert "occasion" not in hits[0].vault_path


@pytest.mark.unit
def test_search_local_vault_path_prefix_normalizes_slashes(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "note",
        subdir="clients/occ",
        frontmatter={"title": "Token overlap"},
        body="unique-token body",
    )
    hits = search_local_vault(v, "unique-token", limit=5, path_prefix="/clients/occ/")
    assert len(hits) == 1
