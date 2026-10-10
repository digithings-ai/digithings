# Deployment

How to run digithings for a small firm or single-operator deployment. For the security posture, see [SECURITY.md](../SECURITY.md). For strategy/vision, see [VISION.md](VISION.md). For local-stack specifics, see [LOCAL_STACK.md](LOCAL_STACK.md).

## One-command run (Docker)

From the repo root, with Docker Desktop (or Docker Engine + Compose) running:

```bash
cp .env.example .env
# Edit .env: set OLLAMA_API_KEY (or OPENAI_API_KEY) and any overrides
make up
```

Endpoints (all bind to `127.0.0.1`):

| Service | URL |
|---------|-----|
| digigraph | http://127.0.0.1:8000 |
| digiquant | http://127.0.0.1:8001 |
| digisearch | http://127.0.0.1:8002 |
| digitrace | http://127.0.0.1:8003 |
| LiteLLM | http://127.0.0.1:4000 |
| digikey | http://127.0.0.1:8005 |
| digichat (profile `digichat`) | http://127.0.0.1:3005 |

Use **Tailscale** or **Cloudflare Tunnel** for remote access. Never expose ports publicly. See [SECURITY.md](../SECURITY.md).

**digiquant image:** Always installs `digiquant[nautilus]` (NautilusTrader). Market sample CSVs for backtests are under `digiquant/data/` (compose-mounted); the image does not download upstream Nautilus fixtures at build time.

## Pull from GHCR (no local image build)

Prefer this when you want published images instead of `docker compose build`. Requires Compose **v2.24+**.

```bash
cp .env.example .env
# Optional pins (production): DIGI_IMAGE_TAG=sha-<12-char-sha> DIGICHAT_IMAGE_TAG=v1.0.0
# (DataTap / existing clients may keep DIGICHAT_IMAGE_TAG=v0.9.3 — that GHCR tag remains.)
docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  pull
docker compose \
  -f docker-compose.yml \
  -f infra/self-host/compose.ghcr.yml \
  up -d
```

Or: `make up-ghcr` / `make up-ghcr-digichat`. Full notes: [templates/self-host/README.md](templates/self-host/README.md). Image publish: [RELEASES.md](../RELEASES.md).

Swagger UI (auth-exempt): `http://127.0.0.1:<port>/docs` on each FastAPI service (8000–8005).

## With heartbeat (unattended monitoring)

```bash
make up-heartbeat
```

Adds the `heartbeat` service. Audit events are appended to the path defined by `AUDIT_LOG_PATH` (default `digiquant/results/audit/events.jsonl`). If ADDM reports strategy drift (when implemented), re-optimize is triggered automatically.

See [digiclaw/docs/HEARTBEAT.md](../digiclaw/docs/HEARTBEAT.md) for the checklist the heartbeat agent follows.

## digichat

```bash
make up-digichat     # core stack + digichat (Docker profile digichat, host port 3005)
make down-digichat
```

digichat needs `AUTH_SECRET`, `AUTH_URL`, and `DIGIKEY_BFF_TOKEN` in `.env`. Auto-migration runs on startup (`DIGICHAT_AUTO_MIGRATE=1`). Full docs: `digichat/ARCHITECTURE.md` (nested repo).

## LiteLLM

LiteLLM is the only LLM router. Compose uses `ghcr.io/berriai/litellm:v1.83.14-stable.patch.3@sha256:f12d528d4a05add56cb09e54c5126088f2edc6bdf3a2f943bcd3a32b08769da2` with explicit `--config` and a `/health/liveliness` healthcheck.

**Auth modes:**

- **No `LITELLM_MASTER_KEY`:** acceptable on loopback/trusted networks only. The proxy may accept requests without a Bearer.
- **With `LITELLM_MASTER_KEY`:** required for anything beyond local dev. Set `LITELLM_PROXY_API_KEY` on digigraph to the same value (or issue virtual keys via digikey).

See [config/MODELS.md](../config/MODELS.md) for model lists, modes (`test` / `medium` / `best`), caching, and fallbacks.

## Metrics and observability

Every HTTP service in the core stack exposes a `/health` endpoint. digitrace additionally exposes `/v1/status` (public — keep secret-free). Full Prometheus dashboards are a roadmap item (see [epic #4](https://github.com/digithings-ai/digithings/issues/4)).

Current audit artifacts:

- `digiclaw/audit.py` — append-only JSONL; single source of truth for the heartbeat/audit flow.
- `digigraph/src/digigraph/audit.py` + `digiquant/src/digiquant/audit.py` — per-component audit sinks; to be consolidated into `digibase.audit` (Phase 5 of the cleanup epic [#31](https://github.com/digithings-ai/digithings/issues/31)).
- Optional `AUDIT_SINK_URL` on digiclaw for NDJSON POST mirror.

## Tests

```bash
make test        # unit + e2e (if stack up)
make test-unit   # unit only
make test-e2e    # e2e (requires make up)
```

## Smoke test

```bash
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}' \
  | python3 -m json.tool
```

## Packaging

`make package` (or `scripts/package.sh`) produces `digi-bundle-YYYYMMDD.tar.gz` with the repo (excluding `.git`, `.venv`, `__pycache__`, `projects/`). Recipients:

1. Extract, copy `.env.example` to `.env`, set secrets.
2. `make up` (optionally `make up-heartbeat`).

The tarball is **not** versioned; for production shipping, use git tags or image digests per [RELEASES.md](../RELEASES.md).

## Unattended run (multi-day)

For a week-long unattended run:

1. Start with heartbeat: `make up-heartbeat`.
2. Set `AUDIT_LOG_PATH` to a persistent volume path (default in Compose uses `./digiquant/results/audit`).
3. Optionally set `REOPTIMIZE_STRATEGY` in the heartbeat container if using ADDM drift → re-optimize.
4. Monitor audit log and service health. **No live trading without explicit human gates** (see [SECURITY.md](../SECURITY.md)).

## Troubleshooting

- **Ports already in use:** check for prior `docker compose up` instances (`docker ps`) or conflicting host services on 8000–8005, 4000, 3005.
- **`make test-cov` fails to import:** requires editable installs — `pip install -e "digigraph[dev]" -e "digiquant[dev]" -e "digitrace"`.
- **digichat shows "auth not configured":** set `AUTH_SECRET`, `AUTH_URL`, `DIGIKEY_BFF_TOKEN` in `.env` and recreate the container.
- **digigraph returns 503 on `/v1/backtest`:** digiquant not healthy or upstream auth missing — check `docker compose ps digiquant` and digikey JWT/scopes.

## Public domain routing

One public domain serves marketing + chat shell:

- **Marketing shell:** `digithings.ai` — Cloudflare Pages (`apps/digithings-web/`).
- **Visitor chat:** `digithings.ai/chat` — Pages iframe → digichat Node `/embed`
  (`NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN`, e.g. Tunnel hostname `digichat.digithings.ai`).
  Backend: digichat → digigraph → digillm → LiteLLM (+ digivault tools).
- digithings has **no Azure**. DataTap digichat ACA is client-only.
- Operator runbook: [`infra/digichat-digithings/README.md`](../infra/digichat-digithings/README.md).
- Product model: [`docs/architecture/digichat-modular-frontend.md`](architecture/digichat-modular-frontend.md) §5.
- Client install: [`docs/digichat/INSTALL.md`](digichat/INSTALL.md).

Do **not** use `chat.digithings.ai` as the marketing host. Customer digichat `/embed`
(DataTap etc.) is separate from digithings’ own marketing chat. Path routing:
[ADR-0018](adr/0018-digichat-path-routing.md).

**Correction (2026-10-10, DIG-2843):** an earlier revision of this file said the digithings
Containers scaffold was removed on 2026-08-06 and never had a deploy path. It was true when
written — the Cloudflare account was on Workers Free then, and Containers need Workers Paid
(`docs/superpowers/specs/2026-08-05-digichat-phase3-unification-design.md` records the gate) —
and it stopped being true when the account moved. It was not kept with a caveat: the claim was
simply removed. `apps/digichat-cloudflare/` (Worker `digithings-digichat` + Container) is live in
the tree, requires Workers Paid, declares seven `digithings.ai` route patterns in its
`wrangler.toml`, and is covered by the CI build matrix. What is missing is not the app but its
**deploy lane** — see [Cloudflare Workers and Containers](#cloudflare-workers-and-containers).

digichat Node for digithings still runs on operator Compose + Cloudflare Tunnel; that is a
different surface from the `digichat-cloudflare` Worker.

### digithings.ai — static landing page

- **Source:** `apps/digithings-web/` (Next.js static export; and shared `packages/design/`, `packages/ui/`, `packages/digichat-ui/` assets). Those four are the app's transitive workspace closure, and `tests/scripts/test_deploy_build_inputs.py` asserts the deploy build check watches all of them.
- **Deployment:** **Cloudflare Pages** via `scripts/build-digithings.sh` (CI: Cloudflare Pages project `digithings-ai`).
- **Legacy:** the `static.yml` GitHub Pages workflow and the pre-migration `cloudflare/digithings/` static HTML tree were both **removed** — the former in the 2026-06 workflow cleanup, the latter in #1240 once `apps/digithings-web` (Next.js) fully replaced it as the build source; do not use GitHub Pages for this domain.
- **Nav link:** the landing page links to `/chat` (Pages shell that iframes digichat `/embed`).
- **Deploy freshness (#1759):** `scripts/build-digithings.sh` writes `dist/build-info.json` (`site`, `commit`, `branch`, `builder`, `built_at`) via `scripts/write-build-info.sh`, and hard-fails the build if it is absent. A Pages project that stops producing deployments keeps serving the last good build with a `200` and no `last-modified` header, so the asset probes below pass throughout a freeze; the `freshness-digithings` job in `smoke-site.yml` reads the live stamp through `scripts/check_deploy_freshness.py` and fails when it is missing or older than 7 days. This is **detection only** — *why* a Pages project stopped building is visible only in the Cloudflare dashboard (deployment list, build log, production branch, watch paths).

To update the landing page: edit `apps/digithings-web/`, run the build script locally, and let Cloudflare Pages deploy from the connected branch.

### digithings.ai/chat — digichat marketing pane

> digithings has **no Azure**. Marketing chat is digithings’ **own** Profile A install:
> Pages shell + iframe → digichat Node (Tunnel) → digigraph → digillm → LiteLLM (+ digivault).
> DataTap Azure digichat is client-only.

- **Shell:** `digithings.ai/chat` on Cloudflare Pages embeds digichat `/embed` via
  `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` (e.g. `https://digichat.digithings.ai`).
- **Backend:** digichat BFF → digigraph (not a Pages Function OpenRouter loop).
- **Operator host:** Compose + Cloudflare Tunnel — see
  [`infra/digichat-digithings/README.md`](../infra/digichat-digithings/README.md).

### Verifying the routing

```bash
dig +short A digithings.ai
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat
# Tunnel origin health (operator hostname; adjust if different):
curl -sf https://digichat.digithings.ai/api/health | jq .
```

## Post-deploy smoke test

Run after every deploy that touches either public surface. Each check is a one-line command where possible; browser-only steps are called out explicitly. Out of scope: synthetic / continuous monitoring (tracked separately under epic [#4](https://github.com/digithings-ai/digithings/issues/4)).

### digithings.ai — static landing

digithings.ai is a Next.js static export on **Cloudflare Pages** — there is no GitHub Pages apex (`185.199.x.x`), no `/style.css`, and no `/assets/qrw.svg`. The regression that matters here (#671) is the SPA fallback turning a *missing* asset into a soft-200 `text/html` response that MIME-blocks it, so each check asserts **content-type**, not just `200`. These mirror the daily `smoke-site.yml` probe.

```bash
# 1. TLS valid and certificate chain terminates (exit 0 = OK)
curl -sSfI https://digithings.ai/ -o /dev/null

# 2. Homepage: 200 + text/html
curl -sL -o /dev/null -w 'home %{http_code} %{content_type}\n' https://digithings.ai/

# 3. Prerendered route: 200 + text/html (/modules/* was folded into the
#    home-page terminal manifest in #1414 — /docs/ is what smoke-site.yml probes)
curl -sL -o /dev/null -w 'docs %{http_code} %{content_type}\n' https://digithings.ai/docs/

# 4. Stable OG asset: 200 + image/png (the #671 SPA-fallback canary;
#    public/og.png at the static-export root — not /design/assets/)
curl -sL -o /dev/null -w 'og %{http_code} %{content_type}\n' https://digithings.ai/og.png

# 5. Deploy freshness (#1759): the build stamp must be JSON, and `built_at`
#    must be the deploy you just shipped — a frozen Pages project passes 1–4.
curl -sL --max-time 20 https://digithings.ai/build-info.json
```

Expected: `home` and `docs` return `200` with a `text/html` content-type; `og` returns `200` with `image/png`. A `200 text/html` on `og` means the SPA fallback is masking a missing asset (**fail**, cf. #671); any `404`/`5xx` is a **fail**; `curl -sSfI` exits `0`. A `403`/`429` is an inconclusive Cloudflare bot challenge (warn, not fail). Check 5 should print a JSON object whose `built_at` matches this deploy; a `404` or an HTML body means the live deploy predates the stamp (the daily probe reports that as `UNSTAMPED`).

### digithings.ai/chat — digichat production

```bash
# 1. TLS valid on the apex domain (same domain as the landing page)
curl -sSfI https://digithings.ai/ -o /dev/null

# 2. Marketing chat shell under /chat (Pages iframe host — 200 expected)
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat

# 3. digichat Node via Tunnel (adjust hostname if your Tunnel differs)
curl -sf https://digichat.digithings.ai/api/health | jq .
```

Browser steps (no one-liner equivalent):

- **Shell smoke:** open `https://digithings.ai/chat` and confirm the iframe loads digichat `/embed` without console CSP / frame errors.
- **Vault-grounded round-trip:** ask a digivault-grounded question (e.g. what digigraph orchestrates) and confirm tool activity + answer via digigraph — see the operator checklist in [`infra/digichat-digithings/README.md`](../infra/digichat-digithings/README.md).

If any check fails, roll back per the deployment target's standard procedure (static landing: revert the offending commit and let Cloudflare Pages redeploy from the connected branch; digichat: redeploy the previous green digichat image / Compose stack on the Tunnel host).

## Legacy URL Redirects

digithings.ai is served by **Cloudflare Pages, which natively supports a `_redirects` file** for server-side 301/302 redirects — this is a first-class Pages feature, not a Netlify-only one. There is no `404.html` JavaScript shim and no Jekyll plugin: legacy paths are redirected at the edge, and `website/` no longer exists.

**Source of truth:** `apps/digithings-web/public/_redirects`. Next.js copies everything under `public/` into the static export (`out/`), and `scripts/build-digithings.sh` assembles `dist/` from `out/`, so the file lands at the deploy root where Cloudflare Pages reads it. Current contents:

```
# Back-compat for the legacy static digithings.ai URLs.
/chat.html            /chat/            301
/index.html           /                 301
```

Format is `<from> <to> <status>`, one rule per line, first match wins (`#` starts a comment). `/chat` is **not** a redirect target — per [ADR-0018](adr/0018-digichat-path-routing.md) it is the live digichat marketing path (Pages shell + iframe to digichat Node), so it must never appear here.

### Adding a redirect

1. Add a `<from> <to> <status>` line to `apps/digithings-web/public/_redirects`.
2. Push to the connected deploy branch; Cloudflare Pages rebuilds via `scripts/build-digithings.sh` and picks up the new rule (no other code changes).
3. Verify: `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://digithings.ai/<from>` prints the `301`/`302` and the target `Location`.

See also [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) for the domain strategy behind the path inventory.

## Cloudflare Workers and Containers

**"Deploy" means three different things in this repo, and only one of them is an actual deploy.**
This section is the authority on which is which. Measured at `develop` `c326332bd`
(DIG-2843, 2026-10-10); the machine check is a single grep:

```bash
grep -rn "wrangler deploy" .github/workflows/
```

It returns exactly two files.

### 1. A real deploy (`deploy-digiquant-runner.yml`)

`npx wrangler deploy -c apps/digiquant-runner/wrangler.toml`, behind
`environment: production`, with `CLOUDFLARE_API_TOKEN` / `CLOUDFLARE_ACCOUNT_ID`.
`deploy-digithings-cron.yml` is the second one, and uses
`cloudflare/wrangler-action@v3` rather than the CLI. Both push-to-branch.

### 2. A build check that deploys nothing (`build-cloudflare-workers.yml`)

`wrangler deploy --dry-run --containers-rollout=none`, `pull_request` only, **no `push`
trigger**, `permissions: contents: read`, and a test asserting no `secrets.` string is in
the file. It proves the Worker **builds** — a `tsc`-invisible Durable Object export failure
is the failure it was added for. It proves nothing about what is live.

Its matrix is every app that pins `wrangler` and ships a `wrangler.toml`, and
`tests/scripts/test_worker_build_matrix.py` derives that set from the tree and fails when a
Worker is added without landing in the matrix. The matrix covers
`digichat-cloudflare` and `digithings-stack-cloudflare`.

### 3. A build check for a site Cloudflare deploys itself (`deploy-digithings-cloudflare.yml`)

`bash scripts/build-digithings.sh` plus `dist/` assertions. It never deploys: the real
digithings.ai deploy is **Cloudflare Pages watching `main`**, configured in the Cloudflare
dashboard, not in this repo. `deploy-digiquant-cloudflare.yml` is the same shape for
digiquant.io. Nothing in the repo can make a Pages deployment fail before it happens, only
fail a PR before it merges.

### The two stacks have no deploy lane

| App | Worker name | Declared routes | Deploy lane |
|---|---|---|---|
| `apps/digithings-stack-cloudflare` | `digithings-stack` | `graph.digithings.ai`, `key.digithings.ai`, `search.digithings.ai` (all `custom_domain = true`) | **none — manual** |
| `apps/digichat-cloudflare` | `digithings-digichat` | `digithings.ai` `/embed*`, `/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`, `/api/health`, `/_dtchat*` | **none — manual** |

Read the routes column as "what `wrangler.toml` declares", not as a claim about what is
currently serving. Both are Workers **Containers**: both need **Workers Paid**, and both need
a Docker CLI locally for `wrangler deploy` to build the image.

Both `Dockerfile.digichat-cloudflare` and `Dockerfile.digithings-stack-cloudflare` are live at
the repo root. It is the workflow YAML that is missing, not the build.

#### Why the lane is missing — it was deleted, not never written

`deploy-digithings-stack-cloudflare.yml` and `deploy-digichat-cloudflare-container.yml` both
existed and both were deleted on **2026-10-01** by `f54af7052` (*"strict-essentials cut +
pause CF→disabled traps",* #4919), a commit whose own message records a **Human Gate**:
*"Path A (Human Gate 2026-10-01): delete non-essential workflow YAML."* Thirty workflow files
went with it.

Before that cut the stack lane was `workflow_dispatch`-only behind an
`environment: production` gate, running `npx wrangler deploy -c apps/digithings-stack-cloudflare/wrangler.toml`
from the repo root; the digichat lane pushed to `main` and gated its deploy on a version-change
step. **Both are recoverable:**

```bash
git show 'f54af7052^:.github/workflows/deploy-digithings-stack-cloudflare.yml'
git show 'f54af7052^:.github/workflows/deploy-digichat-cloudflare-container.yml'
```

The caveats those files carried are now stale: both said `CLOUDFLARE_API_TOKEN` and
`CLOUDFLARE_ACCOUNT_ID` were "not yet present", and both are repo secrets today
([ops/SECRETS_INVENTORY.md](ops/SECRETS_INVENTORY.md)).

Restoring either lane is a **production deploy path**, so it was not done unilaterally in a
documentation change. The restore decision is recorded on DIG-2843 in the company board; if it
is taken, follow the precedent set by
[ops/digichat-datatap-aca.md](ops/digichat-datatap-aca.md): **re-derive the lane, do not
`git revert` it**, because the deleted digichat lane pinned no `wranglerVersion` for a
documented reason (4.28.0 rejects `deploy --message`) and re-deriving it keeps that.

#### Deploying by hand today

Prerequisites: Workers Paid; a Docker CLI; `npx wrangler login` into the digithings Cloudflare
account (same zone as `digithings.ai`); the app's Worker secrets already set — they are
write-only, so `wrangler secret list` shows names and types but never values, and a deploy
does not create them.

```bash
# digithings-stack — from the REPO ROOT, because the image_build_context values
# are "../.." and the -c path assumes root (#4046)
npx wrangler deploy -c apps/digithings-stack-cloudflare/wrangler.toml

# digichat-cloudflare
cd apps/digichat-cloudflare && npx wrangler deploy
```

The full secret-by-secret bring-up for the standalone digichat Worker is
[`apps/digichat-cloudflare/README.md`](../apps/digichat-cloudflare/README.md) § Deploy;
the stack's operator notes are
[`apps/digithings-stack-cloudflare/README.md`](../apps/digithings-stack-cloudflare/README.md) § Deploy.

**What no CI check covers:** that the live deployment is the built one. The dry-run matrix
builds both; nothing records a version of the live Worker and compares it. If you deploy by
hand, the only verification available is
[`ops/SECRETS_INVENTORY.md`](ops/SECRETS_INVENTORY.md) for what the Worker should hold and a
direct probe of the route.

## See also

- [ARCHITECTURE.md](../ARCHITECTURE.md) — full service topology and flows.
- [LOCAL_STACK.md](LOCAL_STACK.md) — no-Docker dev loop details.
- [apps/digichat/ARCHITECTURE.md](../apps/digichat/ARCHITECTURE.md) — digichat module architecture.
- [docs/adr/0018-digichat-path-routing.md](adr/0018-digichat-path-routing.md) — digichat path-routing decision (supersedes the `chat.digithings.ai` subdomain plan).
- [digiclaw/docs/HEARTBEAT.md](../digiclaw/docs/HEARTBEAT.md) — heartbeat checklist.
- [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) — two-domain strategy and migration plan.
