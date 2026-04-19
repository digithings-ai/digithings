# DigiThings-guide

A DigiThings Project that indexes the DigiThings ecosystem's own documentation — ARCHITECTURE files, ADRs, VISION, ROADMAP, and each component's AGENTS / README / DIGI\*.md — so the future "Chat with DigiThings" surface can retrieve from them. This is dogfooding: DigiSearch indexing DigiThings.

## Layout

| File | Purpose |
|---|---|
| `digiproject.yaml` | v1alpha1 project config. Declares the project and points at `indexes/` for discovery. |
| `indexes/docs.yaml` | Index manifest for the `docs` index — lists `sources` globs, backend, description. |

## Reindex

A GitHub Action at [`.github/workflows/reindex-digithings-guide.yml`](../../../.github/workflows/reindex-digithings-guide.yml) triggers on pushes to `develop` that touch any tracked source file. It invokes [`scripts/reindex_digithings_guide.py`](../../../scripts/reindex_digithings_guide.py), which today does a dry-run (resolves the glob set and chunks in-process via the DigiSearch stub backend) and will call a service-less ingest entry point once that lands in DigiSearch.

## Convention note

Conventional DigiThings Projects live under `projects/<name>/` which is gitignored for confidentiality. This one is public and lives under `docs/projects/digithings-guide/` so it can be tracked without carving a `.gitignore` exception. At runtime a deploy may symlink or copy this into the expected `projects/` layout.

## Related

- Spec: [`docs/spec/project-spec-v1alpha1.md`](../../spec/project-spec-v1alpha1.md)
- Schema: `digigraph/src/digigraph/schemas/digiproject.v1alpha1.json` (landed via PR #84)
- Template: [`docs/templates/project/`](../../templates/project/)
- Epic: [#3 Project Spec](https://github.com/digithings-ai/digithings/issues/3)
- Issue: [#23](https://github.com/digithings-ai/digithings/issues/23)
