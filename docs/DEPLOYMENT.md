# Deployment

How to run DigiThings for a small firm or single-operator deployment. For the security posture, see [SECURITY.md](../SECURITY.md). For strategy/vision, see [VISION.md](VISION.md). For local-stack specifics, see [LOCAL_STACK.md](LOCAL_STACK.md).

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
| DigiGraph | http://127.0.0.1:8000 |
| DigiQuant | http://127.0.0.1:8001 |
| DigiSearch | http://127.0.0.1:8002 |
| DigiSmith | http://127.0.0.1:8003 |
| LiteLLM | http://127.0.0.1:4000 |
| DigiKey | http://127.0.0.1:8005 |
| DigiChat (profile `digichat`) | http://127.0.0.1:3005 |

Use **Tailscale** or **Cloudflare Tunnel** for remote access. Never expose ports publicly. See [SECURITY.md](../SECURITY.md).

**DigiQuant build flag:** The default DigiQuant image includes NautilusTrader. Set `NAUTILUS=0` to exclude it (backtest/optimize/pipeline then return 503).

## With heartbeat (unattended monitoring)

```bash
make up-heartbeat
```

Adds the `heartbeat` service. Audit events are appended to the path defined by `AUDIT_LOG_PATH` (default `digiquant/results/audit/events.jsonl`). If ADDM reports strategy drift (when implemented), re-optimize is triggered automatically.

See [digiclaw/docs/HEARTBEAT.md](../digiclaw/docs/HEARTBEAT.md) for the checklist the heartbeat agent follows.

## DigiChat

```bash
make up-digichat     # core stack + DigiChat (Docker profile digichat, host port 3005)
make down-digichat
```

DigiChat needs `AUTH_SECRET`, `AUTH_URL`, and `DIGIKEY_BFF_TOKEN` in `.env`. Auto-migration runs on startup (`DIGICHAT_AUTO_MIGRATE=1`). Full docs: `digichat/ARCHITECTURE.md` (nested repo).

## LiteLLM

LiteLLM is the only LLM router. Compose uses `docker.litellm.ai/berriai/litellm:main-stable` with explicit `--config` and a `/health/liveliness` healthcheck.

**Auth modes:**

- **No `LITELLM_MASTER_KEY`:** acceptable on loopback/trusted networks only. The proxy may accept requests without a Bearer.
- **With `LITELLM_MASTER_KEY`:** required for anything beyond local dev. Set `LITELLM_PROXY_API_KEY` on DigiGraph to the same value (or issue virtual keys via DigiKey).

See [config/MODELS.md](../config/MODELS.md) for model lists, modes (`test` / `medium` / `best`), caching, and fallbacks.

## Metrics and observability

Every HTTP service in the core stack exposes a `/health` endpoint. DigiSmith additionally exposes `/v1/status` (public — keep secret-free). Full Prometheus dashboards are a roadmap item (see [epic #4](https://github.com/digithings-ai/digithings/issues/4)).

Current audit artifacts:

- `digiclaw/audit.py` — append-only JSONL; single source of truth for the heartbeat/audit flow.
- `digigraph/src/digigraph/audit.py` + `digiquant/src/digiquant/audit.py` — per-component audit sinks; to be consolidated into `digibase.audit` (Phase 5 of the cleanup epic [#31](https://github.com/digithings-ai/digithings/issues/31)).
- Optional `AUDIT_SINK_URL` on DigiClaw for NDJSON POST mirror.

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
- **`make test-cov` fails to import:** requires editable installs — `pip install -e "digigraph[dev]" -e "digiquant[dev]" -e "digismith"`.
- **DigiChat shows "auth not configured":** set `AUTH_SECRET`, `AUTH_URL`, `DIGIKEY_BFF_TOKEN` in `.env` and recreate the container.
- **DigiGraph returns 503 on `/v1/backtest`:** image was built with `NAUTILUS=0`. Rebuild without the flag or use `/workflow` (research-only).

## Public domain routing

One public domain is in use for DigiChat; see [docs/adr/0018-digichat-path-routing.md](adr/0018-digichat-path-routing.md) (**Accepted**) for the routing decision, which supersedes the `chat.digithings.ai` subdomain plan in [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md).

### digithings.ai — static landing page

- **Source:** `frontend/digithings-web/` (Next.js static export; and shared `frontend/digiweb/design/`, `frontend/digiweb/web/` assets).
- **Deployment:** **Cloudflare Pages** via `scripts/build-digithings.sh` (CI: Cloudflare Pages project `digithings-ai`).
- **Legacy:** the `static.yml` GitHub Pages workflow and the pre-migration `frontend/digithings/` static HTML tree were both **removed** — the former in the 2026-06 workflow cleanup, the latter in #1240 once `frontend/digithings-web` (Next.js) fully replaced it as the build source; do not use GitHub Pages for this domain.
- **Nav link:** the landing page links to `/chat` (path-routed to the DigiChat container per ADR-0018, not a subdomain).

To update the landing page: edit `frontend/digithings-web/`, run the build script locally, and let Cloudflare Pages deploy from the connected branch.

### digithings.ai/chat — DigiChat production app

> **Status:** not deployed yet. `frontend/digichat` has no live production deployment today; this section documents the target architecture (ADR-0018) for when it ships. Tracked in epic [#1248](https://github.com/digithings-ai/digithings/issues/1248).

- **Source:** `frontend/digichat/` — tracked in this monorepo, not a separate deployment repo.
- **Deployment:** Cloudflare Pages Function `frontend/digithings-web/functions/chat/[[path]].ts` forwards `digithings.ai/chat/*` to the DigiChat container origin (a stateful Next.js standalone server — `frontend/digichat/Dockerfile`). No separate subdomain or DNS entry.
- **Path config:** `DIGICHAT_BASE_PATH=/chat`, `NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat`, `AUTH_URL=https://digithings.ai/chat` in the deployment environment.
- **Auth:** also requires `AUTH_SECRET` and `DIGIKEY_BFF_TOKEN` in the deployment environment.

To deploy DigiChat: build/push the container from `frontend/digichat/Dockerfile`, run DB migrations, and set `DIGICHAT_ORIGIN` in the `digithings-ai` Cloudflare Pages project (falls back to the current Azure Container App URL if unset). No changes needed in this repo's DNS (same domain, no new record).

### Verifying the routing

```bash
# Confirm digithings.ai resolves (Cloudflare)
dig +short A digithings.ai

# Confirm the /chat path routes to the DigiChat container (307 to /chat/login is expected, per ADR-0018)
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat

# Check the Cloudflare Route and Pages deployment in the dashboard (digithings-ai project)
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

# 3. Prerendered module route: 200 + text/html
curl -sL -o /dev/null -w 'module %{http_code} %{content_type}\n' https://digithings.ai/modules/digigraph/

# 4. Stable design asset: 200 + image/png (the #671 SPA-fallback canary)
curl -sL -o /dev/null -w 'og %{http_code} %{content_type}\n' https://digithings.ai/design/assets/og.png
```

Expected: `home` and `module` return `200` with a `text/html` content-type; `og` returns `200` with `image/png`. A `200 text/html` on `og` means the SPA fallback is masking a missing asset (**fail**, cf. #671); any `404`/`5xx` is a **fail**; `curl -sSfI` exits `0`. A `403`/`429` is an inconclusive Cloudflare bot challenge (warn, not fail).

### digithings.ai/chat — DigiChat production

> Not deployed yet — see the status note above. Once live, run:

```bash
# 1. TLS valid on the apex domain (no separate cert needed — same domain as the landing page)
curl -sSfI https://digithings.ai/ -o /dev/null

# 2. App shell reachable under the /chat path (Next.js may 200 or 307 to /chat/login — both acceptable)
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat
```

Browser steps (no one-liner equivalent):

- **Login smoke:** open `https://digithings.ai/chat` in a private window, complete the Auth.js sign-in flow, and confirm the authenticated chat shell renders without console errors.
- **DigiGraph round-trip:** from the authenticated UI, submit the known-good prompt `Build me a mean-reversion stat-arb on tech` and confirm a structured workflow response returns within the usual latency budget. This mirrors the loopback smoke in the "Smoke test" section above, but end-to-end through the BFF.

If any check fails, roll back per the deployment target's standard procedure (static landing: revert the offending commit and let Cloudflare Pages redeploy from the connected branch; DigiChat: redeploy the previous green build).

## Legacy URL Redirects

digithings.ai is served by **Cloudflare Pages, which natively supports a `_redirects` file** for server-side 301/302 redirects — this is a first-class Pages feature, not a Netlify-only one. There is no `404.html` JavaScript shim and no Jekyll plugin: legacy paths are redirected at the edge, and `website/` no longer exists.

**Source of truth:** `frontend/digithings-web/public/_redirects`. Next.js copies everything under `public/` into the static export (`out/`), and `scripts/build-digithings.sh` assembles `dist/` from `out/`, so the file lands at the deploy root where Cloudflare Pages reads it. Current contents:

```
# Back-compat for the legacy static digithings.ai URLs.
/chat.html            /chat/            301
/index.html           /                 301
```

Format is `<from> <to> <status>`, one rule per line, first match wins (`#` starts a comment). `/chat` is **not** a redirect target — per [ADR-0018](adr/0018-digichat-path-routing.md) it is the live DigiChat path (Cloudflare route to the container), so it must never appear here.

### Adding a redirect

1. Add a `<from> <to> <status>` line to `frontend/digithings-web/public/_redirects`.
2. Push to the connected deploy branch; Cloudflare Pages rebuilds via `scripts/build-digithings.sh` and picks up the new rule (no other code changes).
3. Verify: `curl -s -o /dev/null -w '%{http_code} %{redirect_url}\n' https://digithings.ai/<from>` prints the `301`/`302` and the target `Location`.

See also [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) for the domain strategy behind the path inventory.

## See also

- [ARCHITECTURE.md](../ARCHITECTURE.md) — full service topology and flows.
- [LOCAL_STACK.md](LOCAL_STACK.md) — no-Docker dev loop details.
- [frontend/digichat/ARCHITECTURE.md](../frontend/digichat/ARCHITECTURE.md) — DigiChat module architecture.
- [docs/adr/0018-digichat-path-routing.md](adr/0018-digichat-path-routing.md) — DigiChat path-routing decision (supersedes the `chat.digithings.ai` subdomain plan).
- [digiclaw/docs/HEARTBEAT.md](../digiclaw/docs/HEARTBEAT.md) — heartbeat checklist.
- [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) — two-domain strategy and migration plan.
