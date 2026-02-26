"""Validate Sitaas project index configuration and Azure index filtering.

- Unit: validate YAML config (field_mapping, filterable_fields, schema consistency).
- Integration: when Azure env is set, probe index (sample docs, distinct filter values)
  and test structured filter syntax.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml

# Repo root: tests/ds/ -> repo root is parent of tests/
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SITAAS_ROOT = REPO_ROOT / "projects" / "sitaas"
PROJECT_CONFIG = SITAAS_ROOT / "config.yaml"
INDEX_CONFIG = SITAAS_ROOT / "indexes" / "unified-content-index.yaml"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


# --- Unit: config validation ---


@pytest.mark.unit
def test_sitaas_project_config_exists_and_includes_indexes_dir() -> None:
    """Sitaas config.yaml exists and uses indexes_dir so all indexes/*.yaml are included."""
    assert PROJECT_CONFIG.exists(), "projects/sitaas/config.yaml should exist"
    cfg = _load_yaml(PROJECT_CONFIG)
    indexes_dir = cfg.get("indexes_dir")
    assert indexes_dir == "indexes", "config should set indexes_dir: indexes"
    # Load via DigiProjectConfig to get discovered indexes
    from digigraph.project_config import DigiProjectConfig
    project_cfg = DigiProjectConfig.load(str(PROJECT_CONFIG))
    indexes = project_cfg.get_indexes()
    assert len(indexes) >= 1, "indexes_dir should discover at least one index"
    first = indexes[0]
    assert first.get("name") == "unified-content-index"
    assert first.get("config_ref") == "indexes/unified-content-index.yaml"
    assert "digisearch_unified_content_index_query" in project_cfg.get_mcp_tools()


@pytest.mark.unit
def test_unified_content_index_yaml_exists() -> None:
    """Unified content index YAML exists and has index_name."""
    assert INDEX_CONFIG.exists(), "projects/sitaas/indexes/unified-content-index.yaml should exist"
    cfg = _load_yaml(INDEX_CONFIG)
    assert cfg.get("index_name") == "unified-content-index"


@pytest.mark.unit
def test_index_field_mapping_complete() -> None:
    """Field mapping references required keys and schema has those fields."""
    cfg = _load_yaml(INDEX_CONFIG)
    fm = cfg.get("field_mapping") or {}
    schema = cfg.get("schema") or {}
    required = ["content_field", "key_field", "doc_id_field"]
    for k in required:
        assert k in fm, f"field_mapping should have {k}"
        fname = fm[k]
        assert fname in schema, f"schema should define field_mapping.{k}={fname}"
    if fm.get("content_fallback"):
        assert fm["content_fallback"] in schema


@pytest.mark.unit
def test_filterable_fields_in_schema() -> None:
    """Every filterable_fields entry exists in schema (Azure filterable = in schema)."""
    cfg = _load_yaml(INDEX_CONFIG)
    filterable = set(cfg.get("filterable_fields") or [])
    schema = cfg.get("schema") or {}
    for f in filterable:
        assert f in schema, f"filterable_fields '{f}' must exist in schema"


@pytest.mark.unit
def test_facetable_fields_in_schema() -> None:
    """Every facetable_fields entry exists in schema (Azure facetable = in schema)."""
    cfg = _load_yaml(INDEX_CONFIG)
    facetable = set(cfg.get("facetable_fields") or [])
    schema = cfg.get("schema") or {}
    for f in facetable:
        assert f in schema, f"facetable_fields '{f}' must exist in schema"


@pytest.mark.unit
def test_result_metadata_fields_in_schema() -> None:
    """result_metadata_fields exist in schema."""
    cfg = _load_yaml(INDEX_CONFIG)
    meta = set(cfg.get("result_metadata_fields") or [])
    schema = cfg.get("schema") or {}
    for f in meta:
        assert f in schema, f"result_metadata_fields '{f}' must exist in schema"


@pytest.mark.unit
def test_sitaas_odata_filter_format() -> None:
    """Structured filters for Sitaas filterable_fields produce correct OData strings."""
    from digisearch.indexes.backends.azure_search import _build_odata_filter
    cfg = _load_yaml(INDEX_CONFIG)
    filterable = cfg.get("filterable_fields") or []
    assert "sourceType" in filterable and "hasAttachments" in filterable
    single = _build_odata_filter(
        [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}],
        filterable,
    )
    assert single == "(sourceType eq 'EXCHANGE')"
    two = _build_odata_filter(
        [
            {"field": "sourceType", "op": "eq", "value": "EXCHANGE"},
            {"field": "hasAttachments", "op": "eq", "value": True},
        ],
        filterable,
    )
    assert "(sourceType eq 'EXCHANGE')" in two
    assert "(hasAttachments eq true)" in two
    assert " and " in two
    # search.in for multi-value (op 'in')
    in_filter = _build_odata_filter(
        [{"field": "sourceType", "op": "in", "value": ["EXCHANGE", "TEAMS"]}],
        filterable,
    )
    assert in_filter == "search.in(sourceType, 'EXCHANGE,TEAMS', ',')"


# --- Integration: Azure index probe and filtering (skip if no Azure) ---


def _azure_configured() -> bool:
    from digisearch.indexes.backends.azure_search import is_azure_configured
    return is_azure_configured()


@pytest.fixture
def sitaas_index_config_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point DIGISEARCH_INDEX_CONFIG at Sitaas index YAML (for integration tests)."""
    path = str(INDEX_CONFIG.resolve())
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", path)


@pytest.mark.integration
def test_azure_status_when_configured(sitaas_index_config_env: None) -> None:
    """GET /azure_status returns configured True when Azure env + index config set."""
    from fastapi.testclient import TestClient
    from digisearch.server import app
    client = TestClient(app)
    r = client.get("/azure_status")
    assert r.status_code == 200
    data = r.json()
    # If Azure env is not set, configured is False; if set, we expect True and optionally reachable
    assert "configured" in data
    if data["configured"]:
        assert "reachable" in data or "message" in data


@pytest.mark.integration
def test_query_sample_returns_valid_shape(sitaas_index_config_env: None) -> None:
    """POST /query with broad query returns 200 and valid result shape (when Azure configured)."""
    from fastapi.testclient import TestClient
    from digisearch.server import app
    if not _azure_configured():
        pytest.skip("Azure not configured (AZURE_SEARCH_* + DIGISEARCH_INDEX_CONFIG)")
    client = TestClient(app)
    r = client.post(
        "/query",
        json={
            "text": "message",
            "index_name": "unified-content-index",
            "top_k": 5,
            "columns": ["sourceType", "itemType", "fromAddress", "subject"],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "total" in data
    assert "query" in data
    for res in data["results"]:
        assert "content" in res
        assert "metadata" in res
        assert "score" in res


@pytest.mark.integration
def test_query_with_structured_filter_syntax(sitaas_index_config_env: None) -> None:
    """POST /query with structured filters (sourceType eq) returns 200; all results match filter."""
    from fastapi.testclient import TestClient
    from digisearch.server import app
    if not _azure_configured():
        pytest.skip("Azure not configured")
    client = TestClient(app)
    r = client.post(
        "/query",
        json={
            "text": "*",
            "index_name": "unified-content-index",
            "top_k": 10,
            "filters": [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}],
            "columns": ["sourceType", "itemType", "fromAddress"],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    # Every result must have metadata.sourceType == EXCHANGE (filter correctly applied)
    for res in data["results"]:
        meta = res.get("metadata") or {}
        assert "sourceType" in meta, "result metadata should include filter field when columns requested"
        assert meta["sourceType"] == "EXCHANGE", f"filter not applied: got sourceType={meta['sourceType']!r}"


@pytest.mark.integration
def test_query_with_multiple_structured_filters(sitaas_index_config_env: None) -> None:
    """POST /query with two structured filters builds AND OData; all results match both filters."""
    from fastapi.testclient import TestClient
    from digisearch.server import app
    if not _azure_configured():
        pytest.skip("Azure not configured")
    client = TestClient(app)
    r = client.post(
        "/query",
        json={
            "text": "meeting",
            "index_name": "unified-content-index",
            "top_k": 5,
            "filters": [
                {"field": "sourceType", "op": "eq", "value": "EXCHANGE"},
                {"field": "hasAttachments", "op": "eq", "value": True},
            ],
            "columns": ["sourceType", "hasAttachments"],
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    for res in data["results"]:
        meta = res.get("metadata") or {}
        assert meta.get("sourceType") == "EXCHANGE", "first filter must be applied"
        assert meta.get("hasAttachments") is True, "second filter must be applied"
