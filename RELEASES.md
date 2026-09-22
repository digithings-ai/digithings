# Releases

Monorepo components ship as **independent Python packages** (`digibase`, `digigraph`, `digiquant`, `digisearch`, `digismith`). Use **git tags** or Docker image digests in production.

## Release process

1. Confirm CI is green on `develop`, and land the version bump there first — merge the release-please PR (or, for a hand bump, commit it on `develop` together with its tag — see [Tagging convention](#tagging-convention)). Merging the release-please PR is what cuts the `digichat-vX.Y.Z` tag, on `develop`.
2. **Promote `develop` → `main`.** Open the promotion PR (`gh pr create --base main --head develop`) and merge it. A PR into `main` is the production cutover, so a human owns that step.
3. **Cut the release branch on `main`** — one branch per released version, from `main` at the promotion commit (the tag's commit is in `main`'s history by then):

   ```bash
   git checkout main && git pull
   git checkout -b release/v2.3.2
   git push -u origin release/v2.3.2
   ```

   This is a required step, not bookkeeping: the branch is how that version is patched once `main` has moved on. See [Patching a released version](#patching-a-released-version) and BRANCHING.md § [Cutting a release](BRANCHING.md#cutting-a-release).
4. **Docker images:**
   - digichat → [`.github/workflows/publish-digichat-image.yml`](.github/workflows/publish-digichat-image.yml)  
     Published when release-please cuts the `digichat-vX.Y.Z` tag on `develop` (the release workflow dispatches it at the tag), and re-checked on a push to `main` touching `apps/digichat/**`.  
     Tags: `:v<package.json version>` and `:latest` (skips if that version tag already exists).
   - Python HTTP services → [`.github/workflows/publish-service-images.yml`](.github/workflows/publish-service-images.yml) — a push to `main` only, **not** a tag.  
     Images: `ghcr.io/digithings-ai/{digikey,digigraph,digiquant,digisearch,digismith,digivault,digiclaw}`  
     Tags: `:sha-<12-char-sha>`, `:latest`, and `:v<pyproject-version>`.  
     Manual: Actions → “Publish: service images” → `workflow_dispatch` (all or one service).
5. **Tagging:** the `digichat-vX.Y.Z` tag is cut in step 1 by release-please (if you bump by hand, cut it yourself on `develop` in the same change). Per-component `digichat-vX.Y.Z` or repo-wide `vX.Y.Z` — pick one and stay consistent. The tag is the release identity pinned clients cite, and it is what publishes the digichat image.
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

A human-pushed `digichat-vX.Y.Z` tag publishes the digichat image
(`publish-digichat-image.yml` keys off `package.json`'s version), so for digichat
a patch release needs the bump, the tag and the branch together. The Python
service images publish only on a push to `main`, so a patch that is never
promoted ships no service image.

The fix then has to reach `develop`, in every case — release-please reads
`develop`, so a fix that only lives on the release branch is clobbered by the
next promotion:

```bash
git checkout develop
git cherry-pick <fix-sha>                        # the fix, never the version bump
```

Never merge the release branch into `main`: its version bump would take
production backwards (or fork the version line). Production picks the fix up
through the next `develop` → `main` promotion, which now carries the
cherry-pick. If production has to be patched sooner — only meaningful while
`main` is still on the same line, `2.3.x` — cherry-pick the *fix* into a
`fix/<slug>` branch off `main`, PR it into `main` (human on the cutover), and
cherry-pick the same fix onto `develop`. Still never the version bump.

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
