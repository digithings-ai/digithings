# digichat on DataTap's Azure Container Apps — deploy lane, tag→commit binding, and promotion runbook (DIG-1242)

**Status:** runbook. Nothing in this document performs a write on its own; every command is run by a human, and the production one needs Chris.
**Owner:** DevOps
**Scope:** the digichat Container App that DataTap runs in **their** Azure (`datatapchatregistry.azurecr.io`, East US 2), not the digithings Cloudflare Container.
**Verified:** 2026-10-06, read-only (`az … show` / `list`, `git`, `curl`).

---

## Why this document exists

DIG-1242 asked for three things: decide the lane, bind tag to commit, rehearse on dev. Discovery turned up a fourth fact that shapes the first three.

**There is no deploy lane, because there was never a build lane either.** The tag ladder in the ACR is the evidence:

| Tag family | Count | What it implies |
|---|---|---|
| `v0.4.0` … `v2.3.3` | 15 | clean release names |
| `-error1`…`-error3`, `-welcome1/2`, `-boot1`, `-textleak-…`, `-counter1`…`-counter9` | 15 | **hand-built, hand-debugged images** |

Half the registry is ad-hoc debugging under names no workflow produced. The one tag that embeds a git SHA — `v2.0.0-main.7263272` — shows commit binding was attempted once and abandoned. ~~`ghcr.io/digithings-ai/digichat` **does not exist** (verified three ways: anonymous token `401`, `GET /v2/…/tags/list` `401`, `gh api /orgs/digithings-ai/packages?package_type=container` empty)~~ **CORRECTED 2026-10-09 — the package exists.** All three probes were non-discriminating: the two `401`s are unauthenticated and a *private* package answers `401` exactly like an absent one, and the org package **list** route omits this package under every `visibility` filter even for an org admin. Measured with the by-name route: id `13179652`, `visibility: private`, `version_count: 28`, created 2026-07-05, last published 2026-09-21 (`v2.3.2`, `latest`). Whether any ACR image is a mirror of its GHCR counterpart has **not** been checked — that needs a digest comparison, which is separate work and is not claimed here.

So the lane being absent is not a missing workflow to restore. It is the absence of the whole chain, and the drift is the bill for it:

| Fact | Value |
|---|---|
| prod image | `datatapchatregistry.azurecr.io/digichat:v2.3.2` (digest `sha256:c5708729fea2…`) |
| prod revision | `digichat--0000007`, created 2026-09-21, still the only revision |
| `develop` version | `2.4.0` |
| commits behind prod on `apps/digichat` | **67** |
| last push to the ACR | **2026-09-21** — nothing since, not even a 2.4.0 image |

**And prod cannot be rolled back safely today.** Both ACAs run `activeRevisionsMode: Single` with **no readiness or liveness probes**. In Single mode all traffic goes to the latest revision, traffic weights are ignored, and a failed revision is not automatically demoted. Rolling back means writing the old image again, which mints *another* revision. A 67-commit redeploy is currently an unguarded hard cutover.

---

## 1. The decision: what lane

**Option A was chosen and is built.** Asked on DIG-1242 and answered 2026-10-06 by the local board: build lane only (`a_restore_build_only`), rehearse on dev first (`rehearse_dev`), and both prerequisites — probes plus traffic shifting, and an owned Azure principal — before any production write (`do_both`). This section records the option as decided, and the rest of the document is written against it.

### Option A — restore an image-build lane; keep the ACA promotion a documented human step *(chosen, shipped in this PR)*

The lane is [`.github/workflows/publish-digichat-image.yml`](../../.github/workflows/publish-digichat-image.yml). It is the deleted workflow (recoverable at `git show f54af7052^:.github/workflows/publish-digichat-image.yml`) re-derived for lane A, not a straight revert:

- triggers on the `digichat-v*` tag push, plus `workflow_dispatch` with an explicit `tag` input, and **refuses any tag that is not exactly `digichat-v<major>.<minor>.<patch>`** — the glob is wider than what the lane will publish, deliberately, so a malformed tag fails loudly instead of producing an image named after it. The deleted file's `branches: [main]` push trigger is **deliberately dropped** — a main-push build would publish `v2.4.0` carrying main's commit, and the idempotency guard would then skip the tag build, leaving the tag bound to the wrong commit;
- **refuses to publish when the tag version ≠ `apps/digichat/package.json` version** (the deleted workflow's own guard, and the check `scripts/check_digichat_image_binding.py` now enforces offline);
- idempotency guard via `docker manifest inspect`, with three outcomes rather than two: present ⇒ no-op, the registry's own `manifest unknown` ⇒ publish, and **anything else fails the run** — collapsing "absent" and "could not ask" into one answer would let a registry blip repush a released tag and change the digest under its name. No `force` input: a released tag is immutable;
- builds `context: .`, `file: apps/digichat/Dockerfile` — the repo root is required, it is an npm workspace whose lockfile and private `@digithings/design` dependency resolve only through the workspace link;
- passes `--build-arg DIGICHAT_REVISION=$commit` where `commit` is `git rev-list -n 1 <tag>`, **not** `github.sha`, so the image names the commit its tag points at (see §2);
- publishes `ghcr.io/digithings-ai/digichat:vX.Y.Z` (+ `:latest`);
- **re-reads the pushed image and runs `scripts/check_digichat_image_binding.py --facts -` against it**, so the lane proves its own output rather than asserting a build-arg was honoured.

**What it deliberately cannot do.** No `azure/login`, no `az`, no `environment:`, no `id-token: write`, no repository secret beyond `GITHUB_TOKEN` — the job holds `contents: read` and `packages: write` and nothing else. It cannot read `datatap-rg`, cannot name `datatapchatregistry`, and cannot write a revision. `tests/scripts/test_publish_digichat_image_workflow.py` asserts that boundary over the **whole parsed workflow** — every key, not a hand-picked subset — so widening it through `with:`, a step or job `env:`, a job-level `permissions:` or an `environment:` fails the suite rather than passing it.

The `az containerapp update` stays a human step, run from this document.

**Why this and not more:** the ACA belongs to DataTap. `docs/architecture/digichat-self-hosted-release.md` records "DataTap path | Client-side (out of repo)" and "digithings has no Azure"; a `git grep` for `eastus2|containerApps|jollygrass` on `develop` returns **0 hits**. DevOps' own rule is that the role ends at a PR into their repo and never deploys to DataTap. A workflow that holds write access to a production customer Container App would put us inside that boundary and make us a dependency of a client's uptime — for a deploy that happens a handful of times a year.

### Option B — add an ACA promotion workflow, gated *(not chosen)*

A second workflow: `workflow_dispatch` with an `image` + `environment` input, `environment: production` (required reviewer: Chris), Azure OIDC rather than a stored secret, then `--image …@sha256:…` digest-pinned, wait for the new revision `Running`, verify `/api/health` reports the expected version, fail loudly otherwise.

This is the right *eventual* shape — it is what makes promotion reproducible and reviewable. It needs a federated credential on `datatap-rg/digichat`, which is a real security decision. Security scoped one in PR #5179 without creating anything, then Option A was chosen, so that credential has no consumer: **DIG-1349 is moot unless the lane is revisited.** Nothing about lane A depends on it.

### Option C — document the hand-run and stop there *(rejected)*

Cheapest, and the option that produced the current state. 67 commits of drift is the argument against it: documenting a manual path does not make anyone follow it. The doc *plus* the binding check plus the dev rehearsal is the floor; stopping at the doc re-creates DIG-1242.

---

## 2. Tag → commit binding

**Git already binds the tag.** `digichat-v2.3.2` → `14639ac0ca9947beeb62d6b1971ebd69e3554be1` ("chore(digichat): release 2.3.2 (#4464)"). What is missing is the second hop: **image → commit**.

Two changes, both in this PR:

1. **`apps/digichat/Dockerfile`** now carries OCI annotations — `org.opencontainers.image.revision` (from `ARG DIGICHAT_REVISION`), `.version`, `.source`. A local build that omits the arg still works; labels come out empty.
2. **`scripts/check_digichat_image_binding.py`** asserts the binding. It is pure — facts in on stdin, verdict out — so every branch is testable offline and a registry outage can never read as a pass.

```bash
python3 scripts/check_digichat_image_binding.py --facts facts.json
# exit 0 = bound, 1 = a real finding, 2 = bad input
```

**Fail closed, deliberately.** An image with *no* revision annotation **fails**, not skips. That is the point: every image built before DIG-1242 looks exactly like that, so "no annotation" is the common case here and cannot be allowed to read as fine. An unresolvable tag fails for the same reason — nothing to bind against means the image revision proves only that *something* built it.

**Caller pitfall, verified against the live repo:** `package.json` must be read from **the tag's tree**, not the checkout. `develop` reads `2.4.0`, the `digichat-v2.3.2` tree reads `2.3.2`; auditing the running 2.3.2 image against the checkout reports a version mismatch that is true of the checkout and false of the image.

### Collecting the facts

The checker reads seven keys. Git supplies four of them; the image supplies three. Note the digest key is **`image_digest`**, not `digest`.

```bash
# --- from git: the tag's identity ---
TAG=digichat-v2.3.2                       # must exist; see the note below
COMMIT=$(git rev-list -n1 "$TAG")
PKG=$(git show "$TAG":apps/digichat/package.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')

# --- from the image: its own claim about what it is ---
IMG=datatapchatregistry.azurecr.io/digichat:v2.3.2
az acr login --name datatapchatregistry --expose-token >/dev/null   # or docker login
REV=$(docker pull -q "$IMG" | xargs docker inspect \
        --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}')
VER=$(docker inspect --format '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$IMG")
DIG=$(docker inspect --format '{{ index .RepoDigests 0 }}' "$IMG")  # registry@sha256:…

# --- compose and pipe; each command writes JSON, so `jq -n` assembles the object ---
jq -n \
  --arg version      "${VER:-$(git show "$TAG":apps/digichat/package.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')}" \
  --arg package_version "$PKG" \
  --arg tag          "$TAG" \
  --arg tag_commit   "$COMMIT" \
  --arg image_ref    "$IMG" \
  --arg image_revision "$REV" \
  --arg image_digest  "$DIG" \
  '{version:$version, package_version:$package_version, tag:$tag,
    tag_commit:$tag_commit, image_ref:$image_ref,
    image_revision:$image_revision, image_digest:$image_digest}' \
  | python3 scripts/check_digichat_image_binding.py --facts -
```

Two traps in that recipe, both hit while writing it:

- **`docker inspect` emits a JSON array**, so `docker inspect … | checker` fails with *"facts must be a JSON object"*. Always assemble with `jq -n`, or pass `--format` so each invocation prints a bare scalar.
- **`cmd1; cmd2 | checker` pipes only `cmd2`.** Use `&&` or collect into variables first, or the checker silently validates the wrong thing.

> **The tag must exist.** `git tag -l 'digichat-v*'` currently stops at `digichat-v2.3.2` — there is **no `digichat-v2.4.0` tag**, even though `develop` already reads `2.4.0`. Binding a 2.4.0 image therefore requires cutting `digichat-v2.4.0` first (release-please does this on develop, per [`RELEASES.md`](../../RELEASES.md)); until then `git rev-list -n1` returns empty and the check fails on a missing tag commit — correctly, since there is nothing to bind against.

---

## 3. Environment ledger

| | **prod** | **dev** |
|---|---|---|
| resource group | `datatap-rg` | `datatap-dev-rg` |
| app | `digichat` | `digichat` |
| revision mode | **`Single`** | **`Single`** |
| probes | **none** | **none** |
| image | `digichat:v2.3.2` | `digichat:v2.3.3` |
| revisions | 1 — `digichat--0000007` (2026-09-21) | 1 — `digichat--0000040` (2026-09-28) |
| scale | 0.5 cpu / 1Gi, min 1 / max 3 | min 0 / max 2, cooldown 300 |
| fqdn | `digichat.jollygrass-53364db9.eastus2.azurecontainerapps.io` | `digichat.icymeadow-18dda7db.eastus2.azurecontainerapps.io` |
| `/api/health` | `200 {"ok":true,…,"version":"2.3.2"}` | `200 {"ok":true,…,"version":"2.3.3"}` |
| `/healthz` | **404** | **404** |

Subscription `fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0` ("DataTap WebSite"), region East US 2.

### `/healthz` returns 404 on both — and that is expected, not a bug

The route exists on `develop` (`apps/digichat/src/app/healthz/route.ts`, added `916c4b5d5`, 2026-09-28). It is simply **not in the running builds** — both predate it. An earlier check of `/api/healthz` 404'ing was mine to own: the route is at `/healthz`, not `/api/healthz`, and I looked up the wrong path before reading the tree. Either way the running images are pre-route.

This matters for the promotion below: **`/healthz` only becomes a valid probe path *after* a deploy that carries `916c4b5d5`.** Until then, `/api/health` is the only check available.

### What 2.4.0 changes about startup

`src/instrumentation.ts` on `develop` runs three initializers before serving. Each is a real deploy risk worth knowing:

| Initializer | Behaviour | Risk to this deploy |
|---|---|---|
| `assertDevAuthDisabledInProduction` | throws if `NODE_ENV=production` **and** `DIGICHAT_DEV_AUTH=1` | **none** — `DIGICHAT_DEV_AUTH` is unset on both ACAs |
| `initDigichatConfigAtStartup` | **fails closed** — throws if there is no config file *and* no `DIGICHAT_EMBED_TENANTS` | **none** — `DIGICHAT_EMBED_TENANTS` is set on the container, sourced from the `embed-tenants` secret |
| `initLicenseStateAtStartup` | fail-open; `unlicensed` still serves | **none** — no license credential on the ACA, so state is `unlicensed` and serving continues |
| `startLicenseHeartbeat` | 24h timer to digikey `/v1/licenses/heartbeat` | **none** — `unlicensed` containers never start a timer |

`GET /api/health` reports `license_status` but never lets it affect `ok`. So a 2.4.0 image on these ACAs should come up healthy with `license_status: "unlicensed"`, `database: "skipped"` (no `DIGICHAT_DATABASE_URL` on either ACA), and only `service` in `checks` — because `DIGICHAT_ENABLED_SERVICES=foundry` names none of the four downstream capabilities, so they are all skipped rather than pinged.

---

## 4. Promotion runbook

> **Every command here is a write to a customer's Azure. Do not run any of it without the approval named at the top of the step.** The prod step additionally requires Chris per the Platform hard rules; DevOps does not perform it.

### The `--secrets` footgun — read this first

Both ACAs declare exactly two secrets, `auth-secret` and `embed-tenants`, and **both hold inline values** rather than pointing at a Key Vault secret (`secretRef: null` on the secret entry itself). The container still references them by name via `secretRef` — that is how `AUTH_SECRET` and `DIGICHAT_EMBED_TENANTS` resolve to them. `az containerapp show` returns nothing usable for them and `az containerapp secret show` reports only `hasValue:false`, so the values are not round-tripped by the usual read paths. **They are not, however, unreadable:** `az containerapp secret list --show-values` returns them in cleartext to any principal holding `Microsoft.App/containerApps/listSecrets/action`, and the two dormant `Contributor` principals on these apps would hold it. Treat them as readable by anyone who can authenticate as a principal with that role. See [`credential-ownership.md`](credential-ownership.md).

Consequence: **never pass `--secrets` to a promote.** Re-declaring the secret list requires the original values, which the read paths above do not give you. A promote that re-declares them with empty or placeholder values destroys working auth and embed configuration, and the app boots into a login nobody can explain. The image update does not need them — `az containerapp update --image` patches the template and leaves the rest alone.

If the secret list is ever genuinely lost, it is **not** unrecoverable: `az containerapp secret list --show-values` reads both values back, so rotation never depends on someone remembering the original out of band. That is a credential-ownership question, not a deploy question — tracked in the Security child issue DIG-1344.

**There is now a check for it** (DIG-1344), and it belongs at the top of every promote. It compares a fingerprint of each live value against the recorded inventory, so a secret that changed outside the inventory fails loudly instead of being discovered during an incident:

```bash
python3 scripts/digichat_aca_secret_detector.py          # exit 0 clean, 1 = a finding
python3 scripts/digichat_aca_secret_detector.py --offline # lock + expiry only, no Azure call
```

Exit 1 means the digichat secret inventory is not trustworthy — stop and read [`credential-ownership.md`](credential-ownership.md) before promoting. It prints names, lengths and digests only; no value is ever printed.

It fails on the whole drift family (`drift`, `missing`, `unbound`, `migrated`, `expired`, `lock`) **and** on `unrecorded` — a secret added to the app that has no owner and no fingerprint row in [`digichat-aca-secret-fingerprints.json`](digichat-aca-secret-fingerprints.json). Env vars bound with a plain `value` rather than a `secretRef` are ordinary config and do not trip it, so a new `PORT=…` or `NODE_ENV=…` is not a finding.

### Step 0 — preflight (read-only)

```bash
SUB=fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0
RG=datatap-rg          # datatap-dev-rg for the rehearsal
APP=digichat

az containerapp show -n "$APP" -g "$RG" --subscription "$SUB" \
  -o json | jq '{mode: .properties.configuration.activeRevisionsMode,
                image: .properties.template.containers[0].image,
                probes: .properties.template.containers[0].probes,
                secrets: [.properties.template.secrets[].secretRef]}'

az containerapp revision list -n "$APP" -g "$RG" --subscription "$SUB" \
  -o table --query '[].{name:name,active:active,state:properties.runningState,image:properties.template.containers[0].image}'

az acr repository show-tags --repository digichat \
  --registry datatapchatregistry --subscription "$SUB" \
  -o table --query '[].{name:name,digest:digest[0:19],created:createdTime}'
```

Record the current revision name and image digest. That is the rollback target.

### Step 1 — rehearsal on **dev** (`datatap-dev-rg`)

Requires the 2.4.0 image in the ACR. **There is none** — nothing has been pushed since `v2.3.3` (2026-09-21). Getting one there takes two steps, in this order, and the second one is the gap the build lane does not close:

**1. Publish (CI, lane A).** Two routes, and a rehearsal wants the first one.

*Rehearsal — build from a ref, no release tag.* Dispatch the lane with `ref`
set to the branch or sha holding the change (`gh workflow run
publish-digichat-image.yml -f ref=develop`). It publishes exactly one name:

```
ghcr.io/digithings-ai/digichat:sha-<12 chars of the commit>
```

It never takes a `vX.Y.Z` name and never moves `:latest`. Every
`--source`/`-t` in step 2 below then uses `sha-<commit>` in place of
`v${VERSION}`.

*Release — cut the tag.* A real release still goes through the tag, because a
tag names one version and one commit and that is what makes the binding check
meaningful:

```bash
git tag digichat-v2.4.0 <commit carrying version 2.4.0 in apps/digichat/package.json>
git push origin digichat-v2.4.0
```

**No `digichat-v2.4.0` tag exists today** (`git tag -l 'digichat-v*'` stops at `digichat-v2.3.2`) even though `develop` already reads `2.4.0`. Cutting it is the release decision, not a deploy step, and it is why the rehearsal uses `ref` instead.

**2. Import into the ACR (human, Azure write).** The Container Apps pull from `datatapchatregistry.azurecr.io`, **not** from GHCR. Nothing in this repository bridges those two registries: the old `datatap-web` lane that did the GHCR→ACR import was client-side and out of repo, and a `git grep` for `datatapchatregistry` / `azurecr.io` across `develop` returns 0 hits in any workflow. So the lane stops at GHCR, and a human runs the import:

```bash
# Azure write. Needs a principal with AcrImport on datatapchatregistry.
# GHCR is a foreign registry, so --username/--password are required: the import
# runs server-side and has no GitHub session to borrow. Use a classic PAT with
# read:packages. If the package is public these can be omitted, but do not
# assume that — org default visibility decides, and `ghcr.io/digithings-ai/digichat`
# is private (verified 2026-10-09), so assume the credentials are required.
az acr import -n datatapchatregistry --subscription "$SUB" \
  --source "ghcr.io/digithings-ai/digichat:v${VERSION}" \
  --username "$GHCR_USER" --password "$GHCR_PAT" \
  -t "digichat:v${VERSION}" -o none
```

`--source` takes one fully-qualified value (`registry/repository:tag`) — there is no two-token form, and `--registry` is only for a source that is itself an ACR. The destination is `-t/--image`, not `--tag`. Import is a no-op-overwrite hazard in its own right: without `--force` it refuses an existing tag, which is the behaviour to keep on a release tag.

Import is by digest-preserving copy, so the `org.opencontainers.image.revision` label the build lane set survives it — re-run `check_digichat_image_binding.py` against the **ACR** digest afterwards to prove that rather than assume it. This step is an Azure write on a customer resource and belongs to the owned principal that DIG-1292's `do_both` answer requires; it is not something the pipeline does.

> **Rehearsal gate: do not start until an ACR image exists whose `org.opencontainers.image.revision` names the 2.4.0 release commit.** A rehearsal on an unlabelled image validates the mechanism, not the artifact.

```bash
DIGEST=sha256:<full digest from the ACR ledger>   # pin, never the tag
az containerapp update -n digichat -g datatap-dev-rg --subscription "$SUB" \
  --image "datatapchatregistry.azurecr.io/digichat@$DIGEST" \
  -o none
```

Then verify — do not skip to the next step on "it looks fine":

```bash
az containerapp revision list -n digichat -g datatap-dev-rg --subscription "$SUB" \
  -o table --query '[].{name:name,active:active,state:properties.runningState}'

curl -sS https://digichat.icymeadow-18dda7db.eastus2.azurecontainerapps.io/api/health
# expect: ok=true AND version="2.4.0" AND license_status="unlicensed"
# AND checks.database="skipped" AND no digigraph/digiquant/digitrace/digisearch keys
```

`version` is the load-bearing field: it comes from `DIGICHAT_VERSION`, baked from `package.json` at build time, so it proves the new build is actually serving rather than a cached old one. **`/healthz` should start answering `{"ok":true}` here** — this is the rehearsal's chance to confirm the probe path exists before prod depends on it.

Rollback on dev: same command with `v2.3.3`'s digest (`sha256:fc06e0a57902…`).

### Step 2 — prod (`datatap-rg`) — **Chris only**

**Prerequisites, all of them:**

- [ ] dev rehearsal completed, `/api/health` reported `version=2.4.0`, and the outcome recorded on the issue;
- [ ] binding check passes for the exact image being promoted, digest supplied:
      `python3 scripts/check_digichat_image_binding.py --facts facts.json` → exit 0.
      (Supply `image_digest`; without it the check still exits 0 but only proves the
      *binding*, leaving the tag mutable under you. The recipe in §2 sets it.)
- [ ] the prod `digichat@<digest>` pull is authorised (system identity has ACR pull; the image must be in `datatapchatregistry`);
- [ ] **probes are a known-accepted risk.** With `Single` mode and no probes there is no automatic rollback. Either accept that explicitly, or land the probe change first (child issue);
- [ ] Chris has approved this specific digest, in the issue, in writing;
- [ ] the rollback digest is written down and in hand.

```bash
az containerapp update -n digichat -g datatap-rg --subscription "$SUB" \
  --image "datatapchatregistry.azurecr.io/digichat@$DIGEST" -o none
```

**No `--secrets`.** See the footgun above.

Verify immediately, and treat the version field as the gate:

```bash
az containerapp revision list -n digichat -g datatap-rg --subscription "$SUB" \
  -o table --query '[].{name:name,active:active,state:properties.runningState}'

curl -sS https://digichat.jollygrass-53364db9.eastus2.azurecontainerapps.io/api/health
curl -sS https://digichat.jollygrass-53364db9.eastus2.azurecontainerapps.io/healthz
```

### Step 3 — rollback

There is no re-weight rollback in `Single` mode. Roll back by **writing the previous image again**:

```bash
az containerapp update -n digichat -g datatap-rg --subscription "$SUB" \
  --image "datatapchatregistry.azurecr.io/digichat@sha256:c5708729fea26c0689057beda8d83a0da9f4ad6c59752871bded2c108a9f1e39" \
  -o none   # digichat:v2.3.2
```

This mints a **further** revision rather than reactivating `--0000007` — read the actual name back from `az containerapp revision list` rather than predicting it, because Step 2 has already moved the counter on. The old revision keeps consuming quota until it is deactivated, so prune after a successful rollback.

**Rollback is slower and blunter than a traffic shift.** That is the concrete cost of `Single` mode plus no probes, and the reason the probe change is a prerequisite rather than a follow-up.

---

## 5. Release ledger

The ACR is the ledger of record for what is deployed. Digests below are verified 2026-10-06; the full ladder is reproducible with the `az acr repository show-tags` command in Step 0.

| Image | Digest (prefix) | Pushed | Running on |
|---|---|---|---|
| `v2.3.2` | `sha256:c5708729fea2` | 2026-09-21T11:47Z | **prod** (`digichat--0000007`) |
| `v2.3.3` | `sha256:fc06e0a57902` | 2026-09-21T20:46Z | dev (`digichat--0000040`) |

Nothing newer. No 2.4.0 image exists in any registry.

---

## 6. Known gaps

| Gap | State |
|---|---|
| **No probes on either ACA** | Open — DIG-1292. A production-affecting behavior change on a customer resource, with its own approval and its own rehearsal. Chosen as a prerequisite (`do_both`), not a follow-up: in `Single` mode with no probes a failed revision takes all traffic and there is nothing to demote it. |
| **No owned Azure principal for the promotion** | Open — the other half of `do_both`. Security established that principal `44cfda92-…` is **dormant** (no credential at all) rather than a usable deploy identity, so the writes in §4 currently have no owned identity to run as. |
| **No federated CI credential** | Moot. Scoped in PR #5179 for lane B; lane A was chosen, so DIG-1349 has no consumer. Revisit only if the ACA write is ever automated. |
| **No GHCR→ACR import lane** | Open, and the honest limit of lane A. The build lane publishes to GHCR; the ACAs pull from ACR; the bridge is a human `az acr import` documented in §4 Step 1. Nothing in this repository can do that hop — the old importer was client-side and out of repo. Until it is automated, "build" and "available to promote" remain two human actions. The rehearsal path narrows this only in that it now produces an artifact to hand to that human: **§4 Step 1 promotes the image `ghcr.io/digithings-ai/digichat:sha-<commit>`, not a tag.** |
| **`/healthz` 404s in both running builds** | Self-resolving: any deploy carrying `916c4b5d5` adds the route. Recorded so nobody reads the 404 as a regression. |
| ~~**No build lane**~~ | **Closed by PR #5214** (DIG-1294). `.github/workflows/publish-digichat-image.yml` is back, tag-triggered, revision-labelled and self-verifying. |
| ~~**No rehearsal artifact before `digichat-v2.4.0` exists**~~ | **Closed.** The lane took only a release tag, and `digichat-v2.4.0` does not exist, so §4 Step 1 had nothing to promote. `workflow_dispatch` now also takes a `ref` and builds a rehearsal image named `sha-<12 chars of the commit>`. It never takes a `vX.Y.Z` name and never moves `:latest` — see the workflow header for why a build that is not the tag's commit must not take a release name. |
| ~~**Nothing proves the image boots**~~ | **Closed.** Every build — release or rehearsal — is loaded into the runner, started, and watched until `/healthz` answers 200 with `ok=true` and `/api/health` reports the version it was built as. The push is a separate step gated on that probe. Prod is `Single` mode and a release tag is immutable, so an unbootable image published under a release name cannot be walked back by re-running the lane. |
| ~~**Principal `44cfda92-…`**~~ | **Closed by DIG-1293** (2026-10-06, read-only). It is the service principal for app registration `datatap-digichat-deploy` (`be54468d-2f66-4aeb-a231-5db0b6e58789`), created 2026-08-09 by the shared account `datatap@datatapstream.onmicrosoft.com`. It holds `Contributor` on both ACAs and on the ACR, and it has **no credential at all** — 0 keys, 0 passwords, 0 federated credentials. Dormant, not deleted. Registered in [`credential-ownership.md`](credential-ownership.md) with the owner and the required roles for a future federated credential. |

---

## 7. Corrections to existing docs

The false claim — that `ghcr.io/digithings-ai/digichat` is published — was **not** confined to two files. A fresh-context review found roughly thirteen more sites, written when `publish-digichat-image.yml` was live and left behind when the strict-essentials cut removed it (`f54af7052`, 2026-10-01).

Restoring the lane splits those claims in two, and the distinction matters:

- **Claims that a lane was removed and never replaced** are now false — the lane is back. Corrected.
- ~~**Claims that the GHCR package exists** are still false.~~ **Also corrected 2026-10-09: the package exists** — id `13179652`, `visibility: private`, `version_count: 28`, created 2026-07-05, last published 2026-09-21 with `v2.3.2` and `latest`. The 2026-10-06 check that said otherwise could not tell a *private* package from an absent one: two of its three probes were unauthenticated (`401` = "auth required", which a private package returns identically), and the third, `gh api /orgs/digithings-ai/packages?package_type=container`, returns `[]` for this package under every `visibility` filter even for an org admin. The discriminating route is the by-name one: `gh api /orgs/digithings-ai/packages/container/digichat`. What the earlier check got *right* is that nothing has published since 2026-09-21 and the tag ladder still stops at `digichat-v2.3.2`. Restoring a workflow does not create a package: nothing publishes until a `digichat-v*` tag is pushed, and the ladder stops at `digichat-v2.3.2`. So `ghcr.io/digithings-ai/digichat` does not exist today, and will not until someone cuts the next release tag.

Any doc corrected in this PR that tells a reader to `docker pull ghcr.io/digithings-ai/digichat` must keep saying **that this works once the tag lands**, not that it works now.

**Corrected in PR #5167** — the sites that cause a failed command or a wrong belief about whether a lane exists:

| Site | Was |
|---|---|
| `apps/digichat/OPERATIONS.md` § Release artifacts | "Install digichat from GHCR" |
| `docs/architecture/digichat-self-hosted-release.md` §1 | GHCR row "Exists"; "no GHCR→ACR mirror step exists" |
| `docs/agents/CI_CONVENTIONS.md` | `publish-digichat-image.yml` and `release-please-digichat.yml` listed **Working** — both deleted. This one mattered most: it is the doc whose job is to say which workflows exist. |
| `docs/digichat/INSTALL.md` | `docker pull ghcr.io/…` as the primary install unit |
| `docs/digichat/RELEASE-SMOKE.md` | a smoke checklist whose steps cannot run |
| `apps/digithings-web/lib/sharedDocs.ts`, `apiDocs.ts` | **public site copy** asserting digichat "is already on GHCR" |

**Corrected in this PR** — the lane-restoration half:

| Site | What it now says |
|---|---|
| `docs/agents/CI_CONVENTIONS.md` | `publish-digichat-image.yml` is **Working (restored)** with its real triggers, its guards, and the lane-A boundary |
| `docs/ops/credential-ownership.md` | DIG-1242's lane question is **answered** (Option A), not open; DIG-1349 is moot |
| this document | §1 records the decision and the shipped workflow; §4 Step 1 documents the ACR import; §6 closes the build-lane gap |

**Still false — enumerated, not yet swept** (child issue). Listed so the next person does not rediscover them:

- **Runnable code**: `infra/digichat-release/compose.digichat-release.yml`, `compose.profile-a.yml`, `compose.profile-a-bundle.yml`, `compose.profile-b.yml`, `infra/self-host/compose.ghcr.yml` — all set `image: ghcr.io/digithings-ai/digichat:…`. `make up-ghcr-digichat` therefore fails at pull.
- **Docs**: `docs/vision/api/guide-digichat-install.md`, `guide-self-host.md`, `docs/vision/api/digichat-api.md`, `infra/digichat-release/README.md`, `docs/digichat/ONBOARDING.html`, `docs/architecture/digichat-self-host-picks-fit.md`.
- **Historical, needs judgement not correction**: `RELEASES.md:80,82` and `BRANCHING.md:189` tell you not to delete `ghcr.io/digithings-ai/digichat:v0.9.3` because clients consume it. The package is gone from GHCR, so that advice can no longer be verified from this repo — but whether DataTap still depends on it is a DataTap question, not ours.
- **`openwiki/digichat/operations.md:246`** repeats the claim. `openwiki/` is generated; per `AGENTS.md` it regenerates from source, so fix the source and let the weekly run pick it up rather than hand-editing.

To find the current set at any time:

```bash
git grep -n 'ghcr.io/digithings-ai/digichat' -- . ':!docs/superpowers/plans/**'
```

`docs/superpowers/plans/**` is excluded deliberately: those are dated plan records of what was intended at the time, not current-state claims.