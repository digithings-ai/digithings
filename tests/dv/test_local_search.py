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
def test_search_local_vault_path_prefix_respects_directory_boundary(tmp_path: Path) -> None:
    """Prefix ``clients/acme`` must not leak notes under ``clients/acme-evil``."""
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "tenant-faq",
        subdir="clients/acme",
        frontmatter={"title": "Acme FAQ"},
        body="Acme password reset steps.",
    )
    v.create_note(
        "evil-faq",
        subdir="clients/acme-evil",
        frontmatter={"title": "Evil FAQ"},
        body="Secret password material from another tenant.",
    )
    hits = search_local_vault(v, "password", limit=10, path_prefix="clients/acme")
    assert hits
    assert all(
        h.vault_path.replace("\\", "/").startswith("clients/acme/")
        or h.vault_path.replace("\\", "/") == "clients/acme.md"
        for h in hits
    )
    assert not any("acme-evil" in h.vault_path.replace("\\", "/") for h in hits)
