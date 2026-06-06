"""Unit tests for NotionConnector — all Notion API calls are mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from digibase.connectors.notion import NotionConnector

pytestmark = pytest.mark.unit


@pytest.fixture()
def mock_notion_client():
    with patch("digibase.connectors.notion.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


def test_lazy_import_resolves_notion_connector_class():
    """NotionConnector must lazy-load to the real class, not a None placeholder."""
    import digibase.connectors as connectors

    cls = connectors.NotionConnector
    assert cls is not None
    assert cls.__name__ == "NotionConnector"
    # Cached on module after first access
    assert connectors.NotionConnector is cls


def test_upsert_creates_new_row_when_no_match(mock_notion_client):
    """When no existing row matches, a new page is created."""
    mock_notion_client.request.return_value = {"results": []}
    mock_notion_client.pages.create.return_value = {"id": "new-page-id"}

    connector = NotionConnector(token="fake-token")
    result = connector.upsert_database_row(
        database_id="db-123",
        match_property="Name",
        match_value="Goldman Sachs",
        properties={"USD": "BULLISH — Strong NFP supports dollar"},
    )

    assert result.success is True
    assert result.external_id == "new-page-id"
    mock_notion_client.pages.create.assert_called_once()


def test_upsert_updates_existing_row(mock_notion_client):
    """When an existing row matches, it is updated rather than duplicated."""
    mock_notion_client.request.return_value = {"results": [{"id": "existing-page-id"}]}
    mock_notion_client.pages.update.return_value = {"id": "existing-page-id"}

    connector = NotionConnector(token="fake-token")
    result = connector.upsert_database_row(
        database_id="db-123",
        match_property="Name",
        match_value="Goldman Sachs",
        properties={"USD": "BEARISH — Fed pivot fears"},
    )

    assert result.success is True
    assert result.external_id == "existing-page-id"
    mock_notion_client.pages.update.assert_called_once()
    mock_notion_client.pages.create.assert_not_called()


def test_upsert_sets_last_updated_date(mock_notion_client):
    """Last Updated date field is included in the write payload."""
    mock_notion_client.request.return_value = {"results": []}
    mock_notion_client.pages.create.return_value = {"id": "new-page-id"}

    connector = NotionConnector(token="fake-token")
    connector.upsert_database_row(
        database_id="db-123",
        match_property="Name",
        match_value="Deutsche Bank",
        properties={"EUR": "NEUTRAL — Waiting on ECB"},
        last_updated=date(2026, 6, 4),
    )

    call_kwargs = mock_notion_client.pages.create.call_args[1]
    props = call_kwargs["properties"]
    assert "Last Updated" in props
    assert props["Last Updated"]["date"]["start"] == "2026-06-04"


def test_upsert_returns_failure_on_api_error(mock_notion_client):
    """API errors on create are caught and returned as UpsertResult(success=False)."""
    mock_notion_client.request.return_value = {"results": []}
    mock_notion_client.pages.create.side_effect = Exception("rate limited")

    connector = NotionConnector(token="fake-token")
    result = connector.upsert_database_row(
        database_id="db-123",
        match_property="Name",
        match_value="Citi",
        properties={},
    )

    assert result.success is False
    assert "rate limited" in result.error


def test_query_database_pages_paginates_and_passes_filter(mock_notion_client):
    """query_database_pages follows cursors and includes filter in the request body."""
    mock_notion_client.request.side_effect = [
        {
            "results": [{"id": "page-1"}],
            "has_more": True,
            "next_cursor": "cursor-abc",
        },
        {
            "results": [{"id": "page-2"}],
            "has_more": False,
        },
    ]

    connector = NotionConnector(token="fake-token")
    filter_body = {"property": "Name", "title": {"equals": "ING"}}
    pages = connector.query_database_pages(
        "db-123",
        filter_body=filter_body,
        page_size=50,
    )

    assert [p["id"] for p in pages] == ["page-1", "page-2"]
    first_call = mock_notion_client.request.call_args_list[0]
    assert first_call[1]["body"] == {
        "page_size": 50,
        "filter": filter_body,
    }
    second_call = mock_notion_client.request.call_args_list[1]
    assert second_call[1]["body"]["start_cursor"] == "cursor-abc"
    assert second_call[1]["body"]["filter"] == filter_body


def test_upsert_board_row_writes_currency_cells(mock_notion_client):
    mock_notion_client.request.return_value = {"results": [{"id": "board-page"}]}
    segments = [{"type": "text", "text": {"content": "bullish"}}]

    connector = NotionConnector(token="fake-token")
    result = connector.upsert_board_row(
        database_id="db-board",
        match_property="Name",
        match_value="ING",
        currency_cells={"EUR": segments},
    )

    assert result.success is True
    props = mock_notion_client.pages.update.call_args[1]["properties"]
    assert props["EUR"]["rich_text"] == segments
