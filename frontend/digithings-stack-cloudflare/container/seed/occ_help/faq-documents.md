# OCC documents and PDFs (seed)

## Help center documents

The public OCC help center publishes HTML FAQ pages and direct PDF links.
Sample reconnaissance counted on the order of tens of HTML paths and ~24 PDFs
(see project SCOPE). This seed does **not** include those binary PDFs.

## How digisearch treats docs

When full onboard runs, PDFs with text layers are ingested as searchable chunks.
OCR is a fallback (`DIGISEARCH_OCR_ENABLED`), not the default path.

## Vault notes

Onboarded pages become markdown notes under
`clients/online-compliance-center/` with source URLs in metadata when available.
Until then, use these seed FAQ notes for dogfood chat.

## What to tell users

- Public help content is the grounding source for this assistant
- Portal-only or demo-only content is not in this corpus
- If a specific PDF is not retrieved, say it is not in the indexed set yet
