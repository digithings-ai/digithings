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

Half the registry is ad-hoc debugging under names no workflow produced. The one tag that embeds a git SHA — `v2.0.0-main.7263272` — shows commit binding was attempted once and abandoned. `ghcr.io/digithings-ai/digichat` **does not exist** (verified three ways: anonymous token `401`, `GET /v2/…/tags/list` `401`, `gh api /orgs/digithings-ai/packages?package_type=container` empty), so the ACR images are not mirrors of a published artifact either. They were built on someone's laptop and pushed by hand.

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

Three options. The recommendation is **A now, escalate to B only if Chris wants the ACA write automated**.

### Option A — restore an image-build lane; keep the ACA promotion a documented human step *(recommended)*

Restore the deleted `publish-digichat-image.yml` (recoverable at `git show f54af7052^:.github/workflows/publish-digichat-image.yml`), adapted:

- triggers on the `digichat-v*` tag push, plus `workflow_dispatch`;
- **refuses to publish when the tag version ≠ `apps/digichat/package.json` version** (the deleted workflow's own guard, and the check `scripts/check_digichat_image_binding.py` now enforces offline);
- idempotency guard via `docker manifest inspect` (already-published ⇒ no-op);
- builds `context: .`, `file: apps/digichat/Dockerfile` — the repo root is required, it is an npm workspace whose lockfile and private `@digithings/design` dependency resolve only through the workspace link;
- passes `--build-arg DIGICHAT_REVISION=$GITHUB_SHA` so the image names its own commit (see §2);
- publishes `ghcr.io/digithings-ai/digichat:vX.Y.Z` (+ `:latest`).

The `az containerapp update` stays a human step, run from this document.

**Why this and not more:** the ACA belongs to DataTap. `docs/architecture/digichat-self-hosted-release.md` records "DataTap path | Client-side (out of repo)" and "digithings has no Azure"; a `git grep` for `eastus2|containerApps|jollygrass` on `develop` returns **0 hits**. DevOps' own rule is that the role ends at a PR into their repo and never deploys to DataTap. A workflow that holds write access to a production customer Container App would put us inside that boundary and make us a dependency of a client's uptime — for a deploy that happens a handful of times a year.

### Option B — add an ACA promotion workflow, gated

A second workflow: `workflow_dispatch` with an `image` + `environment` input, `environment: production` (required reviewer: Chris), Azure OIDC rather than a stored secret, then `--image …@sha256:…` digest-pinned, wait for the new revision `Running`, verify `/api/health` reports the expected version, fail loudly otherwise.

This is the right *eventual* shape — it is what makes promotion reproducible and reviewable. It needs a federated credential on `datatap-rg/digichat`, which is a real security decision (child issue). Build the lane first; escalate to this when Chris wants the ACA write automated.

### Option C — document the hand-run and stop there *(not recommended)*

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

```bash
TAG=digichat-v2.3.2
COMMIT=$(git rev-list -n1 "$TAG")
PKG=$(git show "$TAG":apps/digichat/package.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])')
```

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
| `initDigichatConfigAtStartup` | **fails closed** — throws if there is no config file *and* no `DIGICHAT_EMBED_TENANTS` | **none** — `embed-tenants` is set via `secretRef` |
| `initLicenseStateAtStartup` | fail-open; `unlicensed` still serves | **none** — no license credential on the ACA, so state is `unlicensed` and serving continues |
| `startLicenseHeartbeat` | 24h timer to digikey `/v1/licenses/heartbeat` | **none** — `unlicensed` containers never start a timer |

`GET /api/health` reports `license_status` but never lets it affect `ok`. So a 2.4.0 image on these ACAs should come up healthy with `license_status: "unlicensed"`, `database: "skipped"` (no `DIGICHAT_DATABASE_URL` on either ACA), and only `service` in `checks` — because `DIGICHAT_ENABLED_SERVICES=foundry` names none of the four downstream capabilities, so they are all skipped rather than pinged.

---

## 4. Promotion runbook

> **Every command here is a write to a customer's Azure. Do not run any of it without the approval named at the top of the step.** The prod step additionally requires Chris per the Platform hard rules; DevOps does not perform it.

### The `--secrets` footgun — read this first

Both ACAs declare exactly two secrets, `auth-secret` and `embed-tenants`, and **both are inline-valued** (`secretRef: null`). `az` redacts inline values on read, so they **cannot be round-tripped**: `az containerapp show` returns no usable value, only `hasValue:false`.

Consequence: **never pass `--secrets` to a promote.** Re-declaring the secret list requires the original values, which are not recoverable from Azure. A promote that re-declares them with empty or placeholder values destroys working auth and embed configuration, and the app boots into a login nobody can explain. The image update does not need them — `az containerapp update --image` patches the template and leaves the rest alone.

If the secret list is ever genuinely lost, it must be re-supplied by whoever holds the values out of band. That is a credential-ownership question, not a deploy question — tracked in the Security child issue.

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

Requires the 2.4.0 image in the ACR. **There is none** — nothing has been pushed since `v2.3.3` (2026-09-21), so the rehearsal is blocked on §1 Option A shipping a build lane, or on one deliberate hand-build whose digest is then recorded here.

> **Rehearsal gate: do not start until an image exists in the ACR whose `org.opencontainers.image.revision` is the 2.4.0 release commit.** A rehearsal on an unlabelled image validates the mechanism, not the artifact.

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
- [ ] binding check passes for the exact digest being promoted:
      `python3 scripts/check_digichat_image_binding.py --facts facts.json` → exit 0;
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

This mints a further revision (`digichat--0000009`) rather than reactivating `--0000007`. The old revision keeps consuming quota until it is deactivated, so prune after a successful rollback.

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

## 6. Known gaps this PR does not close

Each has a child issue on DIG-1242 rather than being folded in here.

| Gap | Why it is separate |
|---|---|
| **No probes on either ACA** | A production-affecting behavior change on a customer resource. Needs its own approval and its own rehearsal. |
| **No federated Azure credential** | Adding write access to a customer Container App is a security decision with an owner and a rotation path ([`credential-ownership.md`](credential-ownership.md)). |
| **No build lane** | Depends on the §1 decision and on the release-tagging flow, which a human owns. |
| **`/healthz` 404s in both running builds** | Self-resolving: any deploy carrying `916c4b5d5` adds the route. Recorded so nobody reads the 404 as a regression. |
| **Principal `44cfda92-…`** | Display name unknown, and whether its credentials still exist is unverified. Belongs in the credential inventory. |

---

## 7. Corrections to existing docs

Two documents assert a GHCR artifact that does not exist. Both were written when `publish-digichat-image.yml` was live and left behind when the strict-essentials cut removed it (`f54af7052`, 2026-10-01):

- `apps/digichat/OPERATIONS.md` § Release artifacts — "Install digichat from GHCR".
- `docs/architecture/digichat-self-hosted-release.md` §1 — the GHCR row and the "GHCR→ACR mirror" DataTap path.

Corrected in this PR to point here. The GHCR rows are the intended target state of the restored lane, not the current one.