# 0029. One secrets system of record, synced outward (1Password recommended)

## Status

Proposed — 2026-09-17. The vendor is a human decision: this ADR records the
recommendation and the plan, not an adopted one. Until accepted, nothing here
authorises deleting a live secret or creating a vendor account.

**Deciders:** repo owner (vendor + spend). **Evidence base:** [secrets
inventory](../ops/SECRETS_INVENTORY.md) (names, locations, R1–R13) and [secrets
rotation runbook](../ops/SECRETS_ROTATION.md) (what rotation costs today).

## Context

The stack has three disjoint secret surfaces and no system of record:

- **Cloudflare.** Three Workers hold 27 `secret_text` secrets (digichat 10,
  stack 16, cron 1) plus the `digithings-web` Pages project. Worker secrets are
  write-only: `wrangler secret list` returns names and type, never values
  ([`../ops/SECRETS_INVENTORY.md`](../ops/SECRETS_INVENTORY.md), "Storage
  surfaces"). Each Container receives only what its Worker's `envVars` whitelist
  forwards — the stack Worker runs two: `DigiStackContainer`
  (`cloudflare/digithings-stack-cloudflare/src/index.ts:60-112`) and
  `DigiQuantMcpContainer` (`:177-185`) — and a secret that is `put` but absent
  from `envVars` is a silent drop (R4).
- **GitHub.** 72 workflows, only 4 declare `environment: production`
  (`SECRETS_INVENTORY.md:158`); ~42 repo secrets + 6 vars, repo-scoped, so any
  workflow on any branch can read production credentials (R13).
- **Local / Python.** `digikey`, `digigraph`, `digiquant`, `digisearch`,
  `digismith`, `digivault`, `digibase`, `digillm` read plain env vars; dev uses
  gitignored `.env` / `.dev.vars`. `digikey` owns the JWT/API-key model, and
  `DIGIKEY_PRIVATE_KEY_PEM` has **no rollover path** — one static `kid`, one
  key in JWKS (`digikey/src/digikey/jwt_issue.py:88-99`, R1).

Two facts constrain any solution more than vendor features do.

**1. Cloudflare Secrets Store cannot be a Container's env source today.** The
binding's value is read **asynchronously** (`env.SECRET.get()`), while the
`Container.envVars` class field is evaluated **synchronously** at instance
start; the Cloudflare docs say so directly — "we can't set the secret store
binding … as defaults here, as getting their values is asynchronous"
([containers env-vars example](https://developers.cloudflare.com/containers/examples/env-vars-and-secrets/)).
digichat autostarts via `container.fetch(request)`
(`cloudflare/digichat-cloudflare/src/index.ts:90`) and the stack's
`startAndWaitForPorts` calls pass no `startOptions.envVars`
(`cloudflare/digithings-stack-cloudflare/src/index.ts:124`), so both rely on the
static field. Secrets Store *can* reach a container only through the async
per-instance path; adopting it means changing the start call, not just the
wrangler config.

**2. A running Container keeps its boot-time env until recycled.** `wrangler
deploy` does not roll it; the only working lever is bumping
`SHARED_DIGICHAT_CONTAINER_ID` (`cloudflare/digichat-cloudflare/src/paths.ts:22`)
or `SHARED_STACK_CONTAINER_ID`
(`cloudflare/digithings-stack-cloudflare/src/ports.ts:37`) — R5. A rotated
secret can look rotated in `secret list` while the old value stays live.

Secrets Store is also **still open beta** (["Available in open
beta"](https://developers.cloudflare.com/secrets-store/), docs updated
2026-08-14), one store per account, ≤1024-byte values, and its value is not
readable after save — the same write-only property as a Worker secret. It buys
cross-Worker reuse and account-level audit, not readback. No published price was
found.

## Decision

Adopt **one external system of record that fans out into every surface**, and
recommend **1Password** for it: a vault item per logical credential, machine
access through **Service Accounts** (`op read` / `op run` /
`1password/load-secrets-action`), and a repo-owned sync job that writes Cloudflare
Worker secrets and GitHub secrets from the vault. Local dev and Python services
get values from `op run`; they keep reading plain env vars and take no SDK
dependency.

Cloudflare Secrets Store is deferred, not rejected: it is a candidate *dedup
layer for Worker-bound secrets only*, once it is GA and its values are readable.
It is not a system of record for GitHub, Python, or local, and it is explicitly
out of Phase 1.

This is a **recommendation**; the alternatives table below is the owner's menu.
If the owner prefers Infisical or Doppler, only Phase 1's vendor swaps — Phases
0, 2, and 3 are vendor-neutral and stand.

## Decision matrix

Ratings are for *this* stack (Cloudflare + GitHub + Python + one team), not in
general. `strong` / `partial` / `weak` / `none`; sources are linked or marked
unverified.

| Option | Readback + versioning | Rotation | Workers / DO | Container env | GH Actions | Local dev | Python | Audit | Cost | Lock-in | Adoption |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1Password** | strong (item history) | strong (edit + service acct) | partial (custom sync) | partial (still needs roll) | strong ([`load-secrets-action`](https://github.com/1Password/load-secrets-action)) | strong (`op run`) | strong (env; SDK optional) | strong (events) | ~$8/user/mo Business ([pricing](https://1password.com/pricing/business)) | medium (proprietary, thin CLI) | low (likely already held) |
| **Cloudflare Secrets Store** | **none** (write-only) | weak (re-put, no dual-read) | strong (native binding) | **partial** (async per-instance only) | none (CF-only) | none | none | partial (account audit) | unverified, no published price; open beta | high (CF account) | low |
| **Infisical** | strong (Pro) | strong (Pro DB / Advanced) | partial (Agent/API) | partial | strong (official action) | strong (`infisical run`) | strong (SDK + Agent) | strong (90d Pro) | free ≤5 identities; [Pro $18/identity/mo](https://infisical.com/pricing); self-host free | low (MIT core) | medium |
| **Doppler** | strong | strong (Team+) | partial | partial | strong (official action) | strong (`doppler run`) | strong (SDK/CLI) | 3d free / 90d Team | free 3 users, machines free; Team [$21/user/mo](https://www.doppler.com/pricing) | medium-high (on-prem = Enterprise) | medium |
| **Vault / OpenBao** | strong | strong (dynamic) | partial (custom) | partial (custom) | partial (OIDC) | medium (agent) | medium (`hvac`) | strong | OSS free, **ops-heavy** | low ([OpenBao](https://openbao.org/), MPL) | high |
| **SOPS + age in-repo** | strong (git) | weak (re-encrypt) | partial | partial | partial (decrypt in CI) | partial (key file) | partial (decrypt→env) | partial (git) | free | none | low-medium |
| **AWS Secrets Manager / SSM** | strong | strong (Lambda) | none (no native CF) | custom | strong (OIDC) | medium | strong (boto3) | strong | [$0.40/secret/mo + calls](https://aws.amazon.com/secrets-manager/pricing) | high (AWS) | high (no AWS account today) |

Why 1Password wins on this stack: it is the only option that covers all three
surfaces with **zero always-on infrastructure**, its machine path (service
account → CLI) works unchanged for CI, local dev, and Python, and its marginal
cost is near zero if the password manager the audit already notes holding the
signing key (`SECRETS_INVENTORY.md:40`) is 1Password — **unverified which
product**. Infisical is the pick if the owner wants open-source/self-host and
native syncs; note that self-hosting is a new external service dependency, which
[AGENTS.md](../../AGENTS.md) routes through the human gate.

## Alternatives considered

1. **Cloudflare Secrets Store as the whole answer.** Rejected for now: covers
   only Workers/AI Gateway, cannot be the container's static env source, is
   write-only, one store per account, open beta, no CI/local/Python story.
2. **GitHub Environments + OIDC to provider-native stores (AWS SM).** Rejected:
   the stack has no AWS account; it fixes GitHub but not Cloudflare/Python/local;
   adds a cloud account and IAM surface.
3. **SOPS + age in-repo.** Rejected: cheap and git-native, but no access control,
   no rotation automation, and it does not remove the container roll. Good
   fallback, not a system of record.
4. **Vault / OpenBao.** Rejected on ops cost: dynamic secrets are attractive for
   `DIGIKEY_DATABASE_URL`, but a small team maintaining an HA sealed store buys
   more risk than it removes. Revisit only with a second operator.
5. **Do nothing but run the runbook.** Rejected: the audit shows duplicate
   copies, dead secrets, and no readback; runbook discipline does not fix drift.

## Phased migration plan

### Phase 0 — stop the bleeding (no vendor)

**Goal:** remove dead/duplicated secrets and close the scanning hole before any
new tooling.

1. Delete the dead and misdirected secrets the audit found: digichat
   `CHEAPERINFERENCE_API_KEY` / `OPENROUTER_API_KEY` (put but not in `envVars`,
   R4), the dead Pages `OPENROUTER_API_KEY`
   (`cloudflare/digithings-web/wrangler.toml:24`; confirm live Pages env first —
   it is not enumerable, `SECRETS_INVENTORY.md:162`), and the mcp example keys
   after an owner confirm-dead or rotate (R3).
2. Reconcile the stack secret checklist against the live set (R9): documented
   `OPENAI_API_KEY` / `FRED_API_KEY` / `R2_*` (`wrangler.toml:145-155`) are
   absent live; `LITELLM_MASTER_KEY` is live but undocumented.
3. Collapse alias families to one live name each: the Cloudflare token family
   (`CLOUDFLARE_API_TOKEN` / `VECTORIZE_API_TOKEN` / `D1_API_TOKEN`, R7) and the
   account-id aliases; the `DIGISEARCH_URL` secret+var collision
   (`SECRETS_INVENTORY.md:124`).
4. Close the gitleaks allowlist hole: replace the broad path allowlists
   `.gitleaks.toml:25` (`^\.env\.example$`) and `.gitleaks.toml:54-55`
   (the two `mcp.secrets.env.example` paths) with placeholder-shaped regexes, so
   a real literal at those paths is scanned. Keep `.env.example` only while it
   holds placeholders (inventory rechecked `:240`/`:278` as
   `replace-with-…`).
5. Add a stale/unreferenced-secret check to CI: diff live `wrangler secret list`
   per Worker against `envVars` + the `wrangler.toml` checklist, and `gh secret
   list` against workflow `secrets.*` references; fail on any name that is
   neither consumed nor documented-inert (the refresh commands in
   `SECRETS_INVENTORY.md:174-193` are the basis).
6. Put the container roll lever where operators look: `paths.ts:22` /
   `ports.ts:37` in the component READMEs, alongside the existing note in
   [`../ops/SECRETS_ROTATION.md`](../ops/SECRETS_ROTATION.md).

**Acceptance:** alias families have one live name each; the stale check is green
on `develop` and red if a synthetic unreferenced secret is added; gitleaks fails
on a synthetic literal placed in a formerly allowlisted path.
**Effort:** 1–2 days. **Does not fix:** readback, rotation automation, the
container boot-env trap, GitHub environment gating.

### Phase 1 — single system of record + automated sync

**Goal:** one place to add a credential, and one command that lands it on every
consumer.

1. Create the vault items, one per logical credential, environment-separated
   (prod / staging / dev); every name in the inventory maps to exactly one item.
2. Create one service account per surface (CF sync, GH sync, local dev), scoped
   to the vaults it needs.
3. Sync job (repo-owned script + GitHub workflow): read from the vault, then
   `wrangler secret put` on each Worker and `gh secret set` for repo/environment
   secrets. Idempotent, with a `--dry-run` diff and a scheduled reconcile that
   opens an issue on drift.
4. Move production reads behind GitHub Environments (extend the 4 gated
   workflows, `SECRETS_INVENTORY.md:158`) and scope
   `DIGITHINGS_PROJECT_TOKEN` to fine-grained permissions (R13).
5. Python and local dev: `op run --env-file` materialises env; no service reads
   the vault directly, so no vendor SDK ships in `digibase`/`digillm`.

**Acceptance:** changing one vault item and running one command updates every
consumer; `op run … make stack-local` boots the stack; a drift reconcile finds
zero mismatches; every inventory name has an owner and a source item.
**Effort:** 1–2 weeks. **Does not fix:** the container instance roll, the
Cloudflare write-only property, or CI's dependence on vault availability.

### Phase 2 — rotation cadence + automation

**Goal:** make the cadence table in
[`../ops/SECRETS_ROTATION.md`](../ops/SECRETS_ROTATION.md) executable and proven.

1. Implement **JWKS overlap** for `DIGIKEY_PRIVATE_KEY_PEM` before rotating:
   serve two `kid`s during a grace period ≥ `DIGIKEY_JWKS_CACHE_SEC` (300 s,
   `digikey/src/digikey/jwt_verify.py:45`), then retire the old key (R1).
2. Implement the vault **re-seal job** for `DIGIQUANT_VAULT_MASTER_KEY` (the
   module docstring says re-seal is out of scope today,
   `digiquant/src/digiquant/vault/envelope.py:35-36`): seal under a second key
   id, re-seal rows, retire `v1` (R12).
3. Add a dual-accept window for the static bearers (`DIGIKEY_ADMIN_TOKEN`,
   `DIGIKEY_BFF_TOKEN`, R6) so a one-sided rotation cannot break chat auth.
4. Wire the rotation triggers to scheduled reminders; every rotation logged in
   `## Rotation log`.

**Acceptance:** a signing-key rotation produces no issuer-wide 401 beyond the
documented cache window and JWKS serves two `kid`s during overlap; the re-seal
job re-encrypts all ciphertext under the new key id with tests; the log has one
row per rotation.
**Effort:** 1–2 weeks, then ongoing cadence. **Does not fix:** provider-side
rotation APIs; human approval for the `digikey/` crypto path.

### Phase 3 — kill the container boot-env trap

**Goal:** a secret update no longer needs a hand-edited container id.

1. Make the roll derive from content: the sync job bumps
   `SHARED_*_CONTAINER_ID` (or a hash of the forwarded env) only when an
   env-consuming secret changed, then deploys. `wrangler deploy` alone does not
   roll (`../ops/SECRETS_ROTATION.md`, "The container boot-env trap").
2. Prove the roll behaviourally: the stack exposes its instance id at
   `_stack/meta` (`cloudflare/digithings-stack-cloudflare/src/index.ts:319`);
   digichat has no probe, so prove via an auth reset after the 15 m
   `sleepAfter`.
3. **Defer** the async alternative — `startAndWaitForPorts({ startOptions:
   { envVars: { X: await env.SECRET.get() } } })` — until Secrets Store is GA
   and its values are manageable.

**Acceptance:** rotating an env-consuming secret and re-running sync updates the
running container with no manual id edit, and the probe shows the new instance.
**Effort:** ~1 week. **Does not fix:** cold-start cost or the 15 m / 2 h sleep
windows.

## Unverified / could not confirm

- **Secrets Store pricing.** No price is published; the docs still say open
  beta. Treated as unverified rather than guessed.
- **A `containers`-scoped secret consumed directly by a Container.** The
  Secrets Store API model lists a `containers` scope, but no integration doc
  showing a Container reading a Secrets Store secret without the Worker's async
  `startOptions` path was found.
- **The existing password manager product.** The audit records a "password
  manager" copy of the signing key (`SECRETS_INVENTORY.md:40`); which product is
  unverified, so the "already paid for" cost argument is conditional.
- **The live GitHub secret/var set and Pages env.** Only workflow references are
  mapped (`SECRETS_INVENTORY.md:164`, `:162`); whether `CORE_SUPABASE_*` exist or
  workflows fall back to legacy names is unverified.
- **1Password service-account rate limits / audit retention** at the sync
  frequency this plan implies.

## What would change my mind

1. **Secrets Store leaves open beta and gains value readback plus a supported
   sync/CI surface** (check the docs page and changelog): it becomes the natural
   dedup layer for Worker-bound secrets and may absorb much of Phase 1.
2. **The owner names Infisical or Doppler as the org standard**: swap Phase 1
   only; Phases 0/2/3 are vendor-neutral and stay exactly as written.
3. **Measured service-account failures.** If a 100-run sync sample shows any
   vault-fetch failure that blocks a deploy, the "no always-on infra" advantage
   is overstated and a cached/mirrored store (Secrets Store or SOPS) moves up.
4. **A second cloud or account requirement** (e.g. AWS) where least-privilege
   machine access needs IAM/OIDC that a password manager cannot express.
5. **Cloudflare ships automatic container rollout on secret change**: delete
   Phase 3.

## Consequences

**Positive.** One place to add, rotate, and audit every credential; real
readback and versioning for the credentials that hurt most (R1 signing key, R6
static bearers, R12 vault key); CI can diff desired vs deployed and fail on
drift; dead and duplicate secrets are removed in Phase 0 before any new
dependency; the container roll becomes a scripted, visible step instead of
tribal knowledge.

**Negative.** A new hard dependency: if the vault is unreachable, CI cannot
fetch and a deploy can stall — keep a documented break-glass path and a small
seeded copy of the deploy-critical secrets. The vault is the source, but
Cloudflare and GitHub remain **mirrors**, so drift is possible until the
reconcile job exists; ship the reconcile with the sync, not after. Local-dev
friction rises: `cp .env.example .env` becomes an `op run`/service-account
workflow, which is a real onboarding cost. Recurring cost (~$8/user/mo
Business-class) plus service-account proliferation adds a spend and
blast-radius item. It does **not** by itself fix R1 or R12 — those need the
Phase 2 code (JWKS overlap, vault re-seal) before any rotation is safe. And the
Cloudflare write-only property and the container boot-env trap survive the
migration: Phase 3 is the only thing that removes the second.
