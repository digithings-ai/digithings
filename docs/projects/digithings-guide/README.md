# digithings-guide

A digithings Project that indexes the digithings ecosystem's own documentation — ARCHITECTURE files, ADRs, VISION, ROADMAP, and each component's AGENTS / README / DIGI\*.md — so the future "Chat with digithings" surface can retrieve from them. This is dogfooding: digisearch indexing digithings.

> **Deprecation path (dogfood cutover):** Prefer
> [`docs/projects/digithings/`](../digithings/) + `scripts/docs_onboard` dual-sink
> (`onboard.yaml` + `indexes/docs.yaml`). Keep this guide + `reindex_digithings_guide.py`
> only for **parallel comparison** until digisearch dual-sink is verified on
> digithings.ai/chat; then retire (see GAPLOG).

## Layout

| File | Purpose |
|---|---|
| `digiproject.yaml` | v1alpha1 project config. Declares the project and points at `indexes/` for discovery. |
| `indexes/docs.yaml` | Index manifest for the `docs` index — lists `sources` globs, backend, description. |

## Reindex

A GitHub Action at [`.github/workflows/docs-reindex-guide.yml`](../../../.github/workflows/docs-reindex-guide.yml) triggers on pushes to `develop` that touch any tracked source file. It invokes [`scripts/reindex_digithings_guide.py`](../../../scripts/reindex_digithings_guide.py), which today does a dry-run (resolves the glob set and chunks in-process via the digisearch stub backend) and will call a service-less ingest entry point once that lands in digisearch.

## Convention note

Conventional digithings Projects live under `projects/<name>/` which is gitignored for confidentiality. This one is public and lives under `docs/projects/digithings-guide/` so it can be tracked without carving a `.gitignore` exception. At runtime a deploy may symlink or copy this into the expected `projects/` layout.

## Related

- Client #0 onboard: [`docs/projects/digithings/`](../digithings/)
- Spec: [`docs/spec/project-spec-v1alpha1.md`](../../spec/project-spec-v1alpha1.md)
- Schema: `digigraph/src/digigraph/schemas/digiproject.v1alpha1.json` (landed via PR #84)
- Template: [`docs/templates/project/`](../../templates/project/)
- Epic: [#3 Project Spec](https://github.com/digithings-ai/digithings/issues/3)
- Issue: [#23](https://github.com/digithings-ai/digithings/issues/23)
