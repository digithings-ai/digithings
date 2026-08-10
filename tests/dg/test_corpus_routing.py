"""Unit tests for digigraph per-tenant corpus routing."""

from __future__ import annotations

import json

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


def test_load_tenant_corpus_map_skips_invalid_entries() -> None:
    raw = json.dumps(
        {
            "BadSlug": {"digisearch_index": "x"},
            "ok": "not-an-object",
            "occ": {"digisearchIndex": "occ_help"},
        }
    )
    table = load_tenant_corpus_map(raw)
    assert set(table) == {"occ"}
    assert table["occ"].digisearch_index == "occ_help"


def test_load_tenant_corpus_map_non_object_is_empty() -> None:
    assert load_tenant_corpus_map("[1,2]") == {}


def test_resolve_ignores_invalid_corpus_index() -> None:
    headers = {"x-digi-corpus-index": "../evil", "x-digi-tenant": "occ"}
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
        )
    }
    out = resolve_corpus_override(headers=headers, corpus_map=mapped)
    assert out.digisearch_index is None
    assert out.vault_path_prefix == "clients/online-compliance-center"


def test_resolve_tenant_slug_param_without_header() -> None:
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            vault_path_prefix="clients/online-compliance-center",
            research_system_prompt="OCC only",
        )
    }
    out = resolve_corpus_override(tenant_slug="OCC", corpus_map=mapped)
    assert out.digisearch_index == "occ_help"
    assert out.vault_path_prefix == "clients/online-compliance-center"
    assert out.research_system_prompt == "OCC only"


def test_resolve_headers_do_not_override_research_prompt() -> None:
    """Research prompt comes from the map only; headers never set it."""
    mapped = {
        "occ": TenantCorpusOverride(
            digisearch_index="occ_help",
            research_system_prompt="from-map",
        )
    }
    out = resolve_corpus_override(
        headers={
            "x-digi-tenant": "occ",
            "x-digi-corpus-index": "hdr_index",
            "x-digi-vault-prefix": "clients/hdr",
        },
        corpus_map=mapped,
    )
    assert out.digisearch_index == "hdr_index"
    assert out.vault_path_prefix == "clients/hdr"
    assert out.research_system_prompt == "from-map"
