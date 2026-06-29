/**
 * Full API reference content for the digithings stack, keyed by module id and
 * merged with the base `ModuleNode` (tagline/summary/stack/links) at render time.
 *
 * Authored from the codebase (each `{component}/ARCHITECTURE.md` + server.py) and
 * kept honest by the OpenAPI contract tests (`tests/contracts/test_openapi_contract.py`).
 * It is static — no runtime fetch — so the site exports cleanly to Cloudflare.
 *
 * Examples use base-URL variables ($DIGIGRAPH_URL, $DIGIKEY_URL, …) rather than a
 * hardcoded host:port — the canonical ports live only in docker-compose.yml.
 */

export type Method = "GET" | "POST" | "PUT" | "DELETE";

export interface Field {
  name: string;
  type: string;
  required?: boolean;
  description: string;
}

export interface CodeExample {
  lang: "bash" | "python" | "typescript";
  code: string;
}

export interface Endpoint {
  method: Method;
  path: string;
  summary: string;
  auth?: string; // e.g. "digisearch:query", "none", "admin token"
  rateLimit?: string; // e.g. "10/min/IP"
  flag?: string; // env flag that gates the route
  request?: Field[];
  responseFields?: Field[];
  responseExample?: string; // JSON string, when a shape is clearer than a table
  examples?: CodeExample[];
}

export interface EnvVar {
  name: string;
  def?: string;
  required?: boolean;
  description: string;
}

export interface McpTool {
  name: string;
  description: string;
}

export interface InterfaceItem {
  signature: string;
  description: string;
}

export interface ModuleApiDoc {
  /** Base URL variable used in examples, e.g. "$DIGIGRAPH_URL". */
  baseUrlVar?: string;
  authNote?: string;
  scopes?: { scope: string; grants: string }[];
  run?: { compose?: string; standalone?: string; mcp?: string; cli?: string };
  env?: EnvVar[];
  endpoints?: Endpoint[];
  /** For library / CLI modules instead of HTTP endpoints. */
  publicInterface?: InterfaceItem[];
  mcp?: McpTool[];
  notes?: string[];
}

const BEARER = (v: string) => `-H "Authorization: Bearer $${v}"`;

export const apiDocs: Record<string, ModuleApiDoc> = {
  // ─────────────────────────────────────────────────────────────────────────
  digigraph: {
    baseUrlVar: "DIGIGRAPH_URL",
    authNote:
      "Endpoints accept a digikey-issued RS256 JWT in `Authorization: Bearer`. " +
      "When no JWKS is configured the service runs in passthrough mode (dev/test only). " +
      "`/healthz` and `/v1/status` are auth-exempt.",
    scopes: [
      { scope: "digigraph:workflow", grants: "POST /workflow + debug routes (default fallback)" },
      { scope: "digigraph:chat", grants: "/v1/chat/completions, /v1/models, /v1/model-info" },
      { scope: "digigraph:mcp", grants: "/threads/*, /files/* (when enabled)" },
    ],
    run: {
      compose: "docker compose up -d digigraph",
      standalone: "uvicorn digigraph.server:app",
      mcp: "FastMCP streamable-http (workflow, chat, thread_state, list_orchestrator_tools)",
    },
    env: [
      { name: "DIGIQUANT_URL", description: "DigiQuant base URL (defaults to the compose service URL)." },
      { name: "DIGISEARCH_URL", description: "DigiSearch base URL; empty disables retrieval." },
      { name: "DIGIKEY_JWKS_URL", description: "JWT public-key (JWKS) endpoint." },
      { name: "OPENAI_API_BASE", description: "LiteLLM proxy base URL." },
      { name: "DIGI_LLM_MODE", def: "test", description: "Model tier: test / medium / best." },
      { name: "DIGI_CHECKPOINTER", def: "memory", description: "LangGraph state backend: memory / sqlite / postgres / none." },
      { name: "DIGI_ENABLE_THREAD_API", def: "0", description: "Gate /threads/* and /files/*." },
      { name: "DIGI_ENABLE_DEBUG_ENDPOINTS", def: "0", description: "Gate /test_llm and /v1/debug/*." },
    ],
    endpoints: [
      {
        method: "GET",
        path: "/healthz",
        summary: "Liveness probe. Auth-exempt; always 200.",
        auth: "none",
        responseExample: `{ "ok": true }`,
        examples: [{ lang: "bash", code: `curl $DIGIGRAPH_URL/healthz` }],
      },
      {
        method: "GET",
        path: "/v1/status",
        summary: "Public, secret-free project status.",
        auth: "none",
        rateLimit: "30/min/IP",
        responseExample: `{
  "service": "digigraph",
  "project_name": "demo",
  "agents_enabled": true,
  "llm_mode": "test",
  "mcp_enabled": true,
  "workflow_profile": "default"
}`,
        examples: [{ lang: "bash", code: `curl $DIGIGRAPH_URL/v1/status` }],
      },
      {
        method: "POST",
        path: "/workflow",
        summary: "Run the full research + backtest graph (DigiClaw custom skill).",
        auth: "digigraph:workflow (optional)",
        rateLimit: "10/min/IP",
        request: [
          { name: "prompt", type: "string", required: true, description: "The user request to route through the supervisor." },
          { name: "session_id", type: "string", description: "Conversation/session correlation id." },
          { name: "allowed_tools", type: "string[]", description: "Tool allowlist override for this run." },
          { name: "digi_bearer", type: "string", description: "JWT forwarded downstream to DigiSearch/DigiQuant." },
        ],
        responseFields: [
          { name: "success", type: "boolean", description: "Whether the workflow completed." },
          { name: "message", type: "string", description: "Human-readable summary or full RAG answer." },
          { name: "backtest_result", type: "object | null", description: "DigiQuant BacktestResult, if a backtest ran." },
          { name: "rag_sources", type: "object[] | null", description: "Aggregated DigiSearch citations." },
        ],
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGIGRAPH_URL/workflow \\
  ${BEARER("JWT")} -H "content-type: application/json" \\
  -d '{"prompt": "Backtest a momentum strategy on AAPL"}'`,
          },
          {
            lang: "python",
            code: `import os, httpx

r = httpx.post(
    f"{os.environ['DIGIGRAPH_URL']}/workflow",
    headers={"Authorization": f"Bearer {os.environ['DIGI_JWT']}"},
    json={"prompt": "Backtest a momentum strategy on AAPL"},
    timeout=120,
)
print(r.json()["message"])`,
          },
          {
            lang: "typescript",
            code: `const r = await fetch(\`\${process.env.DIGIGRAPH_URL}/workflow\`, {
  method: "POST",
  headers: {
    Authorization: \`Bearer \${process.env.DIGI_JWT}\`,
    "content-type": "application/json",
  },
  body: JSON.stringify({ prompt: "Backtest a momentum strategy on AAPL" }),
});
const { message } = await r.json();`,
          },
        ],
      },
      {
        method: "POST",
        path: "/v1/chat/completions",
        summary: "OpenAI-compatible chat. Set stream:true for SSE (events: tool_call, content, done).",
        auth: "digigraph:chat (optional)",
        rateLimit: "10/min/IP",
        request: [
          { name: "model", type: "string", description: 'Model id; default "sitaas-rag".' },
          { name: "messages", type: "{role,content}[]", required: true, description: "Chat messages." },
          { name: "stream", type: "boolean", description: "Stream tokens as SSE." },
        ],
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGIGRAPH_URL/v1/chat/completions \\
  ${BEARER("JWT")} -H "content-type: application/json" \\
  -d '{"model":"sitaas-rag","messages":[{"role":"user","content":"hi"}]}'`,
          },
          {
            lang: "python",
            code: `from openai import OpenAI
client = OpenAI(base_url=os.environ["DIGIGRAPH_URL"] + "/v1", api_key=os.environ["DIGI_JWT"])
resp = client.chat.completions.create(
    model="sitaas-rag",
    messages=[{"role": "user", "content": "hi"}],
)`,
          },
        ],
      },
      {
        method: "GET",
        path: "/v1/models",
        summary: "OpenAI-style model list.",
        auth: "digigraph:chat (optional)",
        rateLimit: "30/min/IP",
        examples: [{ lang: "bash", code: `curl $DIGIGRAPH_URL/v1/models ${BEARER("JWT")}` }],
      },
    ],
    mcp: [
      { name: "workflow(prompt, thread_id?)", description: "Run the full research + backtest graph; returns a JSON WorkflowResult." },
      { name: "chat(message, thread_id?, model?)", description: "Single-turn chat via /v1/chat/completions." },
      { name: "thread_state(thread_id)", description: "Return the LangGraph checkpoint state for a thread." },
      { name: "list_orchestrator_tools()", description: "List registered orchestrator tool names." },
      { name: "list_orchestrator_tools_detailed()", description: "Tool manifest: name, tags, dynamic_schema flag." },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digiquant: {
    baseUrlVar: "DIGIQUANT_URL",
    authNote:
      "Backtest/optimize/pipeline routes accept a digikey JWT (optional in passthrough mode). " +
      "Async jobs stream progress over SSE.",
    scopes: [
      { scope: "digiquant:backtest", grants: "/run_backtest, /backtest/*, /v1/jobs/*, /v1/orchestrator_tools" },
      { scope: "digiquant:optimize", grants: "/run_optimize, /run_pipeline, /v1/workflow" },
    ],
    run: {
      compose: "docker compose up -d digiquant",
      standalone: "uvicorn digiquant.server:app",
    },
    env: [
      { name: "DIGIQUANT_DATA_DIR", def: "/app/data", description: "Directory of OHLCV CSVs for backtests." },
      { name: "DIGIKEY_JWKS_URL", description: "JWT public-key (JWKS) endpoint." },
      { name: "DIGIQUANT_ALLOW_EXPORT", def: "1", description: "Enable export of strategy configs." },
    ],
    endpoints: [
      {
        method: "GET",
        path: "/strategies",
        summary: "List registered NautilusTrader strategies.",
        auth: "none",
        rateLimit: "30/min/IP",
        responseExample: `[{ "name": "mean_reversion_tech", "aliases": [], "description": "...", "default_params": {} }]`,
        examples: [{ lang: "bash", code: `curl $DIGIQUANT_URL/strategies` }],
      },
      {
        method: "POST",
        path: "/run_backtest",
        summary: "Synchronous backtest. Returns a BacktestResult.",
        auth: "digiquant:backtest (optional)",
        rateLimit: "10/min/IP",
        request: [
          { name: "strategy_name", type: "string", required: true, description: "Registered strategy id." },
          { name: "symbols", type: "string[]", required: true, description: "Instruments to test." },
          { name: "data_dir", type: "string", description: "Directory of {symbol}.csv OHLCV files." },
          { name: "strategy_params", type: "object", description: "Strategy parameter overrides." },
          { name: "full_tearsheet", type: "boolean", description: "Include extended charts (default true)." },
        ],
        responseFields: [
          { name: "run_id", type: "string", description: "Unique run identifier." },
          { name: "total_pnl", type: "number", description: "Total P&L." },
          { name: "sharpe_ratio", type: "number | null", description: "Sharpe ratio." },
          { name: "num_trades", type: "integer", description: "Number of trades executed." },
          { name: "status", type: "string", description: '"completed" | "failed".' },
        ],
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGIQUANT_URL/run_backtest \\
  ${BEARER("JWT")} -H "content-type: application/json" \\
  -d '{"strategy_name":"mean_reversion_tech","symbols":["AAPL"]}'`,
          },
          {
            lang: "python",
            code: `r = httpx.post(
    f"{os.environ['DIGIQUANT_URL']}/run_backtest",
    headers={"Authorization": f"Bearer {os.environ['DIGI_JWT']}"},
    json={"strategy_name": "mean_reversion_tech", "symbols": ["AAPL"]},
    timeout=300,
)
print(r.json()["sharpe_ratio"])`,
          },
        ],
      },
      {
        method: "POST",
        path: "/backtest/start",
        summary: "Submit an async backtest job; returns {job_id}. Poll progress over SSE.",
        auth: "none",
        rateLimit: "10/min/IP",
        responseExample: `{ "job_id": "..." }`,
      },
      {
        method: "GET",
        path: "/backtest/{job_id}/progress",
        summary: "SSE stream of backtest progress events (JSON frames).",
        auth: "none",
        examples: [{ lang: "bash", code: `curl -N $DIGIQUANT_URL/backtest/$JOB_ID/progress` }],
      },
      {
        method: "POST",
        path: "/run_optimize",
        summary: "Parameter optimization (grid / bayesian / random). Returns best params.",
        auth: "digiquant:optimize (optional)",
        rateLimit: "10/min/IP",
        request: [
          { name: "strategy_name", type: "string", required: true, description: "Registered strategy id." },
          { name: "symbols", type: "string[]", required: true, description: "Instruments." },
          { name: "method", type: "string", description: '"grid" | "bayesian" | "random" (default grid).' },
          { name: "n_trials", type: "integer", description: "Trial budget (default 50)." },
          { name: "objective", type: "string", description: '"sharpe" | "return" | "pnl".' },
        ],
        responseFields: [
          { name: "best_params", type: "object", description: "Best parameter set found." },
          { name: "best_sharpe", type: "number | null", description: "Objective value at best params." },
          { name: "num_evaluations", type: "integer", description: "Trials evaluated." },
        ],
      },
      {
        method: "POST",
        path: "/run_pipeline",
        summary: "Full pipeline: backtest → optimize → export.",
        auth: "digiquant:optimize (optional)",
        rateLimit: "10/min/IP",
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digisearch: {
    baseUrlVar: "DIGISEARCH_URL",
    authNote: "All query/ingest routes require a digikey JWT carrying the matching scope.",
    scopes: [
      { scope: "digisearch:query", grants: "/query, /v1/research_turn, orchestrator routes, /indexes/*" },
      { scope: "digisearch:ingest", grants: "/ingest" },
    ],
    run: {
      compose: "docker compose up -d digisearch",
      standalone: "uvicorn digisearch.server:app",
      mcp: "digisearch mcp   (FastMCP streamable-http: digisearch_query, digisearch_research_turn)",
    },
    env: [
      { name: "CHROMA_PATH", description: "Persistent Chroma directory (activates the Chroma backend)." },
      { name: "AZURE_SEARCH_ENDPOINT", description: "Azure AI Search endpoint (alternative backend)." },
      { name: "AZURE_SEARCH_API_KEY", description: "Azure AI Search key." },
      { name: "OPENAI_API_KEY", description: "Embeddings provider key." },
      { name: "DIGIKEY_JWKS_URL", required: true, description: "JWT public-key endpoint." },
    ],
    endpoints: [
      {
        method: "POST",
        path: "/query",
        summary: "Hybrid / keyword / vector search over an index.",
        auth: "digisearch:query",
        rateLimit: "10/min/IP",
        request: [
          { name: "text", type: "string", required: true, description: "Query text." },
          { name: "index_name", type: "string", description: 'Target index (default "default").' },
          { name: "top_k", type: "integer", description: "Results to return, 1–100 (default 10)." },
          { name: "mode", type: "string", description: '"keyword" | "vector" | "hybrid" (default hybrid).' },
          { name: "filters", type: "{field,op,value}[]", description: "Structured metadata filters." },
        ],
        responseFields: [
          { name: "results", type: "object[]", description: "Normalized hits (chunk_id, doc_id, score, content, metadata)." },
          { name: "total", type: "integer", description: "Total matches." },
          { name: "backend", type: "string", description: '"chroma" | "azure_ai_search" | "stub".' },
        ],
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGISEARCH_URL/query \\
  ${BEARER("JWT")} -H "content-type: application/json" \\
  -d '{"text":"momentum factor","index_name":"default","top_k":5}'`,
          },
          {
            lang: "python",
            code: `r = httpx.post(
    f"{os.environ['DIGISEARCH_URL']}/query",
    headers={"Authorization": f"Bearer {os.environ['DIGI_JWT']}"},
    json={"text": "momentum factor", "top_k": 5},
)
for hit in r.json()["results"]:
    print(hit["score"], hit["content"][:80])`,
          },
        ],
      },
      {
        method: "POST",
        path: "/ingest",
        summary: "Ingest a document (parse → chunk → embed → index).",
        auth: "digisearch:ingest",
        rateLimit: "30/min/IP",
        request: [
          { name: "source", type: "string", required: true, description: "Server-side path to the document." },
          { name: "index_name", type: "string", description: "Target index." },
          { name: "doc_type", type: "string", description: "pdf | html | docx | markdown | csv | plaintext." },
          { name: "metadata", type: "object", description: "Evidence metadata (tier, venue, tags, …)." },
        ],
        responseExample: `{ "doc_id": "...", "chunks_created": 12, "index_name": "default", "status": "ok" }`,
      },
      {
        method: "POST",
        path: "/v1/research_turn",
        summary: "Composite research turn (plan → retrieve → aggregate) with citations.",
        auth: "digisearch:query",
        rateLimit: "10/min/IP",
        flag: "requires the digisearch[agent] extra",
      },
    ],
    mcp: [
      { name: "digisearch_query", description: "Search documents; returns formatted hits with score + preview." },
      { name: "digisearch_research_turn", description: "Composite research turn with citations (needs digisearch[agent])." },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digikey: {
    baseUrlVar: "DIGIKEY_URL",
    authNote:
      "digikey is the issuer. Admin routes require the `DIGIKEY_ADMIN_TOKEN` bearer; " +
      "token exchange takes a raw API key or a BFF-session grant. JWKS and /healthz are public.",
    scopes: [
      { scope: "digigraph:workflow / :chat / :mcp", grants: "DigiGraph routes" },
      { scope: "digiquant:backtest / :optimize", grants: "DigiQuant routes" },
      { scope: "digisearch:query / :ingest", grants: "DigiSearch routes" },
      { scope: "*", grants: "Wildcard (all scopes) — dev_global keys only" },
    ],
    run: {
      compose: "docker compose up -d digikey",
      standalone: "uvicorn digikey.server:app",
    },
    env: [
      { name: "DIGIKEY_DATABASE_URL", required: true, description: "SQLite or Postgres URL for key storage." },
      { name: "DIGIKEY_PRIVATE_KEY_PEM", description: "RSA 2048 PEM for RS256 signing (prod)." },
      { name: "DIGIKEY_ADMIN_TOKEN", required: true, description: "Bearer for POST /v1/admin/keys." },
      { name: "DIGIKEY_BFF_TOKEN", description: "Bearer for grant_type=bff_session (DigiChat)." },
      { name: "DIGIKEY_JWT_TTL_SEC", def: "900", description: "Access-token lifetime." },
      { name: "DIGIKEY_BLOCKLIST_REDIS_URL", description: "Redis for JWT revocation (prod)." },
    ],
    endpoints: [
      {
        method: "GET",
        path: "/.well-known/jwks.json",
        summary: "RSA public key set for verifying issued JWTs.",
        auth: "none",
        examples: [{ lang: "bash", code: `curl $DIGIKEY_URL/.well-known/jwks.json` }],
      },
      {
        method: "POST",
        path: "/v1/admin/keys",
        summary: "Create an API key. The raw key is returned ONCE.",
        auth: "admin token",
        rateLimit: "10/min/IP",
        request: [
          { name: "tenant_slug", type: "string", required: true, description: "Tenant identifier." },
          { name: "label", type: "string", description: "Human-readable key name." },
          { name: "scopes", type: "string[]", description: "Granted scopes." },
        ],
        responseExample: `{ "key_prefix": "dgk_live_…", "api_key": "dgk_live_…(once)", "id": "<uuid>" }`,
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGIKEY_URL/v1/admin/keys \\
  ${BEARER("DIGIKEY_ADMIN_TOKEN")} -H "content-type: application/json" \\
  -d '{"tenant_slug":"acme","scopes":["digiquant:backtest"]}'`,
          },
        ],
      },
      {
        method: "POST",
        path: "/v1/oauth/token",
        summary: "Exchange an API key (or BFF session) for a short-lived RS256 JWT.",
        auth: "none (key in body)",
        rateLimit: "10/min/IP",
        request: [
          { name: "grant_type", type: "string", required: true, description: '"api_key" | "bff_session".' },
          { name: "api_key", type: "string", description: "Raw dgk_live_ key (api_key grant)." },
          { name: "requested_scopes", type: "string[]", description: "Downscope to a subset of granted scopes." },
        ],
        responseExample: `{ "access_token": "<JWT>", "token_type": "Bearer", "expires_in": 900 }`,
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGIKEY_URL/v1/oauth/token \\
  -H "content-type: application/json" \\
  -d '{"grant_type":"api_key","api_key":"'"$DIGI_API_KEY"'"}'`,
          },
          {
            lang: "python",
            code: `tok = httpx.post(
    f"{os.environ['DIGIKEY_URL']}/v1/oauth/token",
    json={"grant_type": "api_key", "api_key": os.environ["DIGI_API_KEY"]},
).json()["access_token"]`,
          },
        ],
      },
      {
        method: "POST",
        path: "/v1/admin/keys/{key_id}/revoke",
        summary: "Revoke a key and blocklist its live JWTs (when Redis is configured).",
        auth: "admin token",
        rateLimit: "10/min/IP",
        responseExample: `{ "revoked": true, "jtis_invalidated": 3 }`,
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digismith: {
    baseUrlVar: "DIGISMITH_URL",
    authNote: "Status and metrics are public diagnostics. Tracing is a library wrapper, not an HTTP surface.",
    run: {
      compose: "docker compose up -d digismith",
      standalone: "uvicorn digismith.server:app",
    },
    env: [
      { name: "LANGSMITH_API_KEY", description: "Enable LangSmith trace export; absent = no-op." },
      { name: "LANGSMITH_ENDPOINT", def: "https://api.smith.langchain.com", description: "LangSmith API base (host shown in /v1/status)." },
      { name: "OTEL_EXPORTER_OTLP_ENDPOINT", description: "Enable OTel HTTP export when set." },
    ],
    endpoints: [
      {
        method: "GET",
        path: "/v1/status",
        summary: "Tracing configuration diagnostic (operator-facing; secret-free).",
        auth: "none",
        responseExample: `{
  "version": "0.1.0",
  "tracing_configured": true,
  "langsmith_sdk_installed": true,
  "langsmith_host": "api.smith.langchain.com",
  "request_id": "..."
}`,
        examples: [{ lang: "bash", code: `curl $DIGISMITH_URL/v1/status` }],
      },
      { method: "GET", path: "/metrics", summary: "Prometheus metrics (text/plain 0.0.4).", auth: "none" },
    ],
    publicInterface: [
      {
        signature: "from digismith.trace import traceable",
        description:
          "@traceable(\"name\") wraps a function with langsmith.traceable when LANGSMITH_API_KEY is set; otherwise a no-op. PII is redacted from span inputs/outputs.",
      },
      {
        signature: "from digismith.config import tracing_enabled",
        description: "Returns True when tracing is configured (key set + SDK importable).",
      },
    ],
    notes: [
      "Span attributes SHOULD include workflow_id, request_id, session_id, job_id.",
      "Spans MUST NOT include raw prompts/completions, secrets, or full document bodies.",
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digichat: {
    baseUrlVar: "DIGICHAT_URL",
    authNote:
      "The deployed digithings.ai chat is an agentic Cloudflare Pages Function (no login) that " +
      "grounds answers in the digivault docs. The full Docker BFF additionally authenticates users " +
      "via NextAuth and exchanges a BFF session for a digikey JWT to call DigiGraph.",
    run: {
      compose: "docker compose --profile digichat up -d",
      cli: "make digichat-dev   # Next.js dev server with hot reload",
    },
    env: [
      { name: "OPENROUTER_API_KEY", required: true, description: "LLM calls via OpenRouter free models." },
      { name: "CORE_SUPABASE_URL", required: true, description: "Vault Supabase project URL (RLS read)." },
      { name: "CORE_SUPABASE_ANON_KEY", required: true, description: "Anon key for RLS-gated vault reads." },
      { name: "AUTH_SECRET", description: "NextAuth secret (Docker BFF): openssl rand -base64 32." },
      { name: "DIGIKEY_BFF_TOKEN", description: "Bearer for grant_type=bff_session (Docker BFF)." },
    ],
    endpoints: [
      { method: "GET", path: "/api/health", summary: "Liveness probe.", auth: "none", responseExample: `{ "ok": true }` },
      {
        method: "POST",
        path: "/api/chat",
        summary: "Agentic chat grounded in digivault (single tool: search_digivault).",
        auth: "none (public, rate-limited)",
        request: [
          { name: "messages", type: "{role,content}[]", required: true, description: "Conversation so far." },
          { name: "model", type: "string", description: "OpenRouter free model id." },
        ],
        responseExample: `{ "content": "…grounded answer…", "tool_calls": [] }`,
        examples: [
          {
            lang: "bash",
            code: `curl -X POST $DIGICHAT_URL/api/chat \\
  -H "content-type: application/json" \\
  -d '{"messages":[{"role":"user","content":"What does digigraph do?"}]}'`,
          },
        ],
      },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digiclaw: {
    authNote: "CLI-only — no HTTP service. A heartbeat runner pings service health and appends an immutable audit log.",
    run: {
      cli: "python -m digiclaw            # one cycle\ndocker compose --profile heartbeat up -d heartbeat",
    },
    env: [
      { name: "DIGIGRAPH_URL", description: "DigiGraph base URL for health checks." },
      { name: "DIGIQUANT_URL", description: "DigiQuant base URL for health + drift checks." },
      { name: "DIGICLAW_DIGIKEY_API_KEY", description: "Key (digiquant:backtest+optimize) for auth-gated drift checks." },
      { name: "AUDIT_LOG_PATH", def: "digiquant/results/audit/events.jsonl", description: "Append-only JSONL audit destination." },
      { name: "REOPTIMIZE_STRATEGY", def: "mean_reversion_tech", description: "Strategy id for the drift check." },
    ],
    publicInterface: [
      { signature: "python -m digiclaw", description: "Run one heartbeat cycle: health-check services, run an auth-gated drift check, and (on drift) trigger re-optimization." },
      { signature: "audit_log(event_type, agent_id, payload)", description: "Append one redacted JSON line to the audit log." },
    ],
    notes: [
      "Audit event types: heartbeat, reoptimize_triggered, reoptimize_completed, reoptimize_failed, drift_check_skipped.",
      "Keys matching password / api_key / token / secret are redacted before write.",
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digibase: {
    authNote: "Shared Python library imported by every service — not a network surface.",
    run: { cli: "# installed as a dependency of each service; no standalone run" },
    publicInterface: [
      { signature: "from digibase.errors import register_fastapi_error_handlers", description: 'Standard error envelope: {error:{code,message,request_id,service}}.' },
      { signature: "from digibase.http import outbound_service_headers", description: "Builds X-Request-ID + Authorization headers for service-to-service calls." },
      { signature: "from digibase.http import install_request_id_middleware", description: "Reads/generates X-Request-ID, stores on request.state, echoes on the response." },
      { signature: "from digibase.audit import redact_mapping", description: "Redacts password/api_key/token/secret keys from a payload before logging." },
      { signature: "from digibase.metrics import install_metrics", description: "Mounts Prometheus /metrics with http_requests_total / _duration / _in_flight." },
      { signature: "from digibase.otel import setup_otel_fastapi", description: "Optional OTel wiring; no-op unless OTEL_EXPORTER_OTLP_ENDPOINT is set." },
    ],
    env: [
      { name: "DIGI_ENV", def: "dev", description: "Environment label for metrics." },
      { name: "DIGI_CORS_ORIGINS", description: "Global CORS allowlist (comma-separated)." },
      { name: "DIGI_PII_PATTERNS", description: "Extra regex patterns for PII redaction." },
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digistore: {
    authNote: "Roadmap. Today a session-scoped dataset manager lives inside digigraph; the standalone storage service is planned.",
    notes: [
      "Planned: one storage API over S3, MinIO, Postgres, or SQLite so business code never binds to a backend.",
      "Planned surface: DigiStore.configure(backend=…) + get/put/list over a backend-neutral interface.",
    ],
  },

  // ─────────────────────────────────────────────────────────────────────────
  digilink: {
    authNote: "Roadmap. Today MCP is built into individual modules (e.g. digisearch-mcp).",
    notes: [
      "Planned: a protocol bridge registering adapters that turn REST, gRPC, or bespoke transports into MCP tools.",
      "Planned surface: digilink.register_adapter(\"rest\", …) to expose a non-native transport as MCP.",
    ],
  },
};
