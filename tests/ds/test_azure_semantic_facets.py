"""Unit tests for Azure semantic search, facet gating, and speller (issue #144)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from digisearch.core.models import Query, SearchResponse
from digisearch.server import QueryRequest, QueryResponse, app
from digisearch.search import add_chunks
from digisearch.core.models import Chunk
from tests.digi_test_jwt import auth_headers


# --- Index config accepts new fields ---------------------------------------


@pytest.mark.unit
def test_index_config_accepts_new_fields(tmp_path, monkeypatch) -> None:
    """YAML index config accepts semantic_configuration, facets, speller."""
    from digisearch.indexes.backends.azure_search import _get_index_config

    cfg_path = tmp_path / "idx.yaml"
    cfg_path.write_text(
        "index_name: myindex\n"
        "field_mapping:\n"
        "  key_field: id\n"
        "  content_field: content\n"
        "  doc_id_field: doc_id\n"
        "result_metadata_fields: [year]\n"
        "filterable_fields: [year]\n"
        "facets: [year, region, doc_type]\n"
        "semantic_configuration: my-semantic-config\n"
        "speller: true\n"
    )
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", str(cfg_path))
    cfg = _get_index_config()
    assert cfg["semantic_configuration"] == "my-semantic-config"
    assert cfg["facets"] == ["year", "region", "doc_type"]
    assert cfg["speller"] is True


@pytest.mark.unit
def test_index_config_new_fields_default_absent(tmp_path, monkeypatch) -> None:
    """Missing fields default to None / [] / False (back-compat)."""
    from digisearch.indexes.backends.azure_search import _get_index_config

    cfg_path = tmp_path / "idx.yaml"
    cfg_path.write_text("index_name: myindex\n")
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", str(cfg_path))
    cfg = _get_index_config()
    assert cfg["semantic_configuration"] is None
    assert cfg["facets"] == []
    assert cfg["speller"] is False


# --- Query request / response wire-up --------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


@pytest.fixture
def _stub_results(client: TestClient) -> str:
    idx = "__unit_test_facets__"
    add_chunks(
        idx,
        [Chunk(id="c1", content="Content one", doc_id="d1", embedding=None, metadata={})],
    )
    return idx


@pytest.mark.unit
def test_query_request_accepts_include_facets() -> None:
    """QueryRequest validates include_facets as a boolean."""
    req = QueryRequest(text="hello", include_facets=True)
    assert req.include_facets is True
    req2 = QueryRequest(text="hello")
    assert req2.include_facets is False


@pytest.mark.unit
def test_query_response_facets_null_by_default(client: TestClient, _stub_results: str) -> None:
    """Default response (no include_facets) serializes facets as null on keyword backends."""
    r = client.post("/query", json={"text": "Content", "index_name": _stub_results})
    assert r.status_code == 200
    data = r.json()
    assert "facets" in data
    assert data["facets"] is None


@pytest.mark.unit
def test_query_response_facets_serialization_shape() -> None:
    """QueryResponse.facets is dict[str, list[{value, count}]] when populated."""
    resp = QueryResponse(
        results=[],
        query="x",
        index_name="i",
        total=0,
        facets={"year": [{"value": "2024", "count": 7}, {"value": "2023", "count": 3}]},
    )
    payload = resp.model_dump(mode="json")
    assert payload["facets"]["year"][0] == {"value": "2024", "count": 7}


# --- Azure backend SDK signature -------------------------------------------


def _azure_env(monkeypatch, tmp_path, **cfg_extra) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "testkey")
    base = {
        "index_name": "idx",
        "field_mapping": {"key_field": "id", "content_field": "content", "doc_id_field": "doc_id"},
    }
    base.update(cfg_extra)
    import yaml

    cfg_path = tmp_path / "idx.yaml"
    cfg_path.write_text(yaml.safe_dump(base))
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", str(cfg_path))


def _patched_client(return_docs: list[dict] | None = None, facets: dict | None = None) -> MagicMock:
    docs = return_docs or []
    page = MagicMock()
    page.__iter__ = lambda self: iter(docs)
    page.get_facets = MagicMock(return_value=facets)
    page.get_count = MagicMock(return_value=len(docs))
    client = MagicMock()
    client.search = MagicMock(return_value=page)
    return client


@pytest.mark.unit
def test_azure_semantic_kwargs_passed_to_sdk(monkeypatch, tmp_path) -> None:
    """When semantic_configuration is set on the index config, the SDK call uses query_type='semantic'."""
    # Force azure SDK import guard to True without actually importing the package.
    import digisearch.indexes.backends.azure_search as az

    _azure_env(monkeypatch, tmp_path, semantic_configuration="my-config")
    # Refresh module-level env captures.
    monkeypatch.setattr(az, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(az, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(az, "_AZURE_AVAILABLE", True)

    mock_client = _patched_client()
    with patch.object(az, "_get_client", return_value=mock_client):
        resp = az.query_azure(Query(text="hello", top_k=5), index_name="idx")

    assert isinstance(resp, SearchResponse)
    mock_client.search.assert_called_once()
    kwargs = mock_client.search.call_args.kwargs
    assert kwargs["query_type"] == "semantic"
    assert kwargs["semantic_configuration_name"] == "my-config"


@pytest.mark.unit
def test_azure_no_semantic_keeps_simple_query_type(monkeypatch, tmp_path) -> None:
    """Without semantic_configuration, query_type stays 'simple' (back-compat)."""
    import digisearch.indexes.backends.azure_search as az

    _azure_env(monkeypatch, tmp_path)
    monkeypatch.setattr(az, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(az, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(az, "_AZURE_AVAILABLE", True)

    mock_client = _patched_client()
    with patch.object(az, "_get_client", return_value=mock_client):
        az.query_azure(Query(text="hello", top_k=5), index_name="idx")

    kwargs = mock_client.search.call_args.kwargs
    assert kwargs["query_type"] == "simple"
    assert "semantic_configuration_name" not in kwargs
    assert "speller" not in kwargs


@pytest.mark.unit
def test_azure_speller_only_with_semantic(monkeypatch, tmp_path) -> None:
    """speller='lexicon' is passed iff speller=true AND semantic_configuration is set."""
    import digisearch.indexes.backends.azure_search as az

    # Case 1: speller true + semantic set -> passed.
    _azure_env(monkeypatch, tmp_path, semantic_configuration="sc", speller=True)
    monkeypatch.setattr(az, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(az, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(az, "_AZURE_AVAILABLE", True)

    mock_client = _patched_client()
    with patch.object(az, "_get_client", return_value=mock_client):
        az.query_azure(Query(text="hi", top_k=3), index_name="idx")
    assert mock_client.search.call_args.kwargs.get("speller") == "lexicon"

    # Case 2: speller true but no semantic -> ignored.
    _azure_env(monkeypatch, tmp_path, speller=True)
    mock_client2 = _patched_client()
    with patch.object(az, "_get_client", return_value=mock_client2):
        az.query_azure(Query(text="hi", top_k=3), index_name="idx")
    assert "speller" not in mock_client2.search.call_args.kwargs


@pytest.mark.unit
def test_azure_facets_gated_by_include_facets(monkeypatch, tmp_path) -> None:
    """include_facets=False -> no facets kwarg and response.facets is None, even if config has facets."""
    import digisearch.indexes.backends.azure_search as az

    _azure_env(monkeypatch, tmp_path, facets=["year", "region"])
    monkeypatch.setattr(az, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(az, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(az, "_AZURE_AVAILABLE", True)

    mock_client = _patched_client(facets={"year": [{"value": "2024", "count": 1}]})
    with patch.object(az, "_get_client", return_value=mock_client):
        resp = az.query_azure(Query(text="hi", top_k=3, include_facets=False), index_name="idx")
    assert "facets" not in mock_client.search.call_args.kwargs
    assert resp.facets is None


@pytest.mark.unit
def test_azure_facets_use_config_when_include_facets_and_no_request_facets(
    monkeypatch, tmp_path
) -> None:
    """include_facets=True with no request facets -> falls back to config facets."""
    import digisearch.indexes.backends.azure_search as az

    _azure_env(monkeypatch, tmp_path, facets=["year", "region"])
    monkeypatch.setattr(az, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(az, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(az, "_AZURE_AVAILABLE", True)

    mock_client = _patched_client(
        facets={"year": [{"value": "2024", "count": 5}, {"value": "2023", "count": 2}]},
    )
    with patch.object(az, "_get_client", return_value=mock_client):
        resp = az.query_azure(Query(text="hi", top_k=3, include_facets=True), index_name="idx")

    assert mock_client.search.call_args.kwargs["facets"] == ["year", "region"]
    assert resp.facets is not None
    assert resp.facets["year"][0] == {"value": "2024", "count": 5}


@pytest.mark.unit
def test_azure_request_facets_override_config(monkeypatch, tmp_path) -> None:
    """Request-supplied facets list takes precedence over config facets."""
    import digisearch.indexes.backends.azure_search as az

    _azure_env(monkeypatch, tmp_path, facets=["year"])
    monkeypatch.setattr(az, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(az, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(az, "_AZURE_AVAILABLE", True)

    mock_client = _patched_client(facets={})
    with patch.object(az, "_get_client", return_value=mock_client):
        az.query_azure(
            Query(text="hi", top_k=3, include_facets=True, facets=["region,count:10"]),
            index_name="idx",
        )
    assert mock_client.search.call_args.kwargs["facets"] == ["region,count:10"]
