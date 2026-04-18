# ADR 0001: DigiThings Project Spec

**Status:** proposed
**Date:** 2026-04-18

## Context

DigiThings has grown into eight components (`digigraph`, `digisearch`, `digiquant`, `digichat`, `digikey`, `digiclaw`, `digismith`, `digibase`). The first real client engagement — **SITAAS** (`projects/sitaas/`) — demonstrated a reusable pattern for composing a subset of components into a running stack:

- `config.yaml` — project metadata, enabled agents, LLM mode, system prompts, run-storage path, indexes directory, MCP config, service URLs.
- `indexes/*.yaml` — per-index schema/field mapping.
- `.env` + `.env.example` — connection strings and secrets only.
- `docker-compose.yml` — composes published DigiThings images, mounts `config.yaml` as `DIGI_PROJECT_CONFIG`, mounts `indexes/` into `DigiSearch`.
- `Makefile` — project-local conveniences (`make update`, `make build-no-cache`).

SITAAS does **not** include DigiQuant. Future projects will include different subsets (e.g. Atlas: DigiGraph + DigiSearch + DigiQuant; a client RAG-only project: DigiSearch + DigiChat). Today this composition pattern is **implicit** — documented only in the SITAAS README. Without a shared spec, each new project risks diverging conventions, per-project config shapes, and deployment quirks.

## Decision

Formalize the pattern as the **DigiThings Project Spec**: a declarative manifest that fully describes a deployable composition of DigiThings components. A "project" is the unit of client engagements, internal products, and pilots.

### Minimum required surface

```
<project-root>/
  digiproject.yaml       # required — the manifest
  docker-compose.yml     # required — composes component images per manifest
  .env.example           # required — all env vars the project needs
  indexes/               # optional — per-index schemas (if DigiSearch is enabled)
  prompts/               # optional — overrideable system prompts
  Makefile               # optional — project-local convenience targets
  README.md              # required — quick-start + deployment notes
```

### Manifest structure (v0.1)

```yaml
apiVersion: digithings.ai/v1alpha1
kind: Project
metadata:
  name: sitaas
  description: "Unified content exploration agent over Azure AI Search."
  version: 0.1.0
  owner: team-or-client

components:
  digigraph:
    enabled: true
    agents: [research]
    llm_mode: test
    checkpointer: memory
    system_prompts:
      research: ./prompts/research.md  # or inline string
  digisearch:
    enabled: true
    indexes_dir: ./indexes
  digiquant:
    enabled: false
  digichat:
    enabled: false
  litellm:
    enabled: true
    config: ../../config/litellm.yaml

mcp:
  enabled: true
  tools: [digigraph_workflow]

storage:
  run_data_dir: /data/run

services:
  # per-component URL overrides (for non-default deployments)
  digisearch_url: "${DIGISEARCH_URL:-http://digisearch:8002}"

auth:
  digikey:
    jwks_url: "${DIGIKEY_JWKS_URL}"
    issuer: "${DIGIKEY_ISSUER}"
    audience: "${DIGIKEY_AUDIENCE:-digi-ecosystem}"
```

Today SITAAS's `config.yaml` is already ~80% of this shape. The spec formalizes field names, adds `apiVersion`/`kind` for future evolution, and makes component enablement explicit.

### Rendering

Phase 1: **hand-authored** `docker-compose.yml` per project, following a documented template. No code generation.

Phase 2 (future, behind a feature flag): `digi project render <manifest>` → emits `docker-compose.yml` from the manifest. Deferred until we have 3+ projects and real patterns to codify.

### Component contract

Every component must:
- Accept a manifest-supplied config via a documented env var (`DIGI_PROJECT_CONFIG` for DigiGraph; equivalents for the rest — to be specified).
- Support being disabled — a project that only needs DigiSearch should not require DigiQuant to be pulled or running.
- Publish a **stable Docker image** on a registry (currently built locally; future: GHCR).

## Consequences

**Positive**
- New client engagements start from a template, not a blank repo.
- Components evolve independently of projects; projects pin to image tags.
- Clear public-vs-private boundary: components in the open-core monorepo; project manifests in `projects/` (confidential) or client-owned repos.
- Enables future **managed hosting**: a project manifest is portable enough that we can run it for the client.

**Negative / tradeoffs**
- Upfront cost: we need to refactor SITAAS to the formal spec and update each component to honor the manifest contract. Probably one focused phase of work.
- Risk of premature formalization: the spec may change as we onboard projects 2 and 3. Mitigated by marking `v1alpha1` and being explicit that breaking changes are allowed until `v1`.
- Adds a layer of indirection for contributors who only want to run the core stack. The root `docker-compose.yml` and `make up` flow must remain the zero-config path.

## Alternatives considered

1. **Keep the pattern implicit.** Cheapest, but guarantees drift across projects and makes onboarding harder.
2. **Full Helm/Kustomize-style templating from day one.** Overkill for 1–3 projects; we don't yet know what varies enough to template.
3. **One shared monorepo where every project is a top-level directory.** Couples project lifecycles to component releases; makes client-IP segregation harder.

## Migration plan

1. Formalize spec as `docs/spec/project-spec-v1alpha1.md` (this ADR is the rationale; the spec file is the reference).
2. Refactor `projects/sitaas/config.yaml` → `digiproject.yaml` following the manifest schema. Keep backward-compat loader for one release.
3. Audit each component for manifest-contract gaps (which env vars? which disablement paths?).
4. Add a `projects/template/` starter.
5. Use the spec for the **next** project (Atlas manifest, or SITAAS Phase 2).

## Links

- SITAAS reference implementation: `projects/sitaas/`
- Related: ADR-0002 (Domain Unification)
- Related: `docs/VISION.md` — strategic context
