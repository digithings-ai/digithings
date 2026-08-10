"""Unit tests for digigraph per-tenant corpus routing."""

from __future__ import annotations

import pytest

from digigraph.corpus_routing import (
    TenantCorpusOverride,
    load_tenant_corpus_map,
    resolve_corpus_override,
)

pytestmark = pytest.mark.unit


def test_load_tenant_corpus_map_parses_camel_and_snake() -> None:
    raw = (
        '{"occ":{"digisearchIndex":"occ_help","vaultPathPrefix":"clients/online-compliance-center"},'
        '"digithings":{"digisearch_index":"digithings_docs","vault_path_prefix":"/clients/digithings/"}}'
    )
    table = load_tenant_corpus_map(raw)
    assert table["occ"].digisearch_index == "occ_help"
    assert table["occ"].vault_path_prefix == "clients/online-compliance-center"
    assert table["digithings"].digisearch_index == "digithings_docs"
    assert table["digithings"].vault_path_prefix == "clients/digithings"


def test_resolve_headers_win_over_map() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        )
    }
    headers = {
        "x-digi-corpus-index": "other_index",
        "x-digi-vault-prefix": "clients/other",
        "x-digi-tenant": "occ",
    }
    out = resolve_corpus_override(headers=headers, corpus_map=mapped)
    assert out.digisearch_index == "other_index"
    assert out.vault_path_prefix == "clients/other"


def test_resolve_falls_back_to_map_for_tenant() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
            research_system_prompt="OCC prompt",
        )
    }
    out = resolve_corpus_override(
        headers={"x-digi-tenant": "occ"},
        corpus_map=mapped,
    )
    assert out.digisearch_index == "occ_help"
    assert out.vault_path_prefix == "clients/online-compliance-center"
    assert out.research_system_prompt == "OCC prompt"


def test_invalid_map_json_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", "{not-json")
    assert load_tenant_corpus_map() == {}
