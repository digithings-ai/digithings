"""Notion connector — thin wrapper around notion-client for database upserts.

Works with notion-client 2.2+. Database queries go through a direct POST to
/v1/databases/{id}/query via client.request() rather than databases.query(),
so the same code path holds across client minor versions.

The connector pins ``Notion-Version: 2022-06-28`` because later API versions
changed the databases/query endpoint shape (newer clients default to a version
where that endpoint returns InvalidRequestURL).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any  # noqa: PYI041

from notion_client import Client

logger = logging.getLogger(__name__)


@dataclass
class UpsertResult:
    success: bool
    external_id: str = ""
    error: str = ""


@dataclass(frozen=True)
class DigestGuideItem:
    """A single cross-link target surfaced in the hub digest."""

    label: str
    page_id: str = ""


@dataclass(frozen=True)
class DigestGuideSection:
    """Grouped page mentions under a hub section (events, briefs, consensus)."""

    title: str
    emoji: str
    items: list[DigestGuideItem]


class NotionConnector:
    """Notion connector for database row upserts with page body writing.

    Two pinned clients are held internally because Notion split its admin and
    data-plane endpoints across API versions:

    * ``_client`` (``Notion-Version: 2022-06-28``) — page/block reads and
      writes plus the legacy ``databases/{id}/query`` endpoint. Later versions
      changed that endpoint shape (newer clients return ``InvalidRequestURL``),
      so this client stays pinned for every row upsert and block operation.
    * ``_admin_client`` (``Notion-Version: 2025-09-03``) — the data-sources
      API. ``databases`` creation with ``initial_data_source``, the
      ``data_sources/*`` endpoints, and the ``views/*`` endpoints only exist on
      this version. The DB / data-source / view admin methods use it.

    Callers never construct ``notion_client.Client`` for database,
    data-source, view, or page-icon management — the admin primitives below
    cover those on the correct version. Free-form page/block *layout*
    orchestration (listing/appending/deleting child blocks, creating
    sub-pages) is out of scope for this connector; consumers that need it
    still drive those endpoints themselves.
    """

    # notion-client v3 defaults to Notion-Version 2025-09-03 where the
    # databases/query endpoint returns InvalidRequestURL. Pin to the last
    # stable version where the endpoint works correctly.
    _NOTION_VERSION = "2022-06-28"

    # Data-sources API version. databases-create (with initial_data_source),
    # data_sources/*, and views/* endpoints only exist here.
    _ADMIN_NOTION_VERSION = "2025-09-03"

    def __init__(self, token: str) -> None:
        self._client = Client(auth=token, notion_version=self._NOTION_VERSION)
        self._admin_client = Client(auth=token, notion_version=self._ADMIN_NOTION_VERSION)

    def upsert_database_row(
        self,
        database_id: str,
        match_property: str,
        match_value: str,
        properties: dict[str, Any],
        url_properties: dict[str, str] | None = None,
        date_properties: dict[str, date] | None = None,
        select_properties: dict[str, str] | None = None,
        multi_select_properties: dict[str, list[str]] | None = None,
        number_properties: dict[str, float] | None = None,
        rich_text_properties: dict[str, list[dict[str, Any]]] | None = None,
        checkbox_properties: dict[str, bool] | None = None,
        last_updated: date | None = None,
    ) -> UpsertResult:
        """Upsert a database row matched by a title property value.

        Args:
            database_id:     Notion database ID.
            match_property:  Name of the title property used to find existing rows.
            match_value:     Value to match against (e.g. broker name).
            properties:      Dict of property_name → string value (written as rich_text).
            url_properties:  Dict of property_name → URL string (written as url type).
            date_properties: Dict of property_name → date (written as date type).
            last_updated:    Shorthand — writes date to "Last Updated" property.

        Returns:
            UpsertResult with success flag, page ID, and any error message.
        """
        try:
            page_id = self._find_page(database_id, match_property, match_value)
            notion_props = self._build_properties(
                properties,
                url_properties,
                date_properties,
                select_properties,
                multi_select_properties,
                number_properties,
                rich_text_properties,
                checkbox_properties,
                last_updated,
            )

            if page_id:
                self._client.pages.update(page_id=page_id, properties=notion_props)
                logger.debug("notion: updated page %s (%s)", page_id, match_value)
            else:
                notion_props[match_property] = {"title": [{"text": {"content": match_value}}]}
                result = self._client.pages.create(
                    parent={"database_id": database_id},
                    properties=notion_props,
                )
                page_id = result["id"]
                logger.debug("notion: created page %s (%s)", page_id, match_value)

            return UpsertResult(success=True, external_id=page_id)

        except Exception as exc:
            logger.error("notion: upsert failed for %s: %s", match_value, exc)
            return UpsertResult(success=False, error=str(exc))

    def upsert_database_row_matched(
        self,
        database_id: str,
        *,
        filter_body: dict[str, Any],
        title_property: str,
        title_value: str,
        properties: dict[str, Any] | None = None,
        url_properties: dict[str, str] | None = None,
        date_properties: dict[str, date] | None = None,
        select_properties: dict[str, str] | None = None,
        multi_select_properties: dict[str, list[str]] | None = None,
        number_properties: dict[str, float] | None = None,
        rich_text_properties: dict[str, list[dict[str, Any]]] | None = None,
        checkbox_properties: dict[str, bool] | None = None,
        last_updated: date | None = None,
    ) -> UpsertResult:
        """Upsert a database row matched by a caller-supplied filter.

        Like :meth:`upsert_database_row`, but the existing row is located with
        an arbitrary Notion ``filter_body`` (e.g. a composite
        ``{"and": [...]}`` matching run-date + event-date + name) instead of a
        title-equals lookup. On create the title is still required, so the
        title property is set explicitly from ``title_property`` /
        ``title_value``.

        Args:
            database_id:    Notion database ID.
            filter_body:    Notion query filter used to find an existing row.
                            The first matching row is updated; if none match a
                            new row is created.
            title_property: Name of the title property (set on create).
            title_value:    Title value written on create.
            properties:     property_name → string value (written as rich_text).
            (remaining):    Same typed property maps as ``upsert_database_row``.

        Returns:
            UpsertResult with success flag, page ID, and any error message.
        """
        try:
            page_id = self._find_page_by_filter(database_id, filter_body)
            notion_props = self._build_properties(
                properties or {},
                url_properties,
                date_properties,
                select_properties,
                multi_select_properties,
                number_properties,
                rich_text_properties,
                checkbox_properties,
                last_updated,
            )

            if page_id:
                self._client.pages.update(page_id=page_id, properties=notion_props)
                logger.debug("notion: updated page %s (%s)", page_id, title_value)
            else:
                notion_props[title_property] = {"title": [{"text": {"content": title_value}}]}
                result = self._client.pages.create(
                    parent={"database_id": database_id},
                    properties=notion_props,
                )
                page_id = result["id"]
                logger.debug("notion: created page %s (%s)", page_id, title_value)

            return UpsertResult(success=True, external_id=page_id)

        except Exception as exc:
            logger.error("notion: matched upsert failed for %s: %s", title_value, exc)
            return UpsertResult(success=False, error=str(exc))

    def upsert_board_row(
        self,
        database_id: str,
        match_property: str,
        match_value: str,
        currency_cells: dict[str, list[dict]],
    ) -> UpsertResult:
        """Upsert a broker summary row on the Research Files board.

        Each value in currency_cells is a list of Notion rich_text segment dicts,
        supporting multiple linked entries per cell (one per brief).
        Schema: Name + G10 currency columns only.
        """
        try:
            page_id = self._find_page(database_id, match_property, match_value)
            notion_props: dict[str, Any] = {
                currency: {"rich_text": segments} for currency, segments in currency_cells.items()
            }

            if page_id:
                self._client.pages.update(page_id=page_id, properties=notion_props)
            else:
                notion_props[match_property] = {"title": [{"text": {"content": match_value}}]}
                result = self._client.pages.create(
                    parent={"database_id": database_id},
                    properties=notion_props,
                )
                page_id = result["id"]

            return UpsertResult(success=True, external_id=page_id)

        except Exception as exc:
            logger.error("notion: board row upsert failed for %s: %s", match_value, exc)
            return UpsertResult(success=False, error=str(exc))

    def update_page_icon(self, page_id: str, emoji: str) -> None:
        """Set a page icon from a single emoji character."""
        if not emoji:
            return
        self._client.pages.update(page_id=page_id, icon={"type": "emoji", "emoji": emoji})

    def archive_page(self, page_id: str) -> None:
        """Archive (soft-delete) a Notion page."""
        self._client.pages.update(page_id=page_id, archived=True)

    def set_page_icon(self, page_id: str, icon: dict[str, Any]) -> None:
        """Set a page icon from a raw Notion icon object.

        Accepts any Notion icon shape, e.g. ``{"type": "emoji", "emoji": "🏦"}``,
        ``{"type": "external", "external": {"url": ...}}``, or
        ``{"type": "file_upload", "file_upload": {"id": ...}}``. For the common
        emoji-only case prefer :meth:`update_page_icon`.
        """
        if not icon:
            return
        self._client.pages.update(page_id=page_id, icon=icon)

    # ── DB / data-source / view admin (Notion-Version 2025-09-03) ─────────────
    #
    # These methods drive the data-sources API and therefore use the admin
    # client. They are thin wrappers over the corresponding REST endpoints;
    # layout/orchestration logic stays with the caller.

    def create_database(
        self,
        parent_page_id: str,
        title: str,
        properties: dict[str, Any],
        *,
        inline: bool = False,
    ) -> dict[str, Any]:
        """Create a database under a page with an initial data source.

        Returns the raw Notion database object. Use
        :meth:`primary_data_source_id` to resolve its data-source id.
        """
        return self._admin_client.request(
            method="POST",
            path="databases",
            body={
                "parent": {"type": "page_id", "page_id": parent_page_id},
                "title": [{"type": "text", "text": {"content": title}}],
                "is_inline": inline,
                "initial_data_source": {"properties": properties},
            },
        )

    def get_database(self, database_id: str) -> dict[str, Any]:
        """Retrieve a database object (data-sources API)."""
        return self._admin_client.request(method="GET", path=f"databases/{database_id}")

    def update_database(self, database_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Patch a database. Covers title, ``is_inline``, ``archived``, and parent moves."""
        return self._admin_client.request(
            method="PATCH", path=f"databases/{database_id}", body=body
        )

    def primary_data_source_id(self, database_id: str) -> str:
        """Return the first data-source id of a database, falling back to its id."""
        db = self.get_database(database_id)
        sources = db.get("data_sources") or []
        if sources:
            return sources[0]["id"]
        return database_id

    def get_data_source(self, data_source_id: str) -> dict[str, Any]:
        """Retrieve a data-source object (includes its ``properties`` schema)."""
        return self._admin_client.request(method="GET", path=f"data_sources/{data_source_id}")

    def update_data_source(self, data_source_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        """Patch a data-source schema with a ``properties`` map (add/migrate columns)."""
        return self._admin_client.request(
            method="PATCH",
            path=f"data_sources/{data_source_id}",
            body={"properties": properties},
        )

    def query_data_source(
        self,
        data_source_id: str,
        *,
        filter_body: dict[str, Any] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Query rows via the data-sources ``data_sources/{id}/query`` endpoint.

        This is the 2025-09-03 counterpart to :meth:`query_database_pages`
        (which uses the legacy ``databases/{id}/query`` path). Paginates.
        """
        body: dict[str, Any] = {"page_size": page_size}
        if filter_body:
            body["filter"] = filter_body
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            request_body = dict(body)
            if cursor:
                request_body["start_cursor"] = cursor
            response = self._admin_client.request(
                method="POST",
                path=f"data_sources/{data_source_id}/query",
                body=request_body,
            )
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return results

    def list_view_ids(self, database_id: str) -> list[str]:
        """Return the view ids for a database (empty list if views are unavailable)."""
        try:
            response = self._admin_client.request(
                method="GET", path=f"views?database_id={database_id}"
            )
        except Exception as exc:
            logger.warning("notion: views unavailable for %s: %s", database_id, exc)
            return []
        return [v["id"] for v in response.get("results", [])]

    def get_view(self, view_id: str) -> dict[str, Any] | None:
        """Retrieve a single view object, or None if it cannot be read."""
        try:
            return self._admin_client.request(method="GET", path=f"views/{view_id}")
        except Exception:
            return None

    def create_view(self, body: dict[str, Any]) -> dict[str, Any]:
        """Create a view. ``body`` must include ``database_id`` and ``data_source_id``."""
        return self._admin_client.request(method="POST", path="views", body=body)

    def update_view(self, view_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Patch a view (filter, sorts, configuration, visible_properties, name)."""
        return self._admin_client.request(method="PATCH", path=f"views/{view_id}", body=body)

    def delete_view(self, view_id: str) -> None:
        """Delete a view."""
        self._admin_client.request(method="DELETE", path=f"views/{view_id}")

    def create_file_upload(self, filename: str, content_type: str) -> dict[str, Any]:
        """Start a Notion file upload; returns the upload object with ``upload_url``.

        The caller streams the file bytes to ``upload_url`` (a plain multipart
        POST, not a notion-client call), then polls :meth:`get_file_upload`
        until status is ``"uploaded"`` before referencing the upload id (e.g.
        via :meth:`set_page_icon` with a ``file_upload`` icon).
        """
        return self._admin_client.request(
            method="POST",
            path="file_uploads",
            body={"filename": filename, "content_type": content_type},
        )

    def get_file_upload(self, file_upload_id: str) -> dict[str, Any]:
        """Retrieve a file-upload object (poll its ``status`` until ``uploaded``)."""
        return self._admin_client.request(method="GET", path=f"file_uploads/{file_upload_id}")

    def query_database_pages(
        self,
        database_id: str,
        *,
        filter_body: dict[str, Any] | None = None,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        """Query database rows via the legacy databases/query endpoint."""
        body: dict[str, Any] = {"page_size": page_size}
        if filter_body:
            body["filter"] = filter_body
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            request_body = dict(body)
            if cursor:
                request_body["start_cursor"] = cursor
            response = self._client.request(
                method="POST",
                path=f"databases/{database_id}/query",
                body=request_body,
            )
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return results

    def write_page_content(self, page_id: str, markdown: str) -> None:
        """Replace the body of a Notion page with content converted from markdown.

        Clears existing blocks first, then appends new ones. Handles the main
        structural elements in our brief format: headings, bullets, tables,
        bold-prefixed paragraphs, and plain paragraphs.
        """
        # Clear existing content (paginate — list() only returns the first page).
        for block in self._list_child_blocks(page_id):
            try:
                self._client.blocks.delete(block_id=block["id"])
            except Exception:
                pass  # already deleted or not deletable

        blocks = markdown_to_blocks(markdown)
        if not blocks:
            return

        # Notion limits children.append to 100 blocks per call
        for i in range(0, len(blocks), 100):
            self._client.blocks.children.append(
                block_id=page_id,
                children=blocks[i : i + 100],
            )

    def sync_hub_last_updated(
        self,
        page_id: str,
        run_date: str,
        updated_at: datetime | None = None,
    ) -> None:
        """Show a last-updated callout at the very top of the hub page."""
        stamp = updated_at or datetime.now(timezone.utc)
        label = _format_last_updated(run_date, stamp)
        blocks = self._list_child_blocks(page_id)
        marker_idx = _last_updated_index(blocks)

        callout_block = {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": _plain_rich_text(label),
                "icon": {"type": "emoji", "emoji": "🕐"},
            },
        }

        if marker_idx is not None:
            block_id = blocks[marker_idx]["id"]
            if marker_idx == 0:
                self._client.blocks.update(
                    block_id=block_id,
                    callout=callout_block["callout"],
                )
                return
            try:
                self._client.blocks.delete(block_id=block_id)
            except Exception as exc:
                # Best-effort cleanup of the prior callout — a stale block is
                # cosmetic, so don't fail the hub update on a delete error.
                logger.debug(
                    "set_hub_last_updated: stale callout delete failed (%s): %s", block_id, exc
                )

        self._prepend_child_block(page_id, callout_block)

    def sync_hub_digest(
        self,
        page_id: str,
        run_date: str,
        summary: str,
        key_themes: list[str] | None = None,
        *,
        consensus_take: str = "",
        street_take: str = "",
        guide_sections: list[DigestGuideSection] | None = None,
        doc_count: int = 0,
        broker_count: int = 0,
        updated_at: datetime | None = None,
        digest_heading: str = "Digest",
        matrix_heading: str = "Research Matrix",
    ) -> None:
        """Refresh the digest section on the Atlas hub page (between two headings).

        Expects ``## Digest`` above the inline Research Matrix embed. Replaces
        every block between those markers on each run. Also updates the
        last-updated callout pinned to the top of the page.

        Layout: blue callout title + quote paragraphs + guide-link bullets.
        Notion's children.append rejects nested children on callout/quote blocks —
        use sibling blocks (quote paragraphs read as one indented summary).
        """
        self.sync_hub_last_updated(page_id, run_date, updated_at=updated_at)

        blocks = self._list_child_blocks(page_id)
        digest_idx = _heading_index(blocks, digest_heading)
        if digest_idx is None:
            digest_idx = _heading_index(blocks, "Daily Digest")
        matrix_idx = _heading_index(blocks, matrix_heading)
        if matrix_idx is None:
            matrix_idx = _child_database_index(blocks, matrix_heading)
        if matrix_idx is None:
            matrix_idx = _child_database_index(blocks, "Broker Research Matrix")
        if matrix_idx is None:
            matrix_idx = _first_child_database_index(blocks)
        if digest_idx is None:
            logger.warning("notion: hub page missing %r heading — skip digest sync", digest_heading)
            return
        if matrix_idx is None:
            logger.warning("notion: hub page missing %r section — skip digest sync", matrix_heading)
            return

        # Only remove digest body blocks — never inline database embeds (matrix, events).
        delete_end = matrix_idx
        for idx in range(digest_idx + 1, len(blocks)):
            if blocks[idx].get("type") == "child_database":
                delete_end = idx
                break
        for block in blocks[digest_idx + 1 : delete_end]:
            if block.get("type") == "child_database":
                continue
            try:
                self._client.blocks.delete(block_id=block["id"])
            except Exception as exc:
                # Best-effort: leaving an old digest block is tolerable, so a
                # delete failure must not abort the digest re-sync.
                logger.debug(
                    "sync_hub_digest: old block delete failed (%s): %s", block.get("id"), exc
                )

        take = consensus_take or street_take
        children = _digest_body_blocks(
            run_date,
            summary,
            key_themes or [],
            consensus_take=take,
            guide_sections=guide_sections,
            doc_count=doc_count,
            broker_count=broker_count,
        )
        self._client.blocks.children.append(
            block_id=page_id,
            children=children,
            after=blocks[digest_idx]["id"],
        )

    def ensure_hub_section_heading(
        self,
        page_id: str,
        heading: str,
        *,
        before_heading: str | None = None,
        level: int = 2,
    ) -> None:
        """Insert a section heading if missing, optionally before another heading."""
        blocks = self._list_child_blocks(page_id)
        if _heading_index(blocks, heading) is not None:
            return
        heading_type = f"heading_{level}"
        child = {
            "object": "block",
            "type": heading_type,
            heading_type: {"rich_text": [{"type": "text", "text": {"content": heading}}]},
        }
        if before_heading:
            before_idx = _heading_index(blocks, before_heading)
            if before_idx is not None and before_idx > 0:
                self._client.blocks.children.append(
                    block_id=page_id,
                    children=[child],
                    after=blocks[before_idx - 1]["id"],
                )
                return
        self._client.blocks.children.append(block_id=page_id, children=[child])

    # ── Private helpers ───────────────────────────────────────────────────────

    def _prepend_child_block(self, page_id: str, child: dict[str, Any]) -> None:
        """Insert a block as early as the API allows (no true prepend — insert-after first)."""
        blocks = self._list_child_blocks(page_id)
        if not blocks:
            self._client.blocks.children.append(block_id=page_id, children=[child])
            return
        self._client.blocks.children.append(
            block_id=page_id,
            children=[child],
            after=blocks[0]["id"],
        )

    def _list_child_blocks(self, page_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            kwargs: dict[str, Any] = {"block_id": page_id}
            if cursor:
                kwargs["start_cursor"] = cursor
            response = self._client.blocks.children.list(**kwargs)
            results.extend(response.get("results", []))
            if not response.get("has_more"):
                break
            cursor = response.get("next_cursor")
        return results

    def _find_page(self, database_id: str, property_name: str, value: str) -> str | None:
        """Return the page ID of the first matching row, or None."""
        try:
            response = self._client.request(
                method="POST",
                path=f"databases/{database_id}/query",
                body={
                    "filter": {
                        "property": property_name,
                        "title": {"equals": value},
                    },
                    "page_size": 1,
                },
            )
            results = response.get("results", [])
            return results[0]["id"] if results else None
        except Exception as exc:
            logger.warning("notion: query failed for %s=%s: %s", property_name, value, exc)
            return None

    def _find_page_by_filter(self, database_id: str, filter_body: dict[str, Any]) -> str | None:
        """Return the page ID of the first row matching ``filter_body``, or None."""
        try:
            response = self._client.request(
                method="POST",
                path=f"databases/{database_id}/query",
                body={"filter": filter_body, "page_size": 1},
            )
            results = response.get("results", [])
            return results[0]["id"] if results else None
        except Exception as exc:
            logger.warning("notion: filtered query failed on %s: %s", database_id, exc)
            return None

    def _build_properties(
        self,
        properties: dict[str, Any],
        url_properties: dict[str, str] | None,
        date_properties: dict[str, date] | None,
        select_properties: dict[str, str] | None,
        multi_select_properties: dict[str, list[str]] | None,
        number_properties: dict[str, float] | None,
        rich_text_properties: dict[str, list[dict[str, Any]]] | None = None,
        checkbox_properties: dict[str, bool] | None = None,
        last_updated: date | None = None,
    ) -> dict[str, Any]:
        """Convert flat dicts to Notion property format."""
        notion_props: dict[str, Any] = {}

        for name, value in properties.items():
            if not value:
                continue
            notion_props[name] = {"rich_text": [{"text": {"content": str(value)[:2000]}}]}

        for name, segments in (rich_text_properties or {}).items():
            if segments:
                notion_props[name] = {"rich_text": segments}

        for name, checked in (checkbox_properties or {}).items():
            notion_props[name] = {"checkbox": bool(checked)}

        for name, url in (url_properties or {}).items():
            if url:
                notion_props[name] = {"url": url}

        for name, d in (date_properties or {}).items():
            if d:
                notion_props[name] = {"date": {"start": d.isoformat()}}

        for name, option in (select_properties or {}).items():
            if option:
                notion_props[name] = {"select": {"name": option}}

        for name, options in (multi_select_properties or {}).items():
            if options:
                notion_props[name] = {
                    "multi_select": [{"name": opt} for opt in options if opt],
                }

        for name, value in (number_properties or {}).items():
            if value is not None:
                notion_props[name] = {"number": float(value)}

        if last_updated:
            notion_props["Last Updated"] = {"date": {"start": last_updated.isoformat()}}

        return notion_props


# ── Markdown → Notion blocks ──────────────────────────────────────────────────


def _heading_index(blocks: list[dict[str, Any]], title: str) -> int | None:
    """Return the index of the first heading block whose text contains ``title``."""
    for idx, block in enumerate(blocks):
        block_type = block.get("type", "")
        if not block_type.startswith("heading"):
            continue
        rich = block.get(block_type, {}).get("rich_text", [])
        text = "".join(part.get("plain_text", "") for part in rich)
        if title.lower() in text.lower():
            return idx
    return None


def _child_database_index(blocks: list[dict[str, Any]], title: str) -> int | None:
    """Return the index of a linked/inline database block matching ``title``."""
    for idx, block in enumerate(blocks):
        if block.get("type") != "child_database":
            continue
        rich = block.get("child_database", {}).get("title", [])
        if isinstance(rich, str):
            text = rich
        else:
            text = "".join(part.get("plain_text", "") for part in rich)
        if title.lower() in text.lower():
            return idx
    return None


def _first_child_database_index(blocks: list[dict[str, Any]]) -> int | None:
    """Return the index of the first inline database block on the page."""
    for idx, block in enumerate(blocks):
        if block.get("type") == "child_database":
            return idx
    return None


def _last_updated_index(blocks: list[dict[str, Any]]) -> int | None:
    """Return the index of the hub last-updated callout, if present."""
    for idx, block in enumerate(blocks):
        if block.get("type") != "callout":
            continue
        text = _block_plain_text(block)
        if text.startswith("Last updated:"):
            return idx
    return None


def _block_plain_text(block: dict[str, Any]) -> str:
    block_type = block.get("type", "")
    rich = block.get(block_type, {}).get("rich_text", [])
    return "".join(part.get("plain_text", "") for part in rich)


def _plain_rich_text(text: str) -> list[dict[str, Any]]:
    return [{"type": "text", "text": {"content": text}}]


def _format_last_updated(run_date: str, updated_at: datetime) -> str:
    try:
        parsed = date.fromisoformat(run_date)
        run_label = f"{parsed.day} {parsed.strftime('%b %Y')}"
    except ValueError:
        run_label = run_date
    time_label = updated_at.astimezone(timezone.utc).strftime("%H:%M UTC")
    return f"Last updated: {run_label} · run {run_date} · {time_label}"


def _page_mention_segment(page_id: str, label: str) -> dict:
    """Rich-text segment linking to another Notion page with custom display text."""
    page_slug = page_id.replace("-", "")
    return {
        "type": "text",
        "text": {
            "content": label,
            "link": {"url": f"https://www.notion.so/{page_slug}"},
        },
    }


def _paragraph_rich(segments: list[dict]) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": segments}}


def _bullet_rich(segments: list[dict]) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": segments},
    }


def _quote(text: str) -> dict:
    """Quote block — narrative digest lines (no nested children; Notion rejects them on append)."""
    return {"object": "block", "type": "quote", "quote": {"rich_text": _rich_text(text)}}


def _guide_link_bullet(section: DigestGuideSection) -> dict:
    """One bulleted row of page mentions for a hub section."""
    prefix = f"{section.emoji} {section.title}: "
    segments: list[dict] = [
        {"type": "text", "text": {"content": prefix}, "annotations": {"bold": True}},
    ]
    for idx, item in enumerate(section.items):
        if idx:
            segments.append({"type": "text", "text": {"content": " · "}})
        if item.page_id:
            segments.append(_page_mention_segment(item.page_id, item.label))
        else:
            segments.append({"type": "text", "text": {"content": item.label}})
    return _bullet_rich(segments)


def _digest_body_blocks(
    run_date: str,
    summary: str,
    key_themes: list[str],
    *,
    consensus_take: str = "",
    street_take: str = "",
    guide_sections: list[DigestGuideSection] | None = None,
    doc_count: int = 0,
    broker_count: int = 0,
) -> list[dict]:
    """Body blocks written under the Digest heading on the hub page.

    Returns a blue callout title strip, then quote paragraphs (indented summary)
    and bulleted guide links. Notion cannot nest blocks inside callout/quote on
    children.append — consecutive quote blocks render as one visual summary.
    """
    body: list[dict] = [
        {
            "object": "block",
            "type": "callout",
            "callout": {
                "rich_text": [
                    {
                        "type": "text",
                        "text": {"content": f"Atlas Daily Digest — {run_date}"},
                        "annotations": {"bold": True},
                    }
                ],
                "icon": {"type": "emoji", "emoji": "📋"},
                "color": "blue_background",
            },
        },
    ]

    if doc_count:
        body.append(
            _quote(
                f"**{broker_count} brokers · {doc_count} briefs** — "
                "synthesised from today's broker research."
            )
        )

    body.append(_quote(f"**Today's focus.** {summary.strip()}"))

    take = consensus_take or street_take
    if take:
        body.append(_quote(f"**Consensus read.** {take.strip()}"))

    if key_themes:
        body.append(_quote("**Key themes**"))
        body.extend(_bullet(theme) for theme in key_themes)

    sections = [s for s in (guide_sections or []) if s.items]
    if sections:
        body.append(
            _quote("**What to read next** — follow the links to content below on this page.")
        )
        body.extend(_guide_link_bullet(section) for section in sections)

    return body


def _rich_text(text: str) -> list[dict]:
    """Convert a plain text string with **bold** markers to Notion rich_text."""
    # Strip [[wikilinks]] to plain text
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    parts: list[dict] = []
    # Split on **...** bold markers
    segments = re.split(r"\*\*(.+?)\*\*", text)
    for i, seg in enumerate(segments):
        if not seg:
            continue
        parts.append(
            {
                "type": "text",
                "text": {"content": seg},
                "annotations": {"bold": i % 2 == 1},
            }
        )
    return parts or [{"type": "text", "text": {"content": ""}}]


def _paragraph(text: str) -> dict:
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": _rich_text(text)}}


def _heading(text: str, level: int) -> dict:
    t = f"heading_{level}"
    clean = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return {
        "object": "block",
        "type": t,
        t: {"rich_text": [{"type": "text", "text": {"content": clean}}]},
    }


def _bullet(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": _rich_text(text)},
    }


def _numbered(text: str) -> dict:
    return {
        "object": "block",
        "type": "numbered_list_item",
        "numbered_list_item": {"rich_text": _rich_text(text)},
    }


def _code_block(content: str, language: str) -> dict:
    lang = language.strip().lower() or "plain text"
    return {
        "object": "block",
        "type": "code",
        "code": {
            "rich_text": [{"type": "text", "text": {"content": content}}],
            "language": lang,
        },
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def markdown_to_blocks(md: str, *, skip_title: bool = False) -> list[dict]:
    """Convert markdown to Notion blocks.

    Merged superset of the brief-format and documentation-page converters. It
    handles:

    * ``#`` / ``##`` / ``###`` headings,
    * ``-`` / ``*`` bullets and ``1.`` numbered list items,
    * ```` ``` ```` fenced code blocks (the fence info string becomes the
      Notion code ``language``, so ```` ```mermaid ```` renders as a mermaid
      diagram),
    * ``|`` pipe tables (header row → bold paragraph, data rows → bullets),
    * ``---`` dividers,
    * ``**bold**`` inline markers and ``[[wikilinks]]`` (stripped to plain text),
    * plain paragraphs.

    Tables are flattened to paragraph/bullet rows — Notion table blocks are
    complex and readable rows are sufficient for our content.

    Args:
        md:         Markdown source.
        skip_title: When True, the first top-level ``# `` heading is dropped
                    (documentation pages already carry the title as the page
                    title). Defaults to False so page bodies keep their H1.
    """
    blocks: list[dict] = []
    in_table = False
    in_fence = False
    fence_lang = ""
    fence_lines: list[str] = []
    skipped_title = False

    def flush_fence() -> None:
        nonlocal fence_lines, fence_lang
        blocks.append(_code_block("\n".join(fence_lines), fence_lang or "plain text"))
        fence_lines = []
        fence_lang = ""

    for raw in md.splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        # Fenced code blocks — capture raw lines verbatim until the closing fence.
        if stripped.startswith("```"):
            in_table = False
            if in_fence:
                flush_fence()
                in_fence = False
            else:
                in_fence = True
                fence_lang = stripped[3:].strip()
            continue
        if in_fence:
            fence_lines.append(line)
            continue

        if not stripped:
            in_table = False
            continue

        # Optional title skip — drop the first H1 only.
        if skip_title and not skipped_title and stripped.startswith("# "):
            skipped_title = True
            in_table = False
            continue

        # Headings
        if stripped.startswith("### "):
            in_table = False
            blocks.append(_heading(stripped[4:], 3))
        elif stripped.startswith("## "):
            in_table = False
            blocks.append(_heading(stripped[3:], 2))
        elif stripped.startswith("# "):
            in_table = False
            blocks.append(_heading(stripped[2:], 1))

        # Divider
        elif stripped.startswith("---"):
            in_table = False
            blocks.append(_divider())

        # Numbered list item
        elif re.match(r"^\d+\.\s+", stripped):
            in_table = False
            blocks.append(_numbered(re.sub(r"^\d+\.\s+", "", stripped)))

        # Bullet
        elif stripped.startswith("- ") or stripped.startswith("* "):
            in_table = False
            blocks.append(_bullet(stripped[2:]))

        # Table rows — render header as bold paragraph, data rows as bullets
        elif stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # Skip separator rows (|---|---|)
            if all(re.match(r"^[-: ]+$", c) for c in cells if c):
                continue
            # First table row = header → bold paragraph
            if not in_table:
                in_table = True
                text = " · ".join(f"**{c}**" for c in cells if c)
                blocks.append(_paragraph(text))
            else:
                text = " · ".join(c for c in cells if c)
                blocks.append(_bullet(text))

        # Plain paragraph (includes **bold** lines like "**Rationale:** ...")
        else:
            in_table = False
            blocks.append(_paragraph(stripped))

    # Unterminated fence — emit what we captured rather than dropping it.
    if in_fence and fence_lines:
        flush_fence()

    return blocks
