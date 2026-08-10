/**
 * Shared guide sections for the docs (rendered above the per-module reference and
 * included in the "Copy all as Markdown" export). Structured as simple blocks so a
 * single renderer + markdown serializer covers them. Codebase-accurate; examples
 * use base-URL variables rather than hardcoded host:port.
 *
 * Product guides map public repo docs (DEPLOYMENT, self-host templates, digichat
 * INSTALL, root ARCHITECTURE) — never confidential projects/ content.
 */

export type Block =
  | { kind: "p"; text: string }
  | { kind: "h"; text: string }
  | { kind: "code"; lang: string; code: string }
  | { kind: "list"; items: string[] };

export interface Guide {
  id: string;
  title: string;
  blocks: Block[];
}

export const guides: Guide[] = [
  {
    id: "getting-started",
    title: "Getting started",
    blocks: [
      {
        kind: "p",
        text:
          "digithings is open-source, MIT-licensed AI infrastructure: modules that plug into the stack you already run rather than replacing it. digigraph orchestrates specialist sub-graphs — quant research, retrieval, vault, and chat. Self-hosted anywhere, BYOK, audit-on by default.",
      },
      { kind: "h", text: "Prerequisites" },
      {
        kind: "list",
        items: [
          "Docker (with Compose)",
          "Python ≥ 3.12 (for running services outside Docker)",
          "Node.js LTS (for the frontends)",
        ],
      },
      { kind: "h", text: "Run the whole stack" },
      {
        kind: "code",
        lang: "bash",
        code:
          "git clone https://github.com/digithings-ai/digithings && cd digithings\ncp .env.example .env   # add your keys\ndocker compose up -d",
      },
      {
        kind: "p",
        text:
          "Each backend service exposes a liveness probe at `GET /healthz`. The service URLs and ports are defined in `docker-compose.yml`; reference them through env vars (`$DIGIGRAPH_URL`, `$DIGIKEY_URL`, …) rather than hardcoding an address.",
      },
      { kind: "h", text: "Essential environment" },
      {
        kind: "list",
        items: [
          "`OPENROUTER_API_KEY` / `OPENAI_API_KEY` — LLM access via the LiteLLM proxy.",
          "`DIGIKEY_ADMIN_TOKEN` — required to mint API keys (see Authentication).",
          "`DIGIKEY_PRIVATE_KEY_PEM` — stable RS256 signing key for production.",
          "See `.env.example` for the full, annotated list.",
        ],
      },
      { kind: "h", text: "Useful make targets" },
      {
        kind: "list",
        items: [
          "`make up` / `make down` — start / stop the core stack.",
          "`make up-digichat` — start the chat BFF + its Postgres.",
          "`make stack-local` — run the Python services without Docker.",
          "`make test-unit` — unit tests (no stack required).",
        ],
      },
      {
        kind: "p",
        text:
          "Interactive OpenAPI for every HTTP surface lives at [OpenAPI explorer](/docs/api/) — committed specs under `docs/openapi/`, not live FastAPI `/docs` on localhost.",
      },
    ],
  },
  {
    id: "self-host",
    title: "Self-host from GHCR",
    blocks: [
      {
        kind: "p",
        text:
          "Prefer published images when you do not want to `docker compose build`. Requires Compose **v2.24+** and a clone of the repo for compose files, `config/`, and `.env` (build context is not required). Stack images (`digikey`, `digigraph`, …) publish via `publish-service-images.yml` on `main` after promote — until those packages exist on GHCR, use `docker compose build` / `make up` instead.",
      },
      { kind: "h", text: "Quick start (once GHCR stack images exist)" },
      {
        kind: "code",
        lang: "bash",
        code:
          "cp .env.example .env\n# Edit .env: provider keys, DIGIKEY_*, optional AUTH_* for digichat\n\ndocker compose \\\n  -f docker-compose.yml \\\n  -f infra/self-host/compose.ghcr.yml \\\n  pull\ndocker compose \\\n  -f docker-compose.yml \\\n  -f infra/self-host/compose.ghcr.yml \\\n  up -d",
      },
      {
        kind: "p",
        text: "Or: `make up-ghcr` / `make up-ghcr-digichat`. digichat itself is already on GHCR (`ghcr.io/digithings-ai/digichat`).",
      },
      { kind: "h", text: "Profiles" },
      {
        kind: "list",
        items: [
          "`digichat` — digichat + Postgres",
          "`digivault` — digivault",
          "`heartbeat` — digiclaw loop",
          "`litellm-cache` — Redis for LiteLLM",
          "`observability` — Prometheus + Grafana",
        ],
      },
      { kind: "h", text: "Image tags" },
      {
        kind: "list",
        items: [
          "`DIGI_IMAGE_TAG` — digikey, digigraph, digiquant, digisearch, digismith, digivault, digiclaw (pin `sha-<12>` in production).",
          "`DIGICHAT_IMAGE_TAG` — digichat only; prefer `vX.Y.Z` from release-please.",
        ],
      },
      {
        kind: "p",
        text:
          "All services bind loopback by default. Use Tailscale or Cloudflare Tunnel for remote access — never expose ports publicly. Full notes: `docs/templates/self-host/README.md` and `docs/DEPLOYMENT.md` in the repo.",
      },
    ],
  },
  {
    id: "digichat-install",
    title: "digichat install",
    blocks: [
      {
        kind: "p",
        text:
          "digithings ships **self-hosted** AI infra. Clients install digichat **releases from GitHub** and run them in their cloud or on-prem. There is no live shared digichat SaaS for clients. `digithings.ai/chat` is digithings' own install of the same product.",
      },
      { kind: "h", text: "Install unit" },
      {
        kind: "code",
        lang: "bash",
        code: "docker pull ghcr.io/digithings-ai/digichat:v0.9.3",
      },
      {
        kind: "list",
        items: [
          "Git tag: `digichat-vX.Y.Z`",
          "GHCR image: `ghcr.io/digithings-ai/digichat:vX.Y.Z` (currently published through `v0.9.3`)",
          "Changelog: `frontend/digichat/CHANGELOG.md`",
          "Pin a published tag — do not assume a version exists on GHCR until the digichat release workflow has published it from `main`.",
        ],
      },
      { kind: "h", text: "Profiles" },
      {
        kind: "list",
        items: [
          "**A — digigraph stack** — digichat + db + digikey + digigraph + LiteLLM + digivault. Adapters: digigraph owns digillm→LiteLLM and digivault.",
          "**B — Azure AI Foundry** — digichat + db only (`DefaultAzureCredential`). For client Azure environments; digithings has no Azure.",
        ],
      },
      { kind: "h", text: "Profile A (digigraph)" },
      {
        kind: "code",
        lang: "bash",
        code:
          "cp infra/digichat-release/.env.profile-a.example \\\n   infra/digichat-release/.env.profile-a\n# edit AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_EMBED_TENANTS, DIGI_IMAGE_TAG, provider keys\n\nmake digichat-profile-a-up",
      },
      {
        kind: "p",
        text:
          "Does not start digiquant / digisearch / digismith / heartbeat. Full operator guide: `docs/digichat/INSTALL.md`. Minimal compose overlays live under `infra/digichat-release/`.",
      },
    ],
  },
  {
    id: "architecture",
    title: "Architecture overview",
    blocks: [
      {
        kind: "p",
        text:
          "digigraph is the horizontal orchestrator. digisearch and digiquant each own vertical LangGraph pipelines and expose them as HTTP + MCP. digivault is the markdown knowledge vault. digikey issues RS256 JWTs; every protected service verifies JWKS. LiteLLM is the only LLM router. Loopback-only by default.",
      },
      { kind: "h", text: "Service map" },
      {
        kind: "list",
        items: [
          "`digigraph` `:8000` — workflows, OpenAI-compatible chat, federated tools",
          "`digiquant` `:8001` — NautilusTrader backtest / optimize",
          "`digisearch` `:8002` — RAG ingest + query",
          "`digismith` `:8003` — observability helpers + status",
          "`digivault` `:8004` — vault (opt-in compose profile)",
          "`digikey` `:8005` — API keys + JWT exchange + JWKS",
          "`digichat` `:3005` — Next.js BFF + chat UI (profile `digichat`)",
          "LiteLLM `:4000` — provider proxy; Ollama in Compose on host `:11435` (models optional)",
        ],
      },
      { kind: "h", text: "Chat path (simplified)" },
      {
        kind: "p",
        text:
          "Browser → digichat → digikey (session/JWT) → digigraph → LiteLLM; digigraph may call digisearch, digiquant, or digivault tools with the same JWT and `X-Request-ID`.",
      },
      { kind: "h", text: "Non-negotiables" },
      {
        kind: "list",
        items: [
          "Polars only — never pandas",
          "Pydantic v2 models on the wire",
          "MCP-first tool design",
          "NautilusTrader for all backtest / optimize paths",
          "Never expose live-trading without explicit human approval",
        ],
      },
      {
        kind: "p",
        text:
          "Canonical detail: root `ARCHITECTURE.md` and each module's `ARCHITECTURE.md`. This page's module sections below are the operator-facing API reference; machine-readable OpenAPI is at [OpenAPI explorer](/docs/api/).",
      },
    ],
  },
  {
    id: "authentication",
    title: "Authentication",
    blocks: [
      {
        kind: "p",
        text:
          "digikey is the single issuer of RS256 JWTs. Services verify tokens against digikey's JWKS and enforce per-route scopes. The flow: mint an API key (admin), exchange it for a short-lived JWT, then call services with `Authorization: Bearer <jwt>`.",
      },
      { kind: "h", text: "1 · Mint an API key (admin)" },
      {
        kind: "code",
        lang: "bash",
        code:
          'curl -X POST $DIGIKEY_URL/v1/admin/keys \\\n  -H "Authorization: Bearer $DIGIKEY_ADMIN_TOKEN" \\\n  -H "content-type: application/json" \\\n  -d \'{"tenant_slug":"acme","scopes":["digiquant:backtest","digigraph:workflow"]}\'\n# → { "api_key": "dgk_live_… (shown once)", "key_prefix": "dgk_live_…", "id": "<uuid>" }',
      },
      { kind: "h", text: "2 · Exchange for a JWT" },
      {
        kind: "code",
        lang: "bash",
        code:
          'curl -X POST $DIGIKEY_URL/v1/oauth/token \\\n  -H "content-type: application/json" \\\n  -d \'{"grant_type":"api_key","api_key":"\'"$DIGI_API_KEY"\'"}\'\n# → { "access_token": "<JWT>", "token_type": "Bearer", "expires_in": 900 }',
      },
      {
        kind: "code",
        lang: "python",
        code:
          'import os, httpx\n\ntok = httpx.post(\n    f"{os.environ[\'DIGIKEY_URL\']}/v1/oauth/token",\n    json={"grant_type": "api_key", "api_key": os.environ["DIGI_API_KEY"]},\n).json()["access_token"]',
      },
      {
        kind: "code",
        lang: "typescript",
        code:
          'const r = await fetch(`${process.env.DIGIKEY_URL}/v1/oauth/token`, {\n  method: "POST",\n  headers: { "content-type": "application/json" },\n  body: JSON.stringify({ grant_type: "api_key", api_key: process.env.DIGI_API_KEY }),\n});\nconst { access_token } = await r.json();',
      },
      { kind: "h", text: "3 · Call a service" },
      {
        kind: "code",
        lang: "bash",
        code:
          'curl -X POST $DIGIGRAPH_URL/workflow \\\n  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \\\n  -d \'{"prompt":"Backtest a momentum strategy on AAPL"}\'',
      },
      { kind: "h", text: "Scopes" },
      {
        kind: "list",
        items: [
          "`digigraph:workflow`, `digigraph:chat`, `digigraph:mcp`",
          "`digiquant:backtest`, `digiquant:optimize`",
          "`digisearch:query`, `digisearch:ingest`",
          "JWTs are short-lived (default 900s); revoke a key via `POST /v1/admin/keys/{id}/revoke`.",
        ],
      },
    ],
  },
  {
    id: "conventions",
    title: "Conventions",
    blocks: [
      { kind: "h", text: "Liveness vs status" },
      {
        kind: "p",
        text:
          '`GET /healthz` is the auth-exempt liveness probe — always `{"ok": true}`, for load balancers. `GET /v1/status` (digigraph, digismith) is a richer operator diagnostic; never use it for health checks.',
      },
      { kind: "h", text: "Error envelope" },
      { kind: "p", text: "Every service returns the same error shape:" },
      {
        kind: "code",
        lang: "json",
        code:
          '{\n  "error": {\n    "code": "http_401",\n    "message": "Bearer token required",\n    "request_id": "req-…",\n    "service": "digigraph"\n  }\n}',
      },
      {
        kind: "list",
        items: [
          "`http_401` — missing/invalid token · `http_403` / `insufficient_scope` — scope denied.",
          "`validation_error` — request body failed validation.",
          "`rate_limited` — HTTP 429, with a `Retry-After` header.",
        ],
      },
      { kind: "h", text: "Correlation" },
      {
        kind: "p",
        text:
          "Send `X-Request-ID` to correlate a call across services; it is generated if absent and echoed on the response and in the audit log.",
      },
      { kind: "h", text: "Rate limits & CORS" },
      {
        kind: "p",
        text:
          "Mutating routes are rate-limited per IP (typically 10/min, 429 + `Retry-After` on breach). CORS uses an explicit allowlist (`DIGI_CORS_ORIGINS`) — no wildcard — with credentials enabled for session cookies.",
      },
    ],
  },
];
