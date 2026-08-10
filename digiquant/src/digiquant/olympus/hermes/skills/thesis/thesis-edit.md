---
name: thesis-edit
description: Patch-update the thesis review document (edit mode).
---

# Thesis Review — Edit Mode

Update the prior **Thesis Review** via `DocumentPatch` ops only.

- `target_document_key`: `thesis/thesis-review`
- Patch `/body/reviewed_theses` and related fields; do not rewrite unchanged theses.
- When invalidation criteria fire, patch the affected thesis to `CHALLENGED` with `challenged_by`.

Respond with a single `DocumentPatch` JSON object.
