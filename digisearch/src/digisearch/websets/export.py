# score:allow untyped any
# exported row dictionaries are dynamic by field set; Any is the honest annotation.
"""Phase D webset export (#4066, Task 6) — polars CSV + citation-preserving JSON.

Only verified items are ever handed here (the service selects
``verification="verified"``): rejected audit rows stay queryable through
``list_items`` but never reach a dataset export.

``export_json`` serializes the verified items with their full audit shape —
``criteria_results`` (verdict + reasoning + references) and per-field
``enrichments`` (``value`` + ``citations`` + terminal ``status``) — so every
exported value keeps the citations that justify it.

``export_csv`` flattens one row per item through ``polars.DataFrame.write_csv``
(never pandas). Columns:

- core: ``item_id``, ``webset_id``, ``url``, ``title``, ``verification``,
  ``criteria_results`` (JSON), ``created_at``;
- per enrichment field name: ``enrichment__{name}__value`` and
  ``enrichment__{name}__citations``. The citations cell carries the
  semicolon-joined citation URLs (``None`` when the field carries none); a
  non-scalar value (e.g. a ``company_profile`` entity) is JSON-encoded.
  A value column stays numeric (``Int64``/``Float64``) only when every
  non-null value is numeric; any mixed/text column is stringified instead, so
  polars never trips over a heterogeneous column.

Fields come from the webset's attached defs first, then any removed-but-retained
item field (``remove_enrichment`` keeps resolved values), sorted for stable
column order.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import polars as pl

from digisearch.web_search.citation import Citation
from digisearch.websets.models import Webset, WebsetItem

__all__ = ["export_csv", "export_json"]

_ENRICHMENT_PREFIX = "enrichment__"
_VALUE_SUFFIX = "__value"
_CITATIONS_SUFFIX = "__citations"
_CITATIONS_SEPARATOR = "; "

_CORE_COLUMNS = (
    "item_id",
    "webset_id",
    "url",
    "title",
    "verification",
    "criteria_results",
    "created_at",
)


def export_json(webset: Webset, items: Sequence[WebsetItem]) -> str:
    """Serialize *items* as one JSON document with per-field citations retained."""
    payload = {
        "webset_id": webset.id,
        "items": [item.model_dump(mode="json") for item in items],
    }
    return json.dumps(payload, indent=2)


def export_csv(webset: Webset, items: Sequence[WebsetItem]) -> str:
    """Flatten *items* into one polars CSV row per item (schema documented above)."""
    fields = _enrichment_fields(webset, items)
    schema = _schema(items, fields)
    rows = [_row(item, fields, schema) for item in items]
    return pl.DataFrame(rows, schema=schema).write_csv()


def _enrichment_fields(webset: Webset, items: Sequence[WebsetItem]) -> list[str]:
    """Attached def names plus retained item-only fields, sorted for a stable schema."""
    names = {definition.name for definition in webset.enrichments}
    for item in items:
        names.update(item.enrichments)
    return sorted(names)


def _schema(items: Sequence[WebsetItem], fields: Sequence[str]) -> dict[str, pl.DataType]:
    schema: dict[str, pl.DataType] = {column: pl.Utf8 for column in _CORE_COLUMNS}
    for name in fields:
        schema[f"{_ENRICHMENT_PREFIX}{name}{_VALUE_SUFFIX}"] = _value_dtype(items, name)
        schema[f"{_ENRICHMENT_PREFIX}{name}{_CITATIONS_SUFFIX}"] = pl.Utf8
    return schema


def _value_dtype(items: Sequence[WebsetItem], name: str) -> pl.DataType:
    """Numeric only when every non-null value of the field is numeric (bool excluded)."""
    values: list[Any] = []
    for item in items:
        field = item.enrichments.get(name)
        if field is not None and field.value is not None:
            values.append(field.value)
    if values and all(
        not isinstance(value, bool) and isinstance(value, (int, float)) for value in values
    ):
        if all(isinstance(value, int) for value in values):
            return pl.Int64
        return pl.Float64
    return pl.Utf8


def _row(item: WebsetItem, fields: Sequence[str], schema: dict[str, pl.DataType]) -> dict[str, Any]:
    row: dict[str, Any] = {
        "item_id": item.id,
        "webset_id": item.webset_id,
        "url": item.url,
        "title": item.title,
        "verification": item.verification,
        "criteria_results": json.dumps(
            [result.model_dump(mode="json") for result in item.criteria_results],
            sort_keys=True,
        ),
        "created_at": item.created_at.isoformat() if item.created_at is not None else None,
    }
    for name in fields:
        field = item.enrichments.get(name)
        value_column = f"{_ENRICHMENT_PREFIX}{name}{_VALUE_SUFFIX}"
        row[value_column] = _value_cell(
            None if field is None else field.value, schema[value_column]
        )
        row[f"{_ENRICHMENT_PREFIX}{name}{_CITATIONS_SUFFIX}"] = _citations_cell(
            [] if field is None else field.citations
        )
    return row


def _value_cell(value: Any, dtype: pl.DataType) -> Any:
    """Coerce a value to the column's dtype (JSON for collections, str for mixed)."""
    if value is None:
        return None
    if dtype == pl.Utf8 and not isinstance(value, str):
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return str(value)
    return value


def _citations_cell(citations: Sequence[Citation]) -> str | None:
    """The semicolon-joined citation URLs, or ``None`` when the field carries none."""
    urls = [citation.url for citation in citations if citation.url]
    if not urls:
        return None
    return _CITATIONS_SEPARATOR.join(urls)
