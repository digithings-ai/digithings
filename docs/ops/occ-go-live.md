# OCC go-live runbook (DIG-3585)

How to ship the OCC invite path fixes to production. Steps marked **[Chris]** need
Chris's click or Chris's terminal; agents do not merge, deploy, approve production,
change Cloudflare/KV, or handle the invite key.

The invite key is read from the environment only. Never paste it into a chat, a
ticket, a command line you share, or a log. The smoke script takes it from
`OCC_INVITE_KEY` and never prints it.

## 0. What ships

| Order | PR | Branch | What it changes | Deploy that carries it |
|---|---|---|---|---|
| 1 | #6572 | `fix/DIG-3585-tokenless-invite-tenant` | Worker gate + digichat: constant-time compares, cookie v2 with max age, YAML token tenants default to `auth: session`, `/api/chat` needs the install token, query strings redacted from Worker logs, invite links 302 to the clean `/chat/occ/` URL | `deploy-digichat-cloudflare-container.yml` |
| 2 | #6571 | `fix/digisearch-tenant-index-scope` | digisearch: tenant-scoped indexes for query, MCP and ingest | `deploy-digithings-stack-cloudflare.yml` |
| 3 | #6574 | `fix/DIG-3585-no-unsigned-tenant-header` | digikey/digigraph: tenant only from the signed claim | `deploy-digithings-stack-cloudflare.yml` |

#6568 (the single-path `/chat/occ` gate) is already on `develop` and ships in the
same promotion.

The three PRs touch disjoint code, so the order only matters for review. Merge
#6571 before #6574 so the stack image is built once with both.

## 1. Merge into develop **[Chris]**

1. Approve and merge #6572, #6571, #6574 in that order (squash, as usual).
2. After each merge, check that develop CI is green:

   ```sh
   gh run list --branch develop --limit 10
   ```

## 2. Promote develop to main

1. An agent may open the promotion PR (same shape as #6565):

   ```sh
   git fetch origin
   git switch -c promote/$(date +%F)-occ origin/develop
   git push origin promote/$(date +%F)-occ:promote/$(date +%F)-occ
   gh pr create --base main --head promote/$(date +%F)-occ \
     --title "chore(release): promote develop to main — $(date +%F) (OCC)"
   ```

   Before opening it, check that `main` has nothing `develop` lacks (merging
   `origin/main` into a worktree off `origin/develop` must add 0 files).
2. **[Chris]** Review and merge the promotion PR.

The push to `main` runs both deploy workflows in **build-proof mode only**: a push
deploys nothing. Production needs the dispatch below.

## 3. Deploy

Run the stack first (the services the chat calls), then the chat Worker and
container.

1. **[Chris]** Dispatch the stack deploy from `main`:

   ```sh
   gh workflow run deploy-digithings-stack-cloudflare.yml --ref main -f ref=main
   ```

2. **[Chris]** Approve the `production` environment on that run (GitHub Actions →
   the run → "Review deployments" → production → Approve). The run waits there
   until approved; `production-deploy-gate-watchdog.yml` reports runs left waiting.
3. Wait for green. The workflow reads `/_stack/meta` back and fails if the live
   revision is not the deployed commit.
4. **[Chris]** Dispatch the chat deploy from `main`:

   ```sh
   gh workflow run deploy-digichat-cloudflare-container.yml --ref main -f ref=main
   ```

5. **[Chris]** Approve `production` on that run.
6. Wait for green. Anyone may confirm the revision (no cost, no key):

   ```sh
   curl -s https://digithings.ai/_digichat/meta
   git rev-parse --short=12 origin/main
   ```

## 4. Smoke

Uninvited half (anyone, no key):

```sh
scripts/smoke_occ_invite_gate.sh https://digithings.ai
```

Expect `ok https://digithings.ai/chat/occ/ 404, no chat shell`. A plain
`/chat/occ` with no invite is a 404 **on purpose**, so the page does not reveal
that it exists.

Invited half **[Chris, own terminal]**. The key comes from the Keychain into the
environment of that one command; it is never typed or echoed:

```sh
OCC_INVITE_KEY="$(security find-generic-password -s digithings.occ-invite-key -a DIG-1474 -w)" \
  OCC_SMOKE_SKIP_TURN=1 scripts/smoke_occ_invite_gate.sh https://digithings.ai
```

It checks, in order:

- the bare link `/chat/occ?token=…` answers **302** with the `occ_invite` cookie
  and `Location: https://digithings.ai/chat/occ/` (the key is gone from the URL);
- the cookie reload answers **200** with the chat itself and no iframe;
- `/chat/api/embed/tenant-config` binds the OCC tenant only with the cookie from
  the OCC page, and never without it or from a house page.

Drop `OCC_SMOKE_SKIP_TURN=1` to also send one real chat turn (one model call).

Optional browser check **[Chris]**: open the invite link, confirm the address bar
shows `https://digithings.ai/chat/occ/` with no `token=`, and send one message.

## 5. After go-live (decisions for Chris)

- **[Chris] Rotate the invite key (optional).** Worker invocation logs written
  before `redact_query_string` took effect may hold a first-hop `?token=` URL until
  Workers Logs retention (7 days) ages them out. Rotating closes that window now and
  retires every issued cookie. Follow `docs/ops/OCC_INVITE_KEY.md`; it is a
  Cloudflare secret change.
- **[Chris] Remove the Pages copy of `OCC_INVITE_KEY`.** The Pages shell is gone;
  the Worker is the only gate, so the key should exist only as a Worker secret
  (definition of done in `docs/plans/2026-10-27-occ-single-path.md`).
- `OCC_INVITE_MAX_AGE_DAYS = 30` is a plain `[vars]` value in
  `apps/digichat-cloudflare/wrangler.toml`; change it by PR if a different session
  lifetime is wanted.
- `workers_dev = false` takes effect on the deploy; confirm nothing outside the repo
  uses the workers.dev hostname.
- After #6574, a caller using a static upstream key with no tenant claim gets the
  house corpus only. The production chat uses the bff_session token, which carries
  the tenant.

## Rollback

- Worker and container: Cloudflare keeps Worker versions. **[Chris]** redeploy the
  previous version from the dashboard, or dispatch the chat workflow with the
  previous `main` commit as `ref`.
- Stack: **[Chris]** dispatch the stack workflow with the previous `main` commit.
- Code: revert the merge on `develop`, then promote again.
