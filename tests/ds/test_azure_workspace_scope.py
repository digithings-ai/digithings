"""Azure AI Search workspace isolation (cross-tenant leak regression, #3883).

The Azure backend must never issue an unscoped query when ``Query.workspace_id``
is set. Cover the structured-filter path, the raw-OData branch, and the
fail-closed path when the index cannot filter on ``workspace_id``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import yaml
from digisearch.core.models import Query
from digisearch.core.workspace_filter import merge_workspace_filter
from digisearch.indexes.backends.azure_search import query_azure
from digisearch.indexes.backends.azure_search_errors import AzureWorkspaceFilterError

_T1 = {
    "id": "c1",
    "content": "tenant one doc",
    "doc_id": "d1",
    "workspace_id": "t1",
    "sourceType": "X",
}
_T2 = {
    "id": "c2",
    "content": "tenant two doc",
    "doc_id": "d2",
    "workspace_id": "t2",
    "sourceType": "X",
}


@pytest.fixture
def az(monkeypatch: pytest.MonkeyPatch) -> object:
    import digisearch.indexes.backends.azure_search as mod

    monkeypatch.setattr(mod, "AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setattr(mod, "AZURE_SEARCH_API_KEY", "testkey")
    monkeypatch.setattr(mod, "_AZURE_AVAILABLE", True)
    return mod


def _azure_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
    *,
    filterable: list[str],
    allow_raw_filter: bool = False,
) -> None:
    monkeypatch.setenv("AZURE_SEARCH_ENDPOINT", "https://example.search.windows.net")
    monkeypatch.setenv("AZURE_SEARCH_API_KEY", "testkey")
    cfg = {
        "index_name": "idx",
        "field_mapping": {
            "key_field": "id",
            "content_field": "content",
            "doc_id_field": "doc_id",
        },
        "result_metadata_fields": ["workspace_id", "sourceType"],
        "filterable_fields": filterable,
        "allow_raw_filter": allow_raw_filter,
    }
    cfg_path = tmp_path / "idx.yaml"  # type: ignore[operator]
    cfg_path.write_text(yaml.safe_dump(cfg))
    monkeypatch.setenv("DIGISEARCH_INDEX_CONFIG", str(cfg_path))


def _patched_client(docs: list[dict[str, str]]) -> MagicMock:
    page = MagicMock()
    page.__iter__ = lambda self: iter(docs)
    page.get_facets = MagicMock(return_value=None)
    page.get_count = MagicMock(return_value=len(docs))
    client = MagicMock()
    client.search = MagicMock(return_value=page)
    return client


@pytest.mark.unit
def test_structured_workspace_scoping_drops_other_tenant(az, monkeypatch, tmp_path) -> None:
    _azure_env(monkeypatch, tmp_path, filterable=["workspace_id", "sourceType"])
    client = _patched_client([_T1, _T2])
    with patch.object(az, "_get_client", return_value=client):
        resp = query_azure(
            Query(
                text="tenant",
                top_k=10,
                workspace_id="t1",
                filters=merge_workspace_filter({}, "t1"),
            ),
            index_name="idx",
        )

    filt = client.search.call_args.kwargs.get("filter")
    assert filt is not None and "workspace_id eq 't1'" in filt
    assert [r.chunk.id for r in resp.results] == ["c1"]
    assert "workspace_id" in client.search.call_args.kwargs["select"]


@pytest.mark.unit
def test_raw_filter_still_applies_workspace_scoping(az, monkeypatch, tmp_path) -> None:
    _azure_env(
        monkeypatch,
        tmp_path,
        filterable=["workspace_id", "sourceType"],
        allow_raw_filter=True,
    )
    client = _patched_client([_T1, _T2])
    with patch.object(az, "_get_client", return_value=client):
        resp = query_azure(
            Query(
                text="tenant",
                top_k=10,
                workspace_id="t1",
                filters={
                    "odata": "sourceType eq 'X'",
                    "structured": [{"field": "workspace_id", "op": "eq", "value": "t1"}],
                },
            ),
            index_name="idx",
        )

    filt = client.search.call_args.kwargs["filter"]
    assert "sourceType eq 'X'" in filt
    assert "workspace_id eq 't1'" in filt
    assert [r.chunk.id for r in resp.results] == ["c1"]


@pytest.mark.unit
def test_fails_closed_when_workspace_not_filterable(az, monkeypatch, tmp_path) -> None:
    _azure_env(monkeypatch, tmp_path, filterable=["sourceType"])
    client = _patched_client([_T1, _T2])
    with patch.object(az, "_get_client", return_value=client):
        with pytest.raises(AzureWorkspaceFilterError):
            query_azure(
                Query(
                    text="tenant",
                    top_k=10,
                    workspace_id="t1",
                    filters=merge_workspace_filter({}, "t1"),
                ),
                index_name="idx",
            )
    client.search.assert_not_called()


@pytest.mark.unit
def test_no_workspace_leaves_query_unscoped(az, monkeypatch, tmp_path) -> None:
    _azure_env(monkeypatch, tmp_path, filterable=["workspace_id"])
    client = _patched_client([_T1, _T2])
    with patch.object(az, "_get_client", return_value=client):
        resp = query_azure(Query(text="tenant", top_k=10), index_name="idx")

    assert "filter" not in client.search.call_args.kwargs
    assert [r.chunk.id for r in resp.results] == ["c1", "c2"]


@pytest.mark.unit
def test_workspace_filter_error_propagates_through_query_index(az, monkeypatch, tmp_path) -> None:
    """The fail-closed error must not be swallowed and fall through to Chroma."""
    from digisearch.search import _stub

    _azure_env(monkeypatch, tmp_path, filterable=["sourceType"])
    client = _patched_client([_T1])
    with patch.object(az, "_get_client", return_value=client):
        with pytest.raises(AzureWorkspaceFilterError):
            _stub.query_index(
                Query(
                    text="tenant",
                    top_k=10,
                    workspace_id="t1",
                    filters=merge_workspace_filter({}, "t1"),
                ),
                index_name="idx",
            )


@pytest.mark.unit
def test_structured_only_workspace_clause_is_not_dropped(az, monkeypatch, tmp_path) -> None:
    """A structured workspace_id filter with no Query.workspace_id must still scope.

    Reachable via POST /query and the MCP ``filters`` path, which never set
    ``workspace_id``; the clause must not be stripped and silently lost.
    """
    _azure_env(monkeypatch, tmp_path, filterable=["workspace_id", "sourceType"])
    client = _patched_client([_T1, _T2])
    with patch.object(az, "_get_client", return_value=client):
        resp = query_azure(
            Query(
                text="tenant",
                top_k=10,
                workspace_id=None,
                filters={"structured": [{"field": "workspace_id", "op": "eq", "value": "t1"}]},
            ),
            index_name="idx",
        )

    filt = client.search.call_args.kwargs.get("filter")
    assert filt == "(workspace_id eq 't1')"
    assert [r.chunk.id for r in resp.results] == ["c1"]


@pytest.mark.unit
def test_structured_only_workspace_clause_fails_closed_when_not_filterable(
    az, monkeypatch, tmp_path
) -> None:
    """Structured-only workspace scoping must not silently degrade to unscoped."""
    _azure_env(monkeypatch, tmp_path, filterable=["sourceType"])
    client = _patched_client([_T1, _T2])
    with patch.object(az, "_get_client", return_value=client):
        with pytest.raises(AzureWorkspaceFilterError):
            query_azure(
                Query(
                    text="tenant",
                    top_k=10,
                    workspace_id=None,
                    filters={"structured": [{"field": "workspace_id", "op": "eq", "value": "t1"}]},
                ),
                index_name="idx",
            )
    client.search.assert_not_called()
