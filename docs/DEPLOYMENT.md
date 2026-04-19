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

Two public domains are in use. See [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) for the full domain strategy.

### digithings.ai — static landing page

- **Source:** `website/` directory in this repo.
- **Deployment:** GitHub Pages via `.github/workflows/static.yml` (triggers on push to `main` or `develop`).
- **CNAME:** `website/CNAME` = `digithings.ai` — GitHub configures the custom domain from this file.
- **Asset copy:** the workflow runs `cp -r assets website/assets` before upload so the root-level `assets/` directory (e.g. `assets/qrw.svg`) lands alongside the HTML.
- **Nav link:** the landing page links to `https://chat.digithings.ai` (line 25 of `website/index.html`).

To update the landing page: edit files in `website/` and push to `develop`. Pages deploys automatically.

### chat.digithings.ai — DigiChat production app

- **Source:** `digichat/` (gitignored — separate deployment repo).
- **Deployment:** external hosting (Vercel or equivalent). Not deployed by this repo's CI.
- **DNS:** `chat.digithings.ai` CNAME points to the DigiChat production deployment target. Configured in the DNS provider (not in this repo).
- **Auth:** requires `AUTH_SECRET`, `AUTH_URL`, and `DIGIKEY_BFF_TOKEN` in the deployment environment.

To deploy DigiChat: push to the `digichat/` deployment repo (or trigger the external CI pipeline). DNS is already wired — no changes needed in this repo.

### Verifying the routing

```bash
# Confirm CNAME record for digithings.ai (should resolve to github.io pages)
dig CNAME www.digithings.ai

# Confirm CNAME for chat subdomain
dig CNAME chat.digithings.ai

# Check Pages deployment status
gh run list --workflow=static.yml --limit=5
```

## Post-deploy smoke test

Run after every deploy that touches either public surface. Each check is a one-line command where possible; browser-only steps are called out explicitly. Out of scope: synthetic / continuous monitoring (tracked separately under epic [#4](https://github.com/digithings-ai/digithings/issues/4)).

### digithings.ai — static landing

```bash
# 1. TLS valid and certificate chain terminates (exit 0 = OK)
curl -sSfI https://digithings.ai/ -o /dev/null

# 2. CNAME resolves to GitHub Pages
dig +short CNAME www.digithings.ai | grep -E 'github\.io\.?$'

# 3. index.html returns 200
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/

# 4. Hero CTA target (DigiChat link from website/index.html) reachable
curl -s -o /dev/null -w '%{http_code}\n' https://chat.digithings.ai/

# 5. Primary assets return 200 (stylesheet + hero logo)
curl -s -o /dev/null -w 'css=%{http_code}\n' https://digithings.ai/style.css
curl -s -o /dev/null -w 'svg=%{http_code}\n' https://digithings.ai/assets/qrw.svg
```

Expected: all HTTP checks print `200`; `dig` prints a `*.github.io.` target; `curl -sSfI` exits `0`.

### chat.digithings.ai — DigiChat production

```bash
# 1. TLS valid on the chat subdomain
curl -sSfI https://chat.digithings.ai/ -o /dev/null

# 2. App shell reachable (Next.js may 200 or 307 to /login — both acceptable)
curl -s -o /dev/null -w '%{http_code}\n' https://chat.digithings.ai/
```

Browser steps (no one-liner equivalent):

- **Login smoke:** open `https://chat.digithings.ai/` in a private window, complete the Auth.js sign-in flow, and confirm the authenticated chat shell renders without console errors.
- **DigiGraph round-trip:** from the authenticated UI, submit the known-good prompt `Build me a mean-reversion stat-arb on tech` and confirm a structured workflow response returns within the usual latency budget. This mirrors the loopback smoke in the "Smoke test" section above, but end-to-end through the BFF.

If any check fails, roll back per the deployment target's standard procedure (GitHub Pages: revert the offending commit on `develop`; DigiChat: redeploy the previous green build).

## Legacy URL Redirects

GitHub Pages does not support server-side 301 redirects natively. The standard approach for a static Pages site is a `website/404.html` that inspects `window.location.pathname` and redirects known legacy paths via JavaScript before falling through to a generic "not found" page.

### Known legacy paths

The following paths may have been shared externally or are referenced in old content:

| Legacy path | Likely origin | Redirect target |
|---|---|---|
| `/chat` | Early nav link before `chat.digithings.ai` subdomain was live | `https://chat.digithings.ai` |
| `/vite` | Vite DigiChat POC (removed in recent commits per ADR-0002) | `https://chat.digithings.ai` |
| `/atlas` | Atlas research engine teaser (standalone; migrating to `digiquant.io/atlas` per ADR-0002) | `https://digiquant.io/atlas` (future) — hold until domain is live |
| `/digichat` | Pre-unification path variant | `https://chat.digithings.ai` |

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
    "/chat":     "https://chat.digithings.ai",
    "/vite":     "https://chat.digithings.ai",
    "/digichat": "https://chat.digithings.ai",
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
- `digichat/ARCHITECTURE.md` (nested repo) — DigiChat deployment.
- [digiclaw/docs/HEARTBEAT.md](../digiclaw/docs/HEARTBEAT.md) — heartbeat checklist.
- [docs/adr/0002-domain-unification.md](adr/0002-domain-unification.md) — two-domain strategy and migration plan.
