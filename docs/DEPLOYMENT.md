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

- **Source:** `frontend/digithings/` (and shared `frontend/design/` assets).
- **Deployment:** **Cloudflare Pages** via `scripts/build-digithings.sh` (CI: Cloudflare Pages project `digithings-ai`).
- **Legacy:** the `static.yml` GitHub Pages workflow was **removed** in the 2026-06 workflow cleanup; do not use GitHub Pages for this domain.
- **Nav link:** the landing page links to `/chat` (path-routed to the DigiChat container per ADR-0018, not a subdomain).

To update the landing page: edit `frontend/digithings/`, run the build script locally, and let Cloudflare Pages deploy from the connected branch.

### digithings.ai/chat — DigiChat production app

> **Status:** not deployed yet. `frontend/digichat` has no live production deployment today; this section documents the target architecture (ADR-0018) for when it ships. Tracked in epic [#1248](https://github.com/digithings-ai/digithings/issues/1248).

- **Source:** `frontend/digichat/` — tracked in this monorepo, not a separate deployment repo.
- **Deployment:** a Cloudflare Route forwards `digithings.ai/chat/*` to the DigiChat container origin (a stateful Next.js standalone server — `frontend/digichat/Dockerfile`). No separate subdomain or DNS entry.
- **Path config:** `DIGICHAT_BASE_PATH=/chat`, `NEXT_PUBLIC_DIGICHAT_BASE_PATH=/chat`, `AUTH_URL=https://digithings.ai/chat` in the deployment environment.
- **Auth:** also requires `AUTH_SECRET` and `DIGIKEY_BFF_TOKEN` in the deployment environment.

To deploy DigiChat: build/push the container from `frontend/digichat/Dockerfile`, run DB migrations, and configure the Cloudflare Route. No changes needed in this repo's DNS (same domain, no new record).

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

```bash
# 1. TLS valid and certificate chain terminates (exit 0 = OK)
curl -sSfI https://digithings.ai/ -o /dev/null

# 2. Apex A-record resolves to GitHub Pages
dig +short A digithings.ai | grep -E '^185\.199\.(108|109|110|111)\.153$'

# 3. index.html returns 200
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/

# 4. Hero CTA target (DigiChat link from website/index.html) reachable
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat

# 5. Primary assets return 200 (stylesheet + hero logo)
curl -s -o /dev/null -w 'css=%{http_code}\n' https://digithings.ai/style.css
curl -s -o /dev/null -w 'svg=%{http_code}\n' https://digithings.ai/assets/qrw.svg
```

Expected: all HTTP checks print `200`; `dig` prints a `185.199.(108|109|110|111).153` address; `curl -sSfI` exits `0`.

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

If any check fails, roll back per the deployment target's standard procedure (GitHub Pages: revert the offending commit on `develop`; DigiChat: redeploy the previous green build).

## Legacy URL Redirects

GitHub Pages does not support server-side 301 redirects natively. The standard approach for a static Pages site is a `website/404.html` that inspects `window.location.pathname` and redirects known legacy paths via JavaScript before falling through to a generic "not found" page.

### Known legacy paths

The following paths may have been shared externally or are referenced in old content:

`/chat` is **not** a legacy redirect target — per [ADR-0018](adr/0018-digichat-path-routing.md) it is the live DigiChat path (Cloudflare Route to the container), so it must not appear in the 404 redirect table below.

| Legacy path | Likely origin | Redirect target |
|---|---|---|
| `/vite` | Vite DigiChat POC (removed in recent commits per ADR-0002) | `/chat` |
| `/atlas` | Atlas research engine teaser (standalone; migrating to `digiquant.io/atlas` per ADR-0002) | `https://digiquant.io/atlas` (future) — hold until domain is live |
| `/digichat` | Pre-unification path variant | `/chat` |

### Chosen strategy: `website/404.html` JS redirect table

Because GitHub Pages does not honour `_redirects` files (that is a Netlify feature) and the `jekyll-redirect-from` plugin requires a Jekyll build pipeline, the recommended approach is:

1. Add `website/404.html` containing a small JS lookup table that maps each known legacy path to its canonical target and issues an immediate `window.location.replace()`.
2. Unknown paths fall through to a human-readable 404 message.

Skeleton (do not implement until a specific legacy URL complaint arises — see implementation note below):

```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><title>digithings — page not found</title></head>
<body>
<script>
  var redirects = {
    "/vite":     "/chat",
    "/digichat": "/chat",
    // "/atlas": "https://digiquant.io/atlas",  // uncomment when digiquant.io is live
  };
  var target = redirects[window.location.pathname];
  if (target) { window.location.replace(target); }
</script>
<p>Page not found. <a href="/">Return to digithings.ai</a>.</p>
</body>
</html>
```

The redirect preserves the user journey with no server changes and degrades gracefully (browsers without JS see the fallback link).

### Implementation note

This framework is documented now so the pattern is established. Actual `website/404.html` creation is **deferred** until a specific legacy URL complaint is reported (e.g. a broken inbound link confirmed in analytics or user feedback). At that point:

1. Create `website/404.html` from the skeleton above.
2. Add the specific path to the redirect table.
3. Push to `develop` — GitHub Pages deploys automatically (see "Public domain routing" section above).
4. Verify with `curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/<legacy-path>` (GitHub Pages returns 200 from `404.html`; the JS then redirects in-browser).

See also [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) for the domain strategy that motivated this path inventory.

## See also

- [ARCHITECTURE.md](../ARCHITECTURE.md) — full service topology and flows.
- [LOCAL_STACK.md](LOCAL_STACK.md) — no-Docker dev loop details.
- [frontend/digichat/ARCHITECTURE.md](../frontend/digichat/ARCHITECTURE.md) — DigiChat module architecture.
- [docs/adr/0018-digichat-path-routing.md](adr/0018-digichat-path-routing.md) — DigiChat path-routing decision (supersedes the `chat.digithings.ai` subdomain plan).
- [digiclaw/docs/HEARTBEAT.md](../digiclaw/docs/HEARTBEAT.md) — heartbeat checklist.
- [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) — two-domain strategy and migration plan.
