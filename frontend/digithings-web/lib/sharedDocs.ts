/**
 * Shared guide sections for the docs (rendered above the per-module reference and
 * included in the "Copy all as Markdown" export). Structured as simple blocks so a
 * single renderer + markdown serializer covers them. Codebase-accurate; examples
 * use base-URL variables rather than hardcoded host:port.
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
      { kind: "p", text: "digithings is an open-core agentic stack — orchestration, quant research, retrieval, and chat behind one supervisor. Self-hosted, BYOK, audit-on by default." },
      { kind: "h", text: "Prerequisites" },
      { kind: "list", items: ["Docker (with Compose)", "Python ≥ 3.12 (for running services outside Docker)", "Node.js LTS (for the frontends)"] },
      { kind: "h", text: "Run the whole stack" },
      { kind: "code", lang: "bash", code: "git clone https://github.com/digithings-ai/digithings && cd digithings\ncp .env.example .env   # add your keys\ndocker compose up -d" },
      { kind: "p", text: "Each backend service exposes a liveness probe at `GET /healthz`. The service URLs and ports are defined in `docker-compose.yml`; reference them through env vars (`$DIGIGRAPH_URL`, `$DIGIKEY_URL`, …) rather than hardcoding an address." },
      { kind: "h", text: "Essential environment" },
      { kind: "list", items: [
        "`OPENROUTER_API_KEY` / `OPENAI_API_KEY` — LLM access via the LiteLLM proxy.",
        "`DIGIKEY_ADMIN_TOKEN` — required to mint API keys (see Authentication).",
        "`DIGIKEY_PRIVATE_KEY_PEM` — stable RS256 signing key for production.",
        "See `.env.example` for the full, annotated list.",
      ] },
      { kind: "h", text: "Useful make targets" },
      { kind: "list", items: [
        "`make up` / `make down` — start / stop the core stack.",
        "`make up-digichat` — start the chat BFF + its Postgres.",
        "`make stack-local` — run the Python services without Docker.",
        "`make test-unit` — unit tests (no stack required).",
      ] },
    ],
  },
  {
    id: "authentication",
    title: "Authentication",
    blocks: [
      { kind: "p", text: "digikey is the single issuer of RS256 JWTs. Services verify tokens against digikey's JWKS and enforce per-route scopes. The flow: mint an API key (admin), exchange it for a short-lived JWT, then call services with `Authorization: Bearer <jwt>`." },
      { kind: "h", text: "1 · Mint an API key (admin)" },
      { kind: "code", lang: "bash", code: 'curl -X POST $DIGIKEY_URL/v1/admin/keys \\\n  -H "Authorization: Bearer $DIGIKEY_ADMIN_TOKEN" \\\n  -H "content-type: application/json" \\\n  -d \'{"tenant_slug":"acme","scopes":["digiquant:backtest","digigraph:workflow"]}\'\n# → { "api_key": "dgk_live_… (shown once)", "key_prefix": "dgk_live_…", "id": "<uuid>" }' },
      { kind: "h", text: "2 · Exchange for a JWT" },
      { kind: "code", lang: "bash", code: 'curl -X POST $DIGIKEY_URL/v1/oauth/token \\\n  -H "content-type: application/json" \\\n  -d \'{"grant_type":"api_key","api_key":"\'"$DIGI_API_KEY"\'"}\'\n# → { "access_token": "<JWT>", "token_type": "Bearer", "expires_in": 900 }' },
      { kind: "code", lang: "python", code: 'import os, httpx\n\ntok = httpx.post(\n    f"{os.environ[\'DIGIKEY_URL\']}/v1/oauth/token",\n    json={"grant_type": "api_key", "api_key": os.environ["DIGI_API_KEY"]},\n).json()["access_token"]' },
      { kind: "code", lang: "typescript", code: 'const r = await fetch(`${process.env.DIGIKEY_URL}/v1/oauth/token`, {\n  method: "POST",\n  headers: { "content-type": "application/json" },\n  body: JSON.stringify({ grant_type: "api_key", api_key: process.env.DIGI_API_KEY }),\n});\nconst { access_token } = await r.json();' },
      { kind: "h", text: "3 · Call a service" },
      { kind: "code", lang: "bash", code: 'curl -X POST $DIGIGRAPH_URL/workflow \\\n  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \\\n  -d \'{"prompt":"Backtest a momentum strategy on AAPL"}\'' },
      { kind: "h", text: "Scopes" },
      { kind: "list", items: [
        "`digigraph:workflow`, `digigraph:chat`, `digigraph:mcp`",
        "`digiquant:backtest`, `digiquant:optimize`",
        "`digisearch:query`, `digisearch:ingest`",
        "JWTs are short-lived (default 900s); revoke a key via `POST /v1/admin/keys/{id}/revoke`.",
      ] },
    ],
  },
  {
    id: "conventions",
    title: "Conventions",
    blocks: [
      { kind: "h", text: "Liveness vs status" },
      { kind: "p", text: "`GET /healthz` is the auth-exempt liveness probe — always `{\"ok\": true}`, for load balancers. `GET /v1/status` (DigiGraph, DigiSmith) is a richer operator diagnostic; never use it for health checks." },
      { kind: "h", text: "Error envelope" },
      { kind: "p", text: "Every service returns the same error shape:" },
      { kind: "code", lang: "json", code: '{\n  "error": {\n    "code": "http_401",\n    "message": "Bearer token required",\n    "request_id": "req-…",\n    "service": "digigraph"\n  }\n}' },
      { kind: "list", items: [
        "`http_401` — missing/invalid token · `http_403` / `insufficient_scope` — scope denied.",
        "`validation_error` — request body failed validation.",
        "`rate_limited` — HTTP 429, with a `Retry-After` header.",
      ] },
      { kind: "h", text: "Correlation" },
      { kind: "p", text: "Send `X-Request-ID` to correlate a call across services; it is generated if absent and echoed on the response and in the audit log." },
      { kind: "h", text: "Rate limits & CORS" },
      { kind: "p", text: "Mutating routes are rate-limited per IP (typically 10/min, 429 + `Retry-After` on breach). CORS uses an explicit allowlist (`DIGI_CORS_ORIGINS`) — no wildcard — with credentials enabled for session cookies." },
    ],
  },
];
