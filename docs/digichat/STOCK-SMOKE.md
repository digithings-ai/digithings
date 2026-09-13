# digichat stock smoke (2.0 assistant-ui)

Manual checklist for the stock product path after slices 1–4
(gate intercept, CliThread removal, memory thread list, CSS isolation).

Package stays **1.4.0**. Do not treat this as a 2.0 cutover.

## Prerequisites

From the digichat 2.0 worktree:

```bash
# Backend (digikey :8005, digigraph :8000, …)
PATH="$PWD/.venv/bin:$PATH" make stack-local

# Prefer YAML tenants — unset a mangled DIGICHAT_EMBED_TENANTS JSON:
cd cloudflare/digichat
env -u DIGICHAT_EMBED_TENANTS \
  DIGICHAT_CONFIG_PATH="$PWD/config/examples/digithings-ai-embed.yaml" \
  npm run dev -- --hostname 127.0.0.1 -p 3005
```

For memory persistence (stop the other digichat Next instance first — Next 16
refuses a second `next dev` in the same app dir):

```bash
env -u DIGICHAT_EMBED_TENANTS \
  DIGICHAT_CONFIG_PATH="$PWD/config/examples/local-app-memory.yaml" \
  npm run dev -- --hostname 127.0.0.1 -p 3005
```

## Checklist

1. **Health** — `GET /api/health` → ok envelope.
2. **Stock embed** — `/embed?host=https://digithings.ai` (product YAML hosts):
   - First-party `digichat` Thread (`data-thread-skin="digichat"`).
   - Send one turn; Network shows `POST /api/chat` (not `/api/baseline-chat`).
   - Tokens stream (backend may return a workflow error — still counts as transport OK).
3. **Tool catalog** — Search / Vault on the catalog bar; Web search opt-in on
   digithings.ai. Arm Search → next `POST /api/chat` sends `x-digi-force-tool: digisearch`.
4. **Widget / modal** — `widget.js` or dashboard popup opens chat; small viewport uses fullscreen when `mobileFullscreen` is on.
5. **Gate** — gated tenant: locked composer does not fire `POST /api/chat`; after unlock the held question sends once (unit-covered in `embed-send-gate` + `stock-send-gate`).
6. **Memory** — with `local-app-memory.yaml`: sidebar list, New thread, switch threads (unit-covered in `session-memory-thread-list` + `home-stock-client.memory`).
7. **Deploy UI knobs (web)** — with a YAML that sets granular features:
   - `features.reasoning: off` → no reasoning disclosure in the transcript.
   - `features.reasoning: expanded` / `locked_open` → disclosure opens (locked stays open).
   - `gate.showLanguageSelector` / model picker: not mounted on the stock baseline.
   - `data-user-align` / bubbles respect `chrome.transcript.userAlign`.
8. **CLI (optional)** — `cloudflare/digichat/cli` with `local-cli.yaml` (`cli.enabled: true`) hits the same `POST /api/chat`. Confirm Next/product sources still do not import `ink` / `@assistant-ui/react-ink` (`cli-isolation` unit test).

## Record (2026-09-05, worktree `feat/digichat-2.0-assistant-ui`)

| Step | Result | Notes |
|------|--------|-------|
| Health | pass | `http://127.0.0.1:3005/api/health` → `{"ok":true,…}` digigraph+db ok |
| Embed send → `/api/chat` | pass | Stock chrome; POST `/api/chat` streamed; digigraph workflow error body is upstream, not transport |
| Force-tool header | pass | Search pressed → `x-digi-force-tool: digisearch` on next POST `/api/chat` |
| Widget / modal | skip | Not exercised this pass (no dashboard popup host running) |
| Gate hold / restore | pass (unit) | Client intercept + charge-arm covered by Vitest; live gated tenant not loaded |
| Memory list + switch | pass (unit) | `SessionMemoryThreadListAdapter` + HomeStockClient memory mount tests green; live YAML needs exclusive Next port |

Also fixed during smoke: `@/lib/deploy-config` no longer re-exports the
`node:fs` loader — embed client bundle was failing Turbopack chunk generation.
Server routes import `@/lib/deploy-config/loader` directly.
