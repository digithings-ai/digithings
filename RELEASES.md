# Releases

Monorepo components ship as **independent Python packages** (`digibase`, `digigraph`, `digiquant`, `digisearch`, `digismith`). Use **git tags** or Docker image digests in production.

## Release process

1. Confirm CI is green on `develop`, and land the version bump there first — the release-please PR, or a hand bump committed together with its tag (see [Tagging convention](#tagging-convention)).
2. **Promote `develop` → `main`.** Open the promotion PR (`gh pr create --base main --head develop`) and merge it. A PR into `main` is the production cutover, so a human owns that step.
3. **Cut the release branch and the tag on `main`** — one branch per released version, from `main` at the release commit:

   ```bash
   git checkout main && git pull
   git tag digichat-v2.3.2
   git push origin digichat-v2.3.2
   git checkout -b release/v2.3.2
   git push -u origin release/v2.3.2
   ```

   This is a required step, not bookkeeping: the branch is how that version is patched once `main` has moved on. See [Patching a released version](#patching-a-released-version) and BRANCHING.md § [Cutting a release](BRANCHING.md#cutting-a-release).
4. **Docker images (automated on `main`):**
   - Python HTTP services → [`.github/workflows/publish-service-images.yml`](.github/workflows/publish-service-images.yml)  
     Images: `ghcr.io/digithings-ai/{digikey,digigraph,digiquant,digisearch,digismith,digivault,digiclaw}`  
     Tags: `:sha-<12-char-sha>`, `:latest`, and `:v<pyproject-version>`.  
     Manual: Actions → “Publish: service images” → `workflow_dispatch` (all or one service).
   - digichat → [`.github/workflows/publish-digichat-image.yml`](.github/workflows/publish-digichat-image.yml)  
     Tags: `:v<package.json version>` and `:latest` (skips if that version tag already exists).
5. Git tags are cut in step 3 — `git tag <component>-vX.Y.Z` (per-component, e.g. `digichat-v2.3.2`) or repo-wide `vX.Y.Z`, pick one and stay consistent. The tag is what the release branch is anchored to and what pinned clients cite.
6. Append a changelog entry under "Unreleased" below, then move it under a new dated heading.

Self-host pull path: [`infra/self-host/compose.ghcr.yml`](infra/self-host/compose.ghcr.yml) + [`docs/templates/self-host/README.md`](docs/templates/self-host/README.md). Epic: [#2016](https://github.com/digithings-ai/digithings/issues/2016).

**First stack GHCR publish after #2023:** the publish workflow is `main`-only. After promoting develop (includes #2023) to `main`, run Actions → “Publish: service images” → `workflow_dispatch` with `service=all` once so `ghcr.io/digithings-ai/{digikey,digigraph,digivault}` exist for Profile A / `make up-ghcr`.

## Patching a released version

A patch release continues the chain of the version it fixes — a new `release/`
branch off the previous one, so the branch name always equals the version it
carries:

```bash
git checkout -b release/v2.3.3 release/v2.3.2
# apply the fix, bump the version to 2.3.3, commit
git tag digichat-v2.3.3
git push origin release/v2.3.3 digichat-v2.3.3
```

The tag is what publishes the image (`publish-digichat-image.yml` keys off
`package.json`'s version; the Python services key off `pyproject`), so a patch
release needs the bump, the tag, and the branch together.

Then get the fix onto the mainline:

- **Current line** — if `main` is still on `2.3.x`, also open the patch as a PR
  into `main`. Production should carry the fix.
- **Older line** — if `main` has moved on (say to `2.4.0`), do **not** merge the
  release branch into `main`: its version bump would take production backwards.
  Cherry-pick the *fix* (never the version bump) onto `develop` instead, so the
  next promotion carries it forward:

  ```bash
  git checkout develop
  git cherry-pick <fix-sha>
  ```

Release branches are never deleted — one per released version, and an old one is
the only way to patch a client still pinned to it. See BRANCHING.md §
[Patching a release](BRANCHING.md#patching-a-release).

## Tagging convention

- Per-component: `digigraph-v0.1.0`, `digiquant-v0.1.0`, etc.
- Or a single repo-wide `v0.1.0` with matching image builds across services.

Either works; pick one and stay consistent within a release cycle.

### digichat: versioning (1.0.0 public cut)

**Public line is `1.0.0`.** release-please had proposed `0.9.4` (#2014); that PR
was closed and the version was forced to **1.0.0** (`package.json` +
`.release-please-manifest.json` + `CHANGELOG.md`) so the next develop→main
promote publishes `ghcr.io/digithings-ai/digichat:v1.0.0`.

**Do not delete `ghcr.io/digithings-ai/digichat:v0.9.3`.** DataTap and other
existing clients remain pinned there until they upgrade.

Historically, while digichat was pre-1.0, release-please used
`bump-patch-for-minor-pre-major` + `bump-minor-pre-major` so every release was
a patch bump (0.9.2 → 0.9.3 → …) instead of burning minors on each `feat`. Those
flags remain in `release-please-config.json`; after 1.0.0, conventional
`feat`/`fix`/`BREAKING` semver applies normally for subsequent cuts.

**Tag every release.** 0.9.1 and 0.9.2 were bumped inside ordinary PRs
(`6f7d5a30`, `8c166c50`) and never tagged, so release-please lost its baseline
and proposed a bogus 0.10.0 whose changelog re-listed ~28 already-shipped
features. Those two tags have since been created. If you bump a version by
hand, cut the matching `digichat-vX.Y.Z` tag in the same change.

## Pinning policy

- Deploy **one git SHA** across services built from this repo, or
- Follow the compatibility matrix in [ARCHITECTURE.md](ARCHITECTURE.md).

## Install order (local / CI)

`pip install -e ./digibase` first, then editable installs of dependents (`digigraph`, `digiquant`, `digisearch`, `digismith`). Dockerfiles use a **repo-root build context** so `digibase` is copied and installed before each service package.

## Changelog (high level)

### Unreleased

- **Branch cleanup:** Confirmed removal of stale merged branch `task/149-w1e-price-pipeline` (already deleted from origin; merged into `develop` via PR #286 / #288 for issue #149 — research price pipeline migration).

- **Baseline cleanup (Phase 1–7):** AI-hallucinated docs removed; root docs rewritten; digiclaw repackaged (Phase 4); code dedup into `digibase`; test baseline for digiclaw; full details in [#31](https://github.com/digithings-ai/digithings/issues/31).
- **Strategic docs:** [docs/VISION.md](docs/VISION.md) captures two-domain plan (digithings.ai + digiquant.io) and strategic decisions. First ADRs landed: [0001 Project Spec](docs/adr/0001-project-spec.md), [0002 Domain Unification](docs/adr/0002-domain-unification.md).
- **Federated hub:** digisearch/digiquant expose `POST /v1/orchestrator_tools` + `POST /v1/orchestrator_invoke` (manifest + dispatch). digigraph caches vertical tool schemas and invokes them (same JWT chain). `DIGI_HUB_MODE=federated` additionally registers `digisearch_research_delegate` / `digiquant_pipeline_delegate`. digiquant: `POST /v1/workflow`, MCP `digiquant_run_pipeline`. digisearch: optional `digisearch[agent]`, `POST /v1/research_turn`, MCP `digisearch_research_turn`. digichat: `DIGICHAT_ENABLED_SERVICES`, optional `DIGISEARCH_INTERNAL_URL`, trace `service` field in UI.
- **Infra / LiteLLM:** Compose uses `docker.litellm.ai/berriai/litellm:main-stable`, explicit `--config`, `/health/liveliness` healthcheck, digigraph `depends_on: litellm` healthy; optional `litellm-cache` profile (Redis). `LITELLM_PROXY_API_KEY` for digigraph Bearer vs upstream `OPENAI_API_KEY` in LiteLLM; proxy `litellm_settings` cache, retries, timeouts, and Ollama Cloud → local fallbacks in `config/litellm.yaml`.
- **digibase** (new): shared HTTP headers, API error envelope, audit redaction helper, optional OTel FastAPI wiring. Docs: [digibase/ARCHITECTURE.md](digibase/ARCHITECTURE.md) describes the shipped **library** vs the **roadmap** digibase **data-plane** service.
- **digigraph:** depends on `digibase`; standardized errors; policy module; optional tool entry points `digigraph.tools`; `quant_artifact_uri` in workflow state.
- **digiquant:** `POST /v1/jobs/backtest`, `GET /v1/jobs/{id}/status`; `digibase` errors and OTel.
- **digisearch:** `workspace_id` on query; `digisearch-worker` CLI stub; `embeddings.config`; `digibase` integration.
- **digismith:** `digibase` errors and OTel; correlation middleware.
- **digiclaw:** optional `AUDIT_SINK_URL` for NDJSON POST mirror.
