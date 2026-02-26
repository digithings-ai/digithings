# Azure AI Search filter syntax (Sitaas / DigiSearch)

## Facets

You can request **facet counts** (aggregations of distinct values and counts) in the same query. Use the **facets** parameter with a list of facet expressions. The response includes a **facets** object: field name → list of `{value, count}`.

**Example request (POST /query):**
```json
{
  "text": "*",
  "index_name": "unified-content-index",
  "top_k": 10,
  "facets": ["sourceType", "itemType,count:20"]
}
```

**Example response:** `facets` might be `{"sourceType": [{"value": "EXCHANGE", "count": 42}, {"value": "TEAMS", "count": 18}], "itemType": [...]}`.

Facet expressions can include options: `FieldName,count:N` (max terms, default 10), `FieldName,sort:count` or `sort:-value`. Fields must be **facetable** in the Azure index; see `facetable_fields` in this index YAML.

---

DigiSearch supports two ways to filter the unified-content index:

1. **Structured filters** – JSON list `[{ "field", "op", "value" }]` (and optionally `op: "in"` with `value` a list or comma-separated string).
2. **Raw OData** – when `allow_raw_filter: true` is set in this index’s YAML, the API accepts a `filter` string and passes it through to Azure as the `$filter` expression.

Reference: [OData expression syntax (Azure AI Search)](https://learn.microsoft.com/en-us/azure/search/search-query-odata-syntax-reference).

---

## Structured filters (built-in)

Allowed **ops**: `eq`, `ne`, `gt`, `ge`, `lt`, `le`.

- **eq/ne**: value can be string, number, boolean, or `null`.
- **gt/ge/lt/le**: value is number or ISO date-time string.

Only fields listed in **filterable_fields** in this index YAML are allowed.

**Examples (API `filters` body):**

```json
{ "filters": [{ "field": "sourceType", "op": "eq", "value": "EXCHANGE" }] }
{ "filters": [{ "field": "hasAttachments", "op": "eq", "value": true }] }
{ "filters": [
    { "field": "sourceType", "op": "eq", "value": "EXCHANGE" },
    { "field": "importance", "op": "ge", "value": 1 }
  ] }
```

Multiple clauses are combined with **and**.

### Op `in` (match any of a list)

Use **op: `"in"`** with **value** as an array or comma-separated string. This is translated to Azure’s `search.in(field, 'v1,v2,v3', ',')` (efficient and recommended for many values).

```json
{ "filters": [{ "field": "sourceType", "op": "in", "value": ["EXCHANGE", "TEAMS"] }] }
{ "filters": [{ "field": "itemType", "op": "in", "value": "MessageItem,EmailMessage" }] }
```

`search.in` is for **string** filterable fields only.

---

## Raw OData (advanced)

If you set **allow_raw_filter: true** in this index YAML, the API accepts a **filter** string (OData `$filter`). You can then use the full Azure filter grammar.

### Comparison and logical operators

- **Comparison**: `eq`, `ne`, `gt`, `lt`, `ge`, `le`
- **Logical**: `and`, `or`, `not`
- **Constants**: strings in single quotes (`'value'`), numbers, `true`/`false`, `null`, date-time (e.g. `2024-01-15T00:00:00Z`)

Examples:

- `sourceType eq 'EXCHANGE' and hasAttachments eq true`
- `(sourceType eq 'EXCHANGE' or sourceType eq 'TEAMS') and importance ge 1`
- `not (itemType eq 'Spam')`

### search.in (multi-value, string)

- `search.in(sourceType, 'EXCHANGE,TEAMS', ',')`
- Default delimiters (space and comma): `search.in(fromAddress, 'a@b.com user@c.com')`

### search.ismatch / search.ismatchscoring (full-text in filter)

- `search.ismatch('word', 'body')` – simple full-text match in a field.
- `search.ismatch('"exact phrase"', 'body', 'full', 'any')` – phrase and query type/mode.
- Combines with other conditions: `search.ismatch('urgent', 'subject') and sourceType eq 'EXCHANGE'`

### Collection (JSON) fields: any() / all()

The unified index has several **collection** (JSON array) fields. Use `any()` or `all()` in raw OData to filter on them. Set **allow_raw_filter: true** in the index YAML.

**Recipients (Exchange):** Each item has `emailAddress: { name, address }`.

- Match any To recipient: `toRecipients/any(r: r/emailAddress/address eq 'user@example.com')`
- Match any CC: `ccRecipients/any(r: r/emailAddress/address eq 'user@example.com')`
- Same for `bccRecipients`

**Attachments:**

- Has PDF attachment: `attachments/any(a: a/contentType eq 'application/pdf')`
- Has attachment named X: `attachments/any(a: a/name eq 'file.pdf')`

**Teams (mentions, reactions):**

- Message mentions user: `mentions/any(m: m/mentionText eq 'username')`
- Has like reaction: `reactions/any(r: r/reactionType eq 'like')`

**Replies:** `replies/any(r: ...)` with path to the nested field you need.

Exact field paths depend on how the index ingests the Microsoft Graph payload; see **unified-content-index.yaml** → `complex_field_structures` for documented shapes and examples.

### Geospatial (if index has geography fields)

- `geo.distance(location, geography'POINT(lon lat)') lt 5000`
- `geo.intersects(location, geography'POLYGON((...))')`

### Limits

- Filter expression size and complexity are limited by Azure (see [Filters in Azure AI Search](https://learn.microsoft.com/en-us/azure/search/search-filters)).
- Prefer **search.in** over long `(field eq 'a' or field eq 'b' or ...)` for many values.

---

## Enabling raw filter for this index

In **unified-content-index.yaml** add:

```yaml
# Allow API to pass through raw OData filter string (filter param)
allow_raw_filter: true
```

Then call the query API with **filter** set to your OData string instead of (or in addition to) **filters**.
