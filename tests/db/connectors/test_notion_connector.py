"""Unit tests for NotionConnector — all Notion API calls are mocked."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from digibase.connectors.notion import NotionConnector, markdown_to_blocks

pytestmark = pytest.mark.unit


@pytest.fixture()
def mock_notion_client():
    with patch("digibase.connectors.notion.Client") as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        yield mock_instance


@pytest.fixture()
def split_notion_clients():
    """Yield (data_plane_client, admin_client) as two distinct mocks.

    The data-plane client (2022-06-28) is constructed first, the admin client
    (2025-09-03) second — see NotionConnector.__init__.
    """
    data_plane = MagicMock(name="data_plane_2022")
    admin = MagicMock(name="admin_2025")
    with patch("digibase.connectors.notion.Client") as mock_cls:
        mock_cls.side_effect = [data_plane, admin]
        yield mock_cls, data_plane, admin


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


# ── Composite-match upsert (upsert_database_row_matched) ──────────────────────


def test_matched_upsert_creates_with_title_when_no_match(mock_notion_client):
    """No match → create a row; the title property is set from title_value."""
    mock_notion_client.request.return_value = {"results": []}
    mock_notion_client.pages.create.return_value = {"id": "new-event-page"}

    connector = NotionConnector(token="fake-token")
    filter_body = {
        "and": [
            {"property": "Run date", "date": {"equals": "2026-06-07"}},
            {"property": "Event date", "date": {"equals": "2026-06-12"}},
            {"property": "Name", "title": {"equals": "ECB rate decision"}},
        ]
    }
    result = connector.upsert_database_row_matched(
        database_id="db-events",
        filter_body=filter_body,
        title_property="Name",
        title_value="ECB rate decision",
        number_properties={"Mentions": 3.0},
    )

    assert result.success is True
    assert result.external_id == "new-event-page"
    # The find query used the composite filter with page_size=1.
    find_call = mock_notion_client.request.call_args_list[0]
    assert find_call[1]["body"] == {"filter": filter_body, "page_size": 1}
    # The create payload carried the explicit title + the number property.
    create_props = mock_notion_client.pages.create.call_args[1]["properties"]
    assert create_props["Name"] == {"title": [{"text": {"content": "ECB rate decision"}}]}
    assert create_props["Mentions"] == {"number": 3.0}


def test_matched_upsert_updates_existing_without_setting_title(mock_notion_client):
    """A match updates the page and must NOT rewrite the title property."""
    mock_notion_client.request.return_value = {"results": [{"id": "existing-event"}]}

    connector = NotionConnector(token="fake-token")
    result = connector.upsert_database_row_matched(
        database_id="db-events",
        filter_body={"property": "Name", "title": {"equals": "CPI print"}},
        title_property="Name",
        title_value="CPI print",
        checkbox_properties={"Highlighted": True},
    )

    assert result.success is True
    assert result.external_id == "existing-event"
    mock_notion_client.pages.create.assert_not_called()
    update_props = mock_notion_client.pages.update.call_args[1]["properties"]
    assert "Name" not in update_props  # title is only set on create
    assert update_props["Highlighted"] == {"checkbox": True}


def test_matched_upsert_returns_failure_on_api_error(mock_notion_client):
    """Create errors are caught and surfaced as UpsertResult(success=False)."""
    mock_notion_client.request.return_value = {"results": []}
    mock_notion_client.pages.create.side_effect = Exception("conflict")

    connector = NotionConnector(token="fake-token")
    result = connector.upsert_database_row_matched(
        database_id="db-events",
        filter_body={"property": "Name", "title": {"equals": "GDP"}},
        title_property="Name",
        title_value="GDP",
    )

    assert result.success is False
    assert "conflict" in result.error


# ── DB / data-source / view admin (version routing) ───────────────────────────


def test_connector_constructs_both_api_versions(split_notion_clients):
    """Two clients are built: data-plane 2022-06-28 and admin 2025-09-03."""
    mock_cls, _data_plane, _admin = split_notion_clients

    NotionConnector(token="fake-token")

    versions = [c.kwargs["notion_version"] for c in mock_cls.call_args_list]
    assert versions == ["2022-06-28", "2025-09-03"]


def test_admin_methods_use_admin_client_not_data_plane(split_notion_clients):
    """create_database / data_sources / views route through the 2025 admin client."""
    _mock_cls, data_plane, admin = split_notion_clients
    admin.request.return_value = {"id": "db-new", "data_sources": [{"id": "ds-1"}]}

    connector = NotionConnector(token="fake-token")
    db = connector.create_database(
        "parent-page",
        "FX Stances",
        {"Name": {"title": {}}},
        inline=True,
    )

    assert db["id"] == "db-new"
    admin.request.assert_called_once()
    call = admin.request.call_args
    assert call[1]["method"] == "POST"
    assert call[1]["path"] == "databases"
    assert call[1]["body"]["is_inline"] is True
    assert call[1]["body"]["initial_data_source"] == {"properties": {"Name": {"title": {}}}}
    # Database admin must never touch the data-plane (2022-06-28) client.
    data_plane.request.assert_not_called()


def test_primary_data_source_id_reads_first_source(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients
    admin.request.return_value = {"id": "db-x", "data_sources": [{"id": "ds-primary"}]}

    connector = NotionConnector(token="fake-token")
    assert connector.primary_data_source_id("db-x") == "ds-primary"


def test_primary_data_source_id_falls_back_to_database_id(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients
    admin.request.return_value = {"id": "db-x", "data_sources": []}

    connector = NotionConnector(token="fake-token")
    assert connector.primary_data_source_id("db-x") == "db-x"


def test_update_data_source_wraps_properties(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients

    connector = NotionConnector(token="fake-token")
    connector.update_data_source("ds-1", {"Category": {"multi_select": {"options": []}}})

    call = admin.request.call_args
    assert call[1]["method"] == "PATCH"
    assert call[1]["path"] == "data_sources/ds-1"
    assert call[1]["body"] == {"properties": {"Category": {"multi_select": {"options": []}}}}


def test_query_data_source_paginates(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients
    admin.request.side_effect = [
        {"results": [{"id": "r1"}], "has_more": True, "next_cursor": "c2"},
        {"results": [{"id": "r2"}], "has_more": False},
    ]

    connector = NotionConnector(token="fake-token")
    rows = connector.query_data_source("ds-1", filter_body={"property": "X"}, page_size=25)

    assert [r["id"] for r in rows] == ["r1", "r2"]
    first = admin.request.call_args_list[0]
    assert first[1]["path"] == "data_sources/ds-1/query"
    assert first[1]["body"] == {"page_size": 25, "filter": {"property": "X"}}
    second = admin.request.call_args_list[1]
    assert second[1]["body"]["start_cursor"] == "c2"


def test_list_view_ids_returns_empty_on_error(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients
    admin.request.side_effect = Exception("views not on this plan")

    connector = NotionConnector(token="fake-token")
    assert connector.list_view_ids("db-1") == []


def test_view_crud_routes_to_admin_client(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients
    admin.request.return_value = {"id": "v-1"}

    connector = NotionConnector(token="fake-token")
    connector.create_view({"database_id": "db", "data_source_id": "ds", "name": "All"})
    connector.update_view("v-1", {"name": "Renamed"})
    connector.delete_view("v-1")

    methods_paths = [(c[1]["method"], c[1]["path"]) for c in admin.request.call_args_list]
    assert methods_paths == [
        ("POST", "views"),
        ("PATCH", "views/v-1"),
        ("DELETE", "views/v-1"),
    ]


def test_set_page_icon_uses_data_plane_client(split_notion_clients):
    """Page icon (any icon shape) is a 2022-06-28 page update."""
    _mock_cls, data_plane, admin = split_notion_clients

    connector = NotionConnector(token="fake-token")
    connector.set_page_icon("page-1", {"type": "file_upload", "file_upload": {"id": "up-1"}})

    data_plane.pages.update.assert_called_once_with(
        page_id="page-1",
        icon={"type": "file_upload", "file_upload": {"id": "up-1"}},
    )
    admin.request.assert_not_called()


def test_set_page_icon_noop_on_empty(split_notion_clients):
    _mock_cls, data_plane, _admin = split_notion_clients

    connector = NotionConnector(token="fake-token")
    connector.set_page_icon("page-1", {})

    data_plane.pages.update.assert_not_called()


def test_file_upload_primitives_use_admin_client(split_notion_clients):
    _mock_cls, _data_plane, admin = split_notion_clients
    admin.request.side_effect = [
        {"id": "up-1", "upload_url": "https://upload"},
        {"id": "up-1", "status": "uploaded"},
    ]

    connector = NotionConnector(token="fake-token")
    started = connector.create_file_upload("mark.png", "image/png")
    status = connector.get_file_upload("up-1")

    assert started["upload_url"] == "https://upload"
    assert status["status"] == "uploaded"
    create_call = admin.request.call_args_list[0]
    assert create_call[1]["path"] == "file_uploads"
    assert create_call[1]["body"] == {"filename": "mark.png", "content_type": "image/png"}
    get_call = admin.request.call_args_list[1]
    assert get_call[1]["path"] == "file_uploads/up-1"


# ── Public markdown → blocks (merged superset) ────────────────────────────────


def test_markdown_to_blocks_superset_handles_fence_table_and_numbered():
    """One pass proves code fences (mermaid), tables, numbered lists coexist."""
    md = "\n".join(
        [
            "# Title",
            "",
            "## Section",
            "",
            "1. first step",
            "2. second step",
            "",
            "- a bullet with **bold** and [[wikilink]]",
            "",
            "```mermaid",
            "graph TD",
            "A-->B",
            "```",
            "",
            "| Col A | Col B |",
            "| --- | --- |",
            "| v1 | v2 |",
        ]
    )

    blocks = markdown_to_blocks(md)
    types = [b["type"] for b in blocks]

    # H1 retained by default (page bodies keep their title).
    assert types[0] == "heading_1"
    assert "numbered_list_item" in types
    # Code fence → code block carrying the fence language verbatim.
    code = next(b for b in blocks if b["type"] == "code")
    assert code["code"]["language"] == "mermaid"
    assert code["code"]["rich_text"][0]["text"]["content"] == "graph TD\nA-->B"
    # Table: header row → bold paragraph, data row → bullet; separator dropped.
    para = next(b for b in blocks if b["type"] == "paragraph")
    assert para["paragraph"]["rich_text"][0]["annotations"]["bold"] is True
    # Wikilink stripped to plain text inside the bullet.
    bullet = next(
        b
        for b in blocks
        if b["type"] == "bulleted_list_item"
        and any("wikilink" in s["text"]["content"] for s in b["bulleted_list_item"]["rich_text"])
    )
    rendered = "".join(s["text"]["content"] for s in bullet["bulleted_list_item"]["rich_text"])
    assert "[[" not in rendered and "wikilink" in rendered


def test_markdown_to_blocks_skip_title_drops_first_h1():
    md = "# Page Title\n\n## Kept\n\ntext"

    default_blocks = markdown_to_blocks(md)
    skipped_blocks = markdown_to_blocks(md, skip_title=True)

    assert default_blocks[0]["type"] == "heading_1"
    # skip_title drops only the leading H1; the H2 and paragraph remain.
    assert [b["type"] for b in skipped_blocks] == ["heading_2", "paragraph"]


def test_markdown_to_blocks_splits_oversized_rich_text_to_2000():
    """Notion rejects any rich_text element >2000 chars; long content must be SPLIT
    across elements (never truncated), so no body text is silently dropped."""
    long_heading = "H" * 6863           # the real failure mode: an oversized ## line
    long_para = "P" * 4500              # long plain paragraph
    long_code = "C" * 5000              # long fenced code block
    md = "\n".join(
        ["## " + long_heading, "", long_para, "", "```", long_code, "```"]
    )

    blocks = markdown_to_blocks(md)

    def _content(block):
        rt = block[block["type"]]["rich_text"]
        # Every element stays within the hard cap …
        assert all(len(seg["text"]["content"]) <= 2000 for seg in rt)
        # … and concatenating them reproduces the full text (no loss).
        return "".join(seg["text"]["content"] for seg in rt)

    heading = next(b for b in blocks if b["type"] == "heading_2")
    assert _content(heading) == long_heading
    assert len(heading["heading_2"]["rich_text"]) == 4  # ceil(6863/2000)

    para = next(b for b in blocks if b["type"] == "paragraph")
    assert _content(para) == long_para

    code = next(b for b in blocks if b["type"] == "code")
    assert _content(code) == long_code


def test_markdown_to_blocks_splits_preserve_bold_annotation():
    """A long **bold** run is split into multiple elements that all stay bold."""
    md = "**" + ("B" * 4500) + "**"

    para = markdown_to_blocks(md)[0]
    rt = para["paragraph"]["rich_text"]

    assert len(rt) >= 3
    assert all(seg["annotations"]["bold"] is True for seg in rt)
    assert all(len(seg["text"]["content"]) <= 2000 for seg in rt)
    assert "".join(seg["text"]["content"] for seg in rt) == "B" * 4500


def test_write_page_content_uses_public_converter(mock_notion_client):
    """write_page_content still renders bodies (default keeps H1, handles tables)."""
    mock_notion_client.blocks.children.list.return_value = {"results": [], "has_more": False}

    connector = NotionConnector(token="fake-token")
    connector.write_page_content("page-1", "# Brief\n\n| A | B |\n| - | - |\n| 1 | 2 |")

    appended = mock_notion_client.blocks.children.append.call_args[1]["children"]
    types = [b["type"] for b in appended]
    assert types[0] == "heading_1"
    assert "paragraph" in types  # table header
    assert "bulleted_list_item" in types  # table data row
