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
def test_search_local_vault_ignores_stopwords(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "jwt-auth",
        frontmatter={"title": "JWT RS256 scopes"},
        body="digikey issues RS256 tokens and JWKS.",
    )
    v.create_note(
        "filler",
        frontmatter={"title": "What is the how"},
        body="What is this and how does it work for the user?",
    )
    # Without stopword filtering, "what/is/how/the" would rank filler first.
    hits = search_local_vault(v, "What is digikey RS256 JWT?", limit=5)
    assert hits
    assert hits[0].vault_path.endswith("jwt-auth.md")


@pytest.mark.unit
def test_search_local_vault_query_sensitive_top_docs(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "auth",
        subdir="clients/digithings",
        frontmatter={"title": "JWT authentication"},
        body="RS256 JWKS scoped API keys digikey token exchange.",
    )
    v.create_note(
        "rag",
        subdir="clients/digithings",
        frontmatter={"title": "Chroma RAG indexes"},
        body="chunk embed hybrid query digisearch collection digithings_docs.",
    )
    v.create_note(
        "vault",
        subdir="clients/digithings",
        frontmatter={"title": "Obsidian wikilinks"},
        body="frontmatter tags path_prefix digivault local filesystem keyword search.",
    )
    auth = search_local_vault(
        v, "RS256 JWKS digikey token", limit=2, path_prefix="clients/digithings"
    )
    rag = search_local_vault(
        v, "Chroma hybrid embed digisearch", limit=2, path_prefix="clients/digithings"
    )
    assert auth and rag
    assert auth[0].vault_path != rag[0].vault_path
    assert "auth" in auth[0].vault_path
    assert "rag" in rag[0].vault_path


@pytest.mark.unit
def test_search_local_vault_path_prefix_does_not_leak_sibling_tenant(tmp_path: Path) -> None:
    """Regression test for #2358.

    A path_prefix of "clients/acme" must not match notes under a sibling
    directory that merely shares the same characters, e.g. "clients/acme-evil".
    A bare `rel.startswith(prefix)` fallback (pre-fix) would match both.
    """
    root = tmp_path / "vault"
    root.mkdir()
    v = Vault(root)
    v.create_note(
        "secret",
        subdir="clients/acme-evil",
        frontmatter={"title": "Acme Evil confidential plan"},
        body="Acme Evil confidential merger acquisition roadmap secret plan.",
    )
    hits = search_local_vault(
        v,
        "Acme Evil confidential merger acquisition roadmap secret plan",
        limit=5,
        path_prefix="clients/acme",
    )
    assert hits == []
