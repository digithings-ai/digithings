# DigiSearch / Azure index – query features

Summary of what the search tool supports today and what could be added next.

## Implemented (POST /query)

| Feature | Request param | Description |
|--------|----------------|-------------|
| **Full-text search** | `text`, `top_k`, `mode` | Simple query; `top_k` limit; mode keyword/vector/hybrid (Azure: simple query_type). |
| **Structured filters** | `filters` | `[{field, op, value}]` with `eq`, `ne`, `gt`, `ge`, `lt`, `le`, `in`. See FILTER_SYNTAX.md. |
| **Raw OData filter** | `filter` | When index has `allow_raw_filter: true`. |
| **Facets** | `facets` | e.g. `["sourceType", "itemType,count:20"]`; response includes `facets` with value/count per field. |
| **Columns** | `columns` | Metadata fields to return in each hit. |
| **Highlighting** | `highlight_fields`, `highlight_pre_tag`, `highlight_post_tag` | Hit highlighting; matching terms wrapped in tags. Highlights appear in result `metadata["@search.highlights"]`. |
| **Sort (orderby)** | `order_by` | e.g. `["sentDateTime desc", "search.score() desc"]`. Fields must be sortable in Azure. |
| **Pagination** | `skip`, `top_k` | `skip` = offset; page = `skip` to `skip + top_k`. |
| **Total count** | `include_total_count` | When `true`, response `total` is full match count (for “Page 1 of 24”). |
| **Summary** | `response_mode`, `summarize_if_over` | Summary of results when over threshold. |

## Possible next steps (Azure supports, we don’t yet)

| Feature | Azure capability | Notes |
|--------|------------------|--------|
| **Semantic search** | `queryType: "semantic"`, semantic config, captions/answers | Requires semantic configuration on the index; improves relevance and supports captions/answers. |
| **Vector search** | `vector_queries`, vector fields | For hybrid/vector mode we’d pass vector_queries when embeddings provided. |
| **Scoring profile** | `scoring_profile`, `scoring_parameters` | Custom ranking (e.g. boost recent, boost by importance). |
| **Query type** | `query_type: "full"` | Lucene-style query syntax (phrase, wildcards, etc.) instead of simple. |
| **Speller** | `speller` (preview) | Lexicon-based spelling correction. |
| **Session** | `session_id` | Session tracking for learning-to-rank or analytics. |

## Sitaas index (unified-content-index)

- **Filterable / facetable:** See `filterable_fields` and `facetable_fields` in `unified-content-index.yaml`.
- **Sortable:** Typically date fields (`sentDateTime`, `createdDateTime`, `receivedDateTime`, `lastModifiedDateTime`) and possibly others; check Azure index definition.
- **Highlighting:** Use searchable text fields, e.g. `body`, `bodyPreview`, `subject` (see schema in the YAML).
