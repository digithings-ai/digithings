# Epic #3 — DigiThings Project Spec v1alpha1

Decomposition of [epic #3](https://github.com/digithings-ai/digithings/issues/3) into shipped work and remaining sub-tasks. The epic formalises `digiproject.yaml` as the single source of truth for per-deployment tunables, per [ADR-0001](../adr/0001-project-spec.md).

## Recap

`digiproject.yaml` (v1alpha1) replaces the ad-hoc `projects/<name>/config.yaml` used by SITAAS. The schema covers project identity, agent selection, LLM mode, per-project paths (`run_data_dir`, `indexes_dir`), MCP exposure, and service URLs. Every field is optional and defaults produce a valid (minimal) deployment. The formal reference lives at [docs/spec/project-spec-v1alpha1.md](../spec/project-spec-v1alpha1.md); the loader is `digigraph/src/digigraph/project_config.py`.

## Shipped

- **PR #55** — `docs(spec): write project-spec-v1alpha1.md`. Landed the formal reference: YAML schema, equivalent JSON Schema (draft 2020-12), env-var contract table, enable/disable matrix, versioning policy, SITAAS reference config.
- **PR #56** — `refactor(digigraph): backward-compat loader for digiproject.yaml migration`. Added `_resolve_config_path()` with priority order (`digiproject.yaml` → `config/digiproject.yaml` → `config/digi_project.yaml`) and deprecation warnings when the legacy `config.yaml` path is still in use.
- **PR #57** — `feat(docs): create project template starter`. Landed `docs/templates/project/` (minimal `digiproject.yaml`, `docker-compose.yml`, `.env.example`, README quickstart) so a new project can be bootstrapped by copying the directory into the gitignored `projects/` tree.

## Remaining sub-tasks

- [x] **E2E loader test.** Add a pytest (marker `e2e`) that mounts `docs/templates/project/digiproject.yaml` into a running DigiGraph, issues `/workflow`, and asserts the resolved `DigiProjectConfig` surfaced through `/v1/status` (or an equivalent debug endpoint) matches the file contents. Covers the "new engineer → 10 min" success criterion in epic #3. (**PR #69**)
- [x] **Validation CLI.** Ship `digi project validate <path>` that parses the YAML, runs the JSON Schema from the spec, checks env-var references resolve, and exits non-zero on error. Reuses the schema block already embedded in [docs/spec/project-spec-v1alpha1.md](../spec/project-spec-v1alpha1.md); extracted to `digigraph/src/digigraph/schemas/digiproject.v1alpha1.json` so the spec doc and the CLI stay in lockstep. (**PR #92**)
- [x] **Legacy-shape migration helper.** `digi project migrate <old-config.yaml>` that rewrites a pre-spec `config.yaml` into a valid `digiproject.yaml` (field renames, section nesting, removed keys flagged as warnings). The backward-compat loader from PR #56 is meant to last one release; this gives users a one-shot path off it. (**PR #99**)
- [x] **Unsupported-version warning.** The spec promises `DigiProjectConfig` "will emit a warning when loading a file that declares an unsupported `version` field" — wire this in the loader with a unit test. (**PR #91**)
- [x] **mtime cache contract test.** The spec asserts the project config is re-read on every request, keyed by mtime. Add a unit test that mutates the file between two `load_project_config()` calls and verifies the second call sees the change without a process restart. (**PR #90**)

All items block graduation from `v1alpha1` → `v1beta1` (see the versioning policy in [the spec](../spec/project-spec-v1alpha1.md#versioning-policy)).
