# Index Definitions

Each index has its own config file. Connection credentials (endpoint, api_key) stay in `.env`. Index name, field mapping, and schema live here.

Project `config.yaml` uses `indexes_dir: indexes`, so **all `*.yaml` files in this folder are included** automatically; no need to list them in `config.yaml`. Each file’s `index_name` becomes the index name and a `digisearch_{name}_query` MCP tool is registered.

## Structure

```
indexes/
├── README.md
└── unified-content-index.yaml   # Microsoft 365 unified content
```

## Adding an Index

1. Create `indexes/<index-name>.yaml`
2. Define `index_name`, `field_mapping`, `schema`
3. No change to `config.yaml`—indexes in this folder are discovered automatically

## Field Mapping

| Key | Purpose |
|-----|---------|
| `content_field` | Primary text for search and display |
| `content_fallback` | Fallback when content_field is empty |
| `key_field` | Unique chunk/document ID |
| `doc_id_field` | Parent document ID for grouping |

## Validate index and filtering

From repo root with venv and `.env` in `projects/sitaas/`:

```bash
# Unit tests: validate config YAML (no Azure)
pytest tests/ds/test_sitaas_index.py -m unit -v

# Integration tests: require AZURE_SEARCH_* and DIGISEARCH_INDEX_CONFIG
pytest tests/ds/test_sitaas_index.py -m integration -v

# Probe live index: sample docs, distinct filter values, filter syntax
make -C projects/sitaas probe
# Or: cd projects/sitaas && set -a && source .env && set +a && python scripts/probe_index.py
```

**Index structure:** The YAML schema lists all fields; **complex_field_structures** documents JSON/collection fields (toRecipients, ccRecipients, attachments, mentions, reactions, replies) with item shape and example OData filters. To inspect live structure from the index, run `python projects/sitaas/scripts/inspect_index_structure.py` (requires Azure .env).

Filtering: **structured** `filters` with ops `eq`, `ne`, `gt`, `ge`, `lt`, `le`, **`in`**. **Raw OData** when `allow_raw_filter: true` (required for collection filters like `toRecipients/any(...)`). See **FILTER_SYNTAX.md**. **Facets**, **highlighting**, **order_by**, **skip**, **include_total_count**: see **SEARCH_FEATURES.md**.
