/**
 * Per-module showcase content for the expanded mosaic card (#4429).
 *
 * One record per module: the pipeline stages for the strip, the capability
 * rows, the copy-paste snippet, and the proof ledger. Every claim below was
 * lifted from the per-module research briefs (code-verified, [UNVERIFIED]
 * items excluded) — no invented numbers, no roadmap-as-shipped, no secrets.
 *
 * Roadmap modules (digistore, digilink) carry planned stages + capabilities
 * and NO runnable snippet; the showcase renders them muted with a badge.
 */
import type { ModuleNode } from "./modules";

export interface ShowcaseCapability {
  title: string;
  line: string;
}

export interface ShowcaseProof {
  term: string;
  value: string;
}

export interface ModuleShowcase {
  /** Stage labels for the strip. `planned: true` renders them as intent. */
  stages: { label: string; detail: string }[];
  planned?: boolean;
  capabilities: ShowcaseCapability[];
  /** Runnable snippet. Absent for roadmap modules (nothing runs yet). */
  snippet?: { lang: string; code: string };
  proof: ShowcaseProof[];
}

function flowOf(m: ModuleNode): { label: string; detail: string }[] {
  return (m.flow?.stages ?? []).map((s) => ({ label: s.label, detail: s.detail }));
}

export function showcaseFor(m: ModuleNode): ModuleShowcase {
  const fromFlow = flowOf(m);
  switch (m.id) {
    case "digigraph":
      return {
        stages: [
          { label: "ask", detail: "Chat, workflow, or MCP call arrives with a digikey JWT." },
          { label: "route", detail: "Profile + supervisor budget pick the sub-graph." },
          { label: "retrieve + reason", detail: "digisearch/vault tools, brief builder, compaction." },
          { label: "validate + backtest", detail: "digiquant runs strategies behind the same JWT." },
          { label: "stream", detail: "One SSE answer back, traces + files attached." },
        ],
        capabilities: [
          { title: "StateGraph router", line: "Profiles (full_stack, research_rag, quant_backtest) pick the path; conditional edges, not if-else." },
          { title: "Supervisor budget", line: "Opt-in entry node stamps the run and enforces a recursion budget." },
          { title: "Research sub-graph", line: "Model-driven tool loop plus a typed ResearchBrief; skippable per project." },
          { title: "Tool registry + skills", line: "Named tools with schemas and when() predicates; vertical schemas fetched lazily." },
          { title: "OpenAI-compatible API", line: "POST /v1/chat/completions streams SSE; POST /workflow runs a full graph." },
          { title: "MCP server", line: "Streamable-http on :8766 plus --stdio for Claude Desktop." },
        ],
        snippet: {
          lang: "bash",
          code: 'curl -s -X POST http://127.0.0.1:8000/workflow -H "Content-Type: application/json" -d \'{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}\'',
        },
        proof: [
          { term: "port", value: "8000" },
          { term: "liveness", value: "GET /healthz → {\"ok\": true}" },
          { term: "model id", value: "digigraph-rag" },
        ],
      };
    case "digiquant":
      return {
        stages: fromFlow,
        capabilities: [
          { title: "Strategy registry", line: "Slappers, sdca, rotation, and the six classics — registered by name with default params." },
          { title: "NautilusTrader backtests", line: "Bar-driven runs on a real engine; no number leaves without a completed result." },
          { title: "Three optimizers", line: "Grid, random, and Optuna Bayesian search over the parameter space." },
          { title: "Research + portfolio graphs", line: "Daily research phases and a thesis-first H1–H9 portfolio path." },
          { title: "Tearsheets + NAV", line: "Plotly tearsheets per strategy; delayed public NAV history." },
          { title: "Paper only", line: "Broker adapters are stubs or paper-gated. Live trading is not shipped." },
        ],
        snippet: {
          lang: "bash",
          code: "docker compose up -d digiquant\ndigiquant backtest -s ema_cross -S BTC-USD -d digiquant/data/BTC-USD.csv -v",
        },
        proof: [
          { term: "registry", value: "GET /strategies" },
          { term: "tearsheets", value: "digiquant.io/strategies" },
          { term: "signal delay", value: "3 days, enforced" },
        ],
      };
    case "digisearch":
      return {
        stages: [
          { label: "ingest", detail: "PDF/HTML/DOCX/MD/CSV parsed with sidecar metadata." },
          { label: "chunk", detail: "Chonkie semantic chunking, segment-aware." },
          { label: "embed + index", detail: "MiniLM or OpenAI embeds into Chroma, Vectorize, or Azure." },
          { label: "query", detail: "Keyword, vector, or hybrid with filters and rerank." },
          { label: "ground", detail: "Hits + citations back to agents via digigraph." },
        ],
        capabilities: [
          { title: "Parsers", line: "PDF, HTML, DOCX, Markdown, CSV — extension-detected, YAML sidecars." },
          { title: "Chunking", line: "Chonkie semantic default; pages and heading sections never split." },
          { title: "Two embedders", line: "Local MiniLM (no key) or OpenAI; SQLite embedding cache." },
          { title: "Three backends", line: "Chroma on disk, Cloudflare Vectorize, or Azure AI Search — env-selected." },
          { title: "Modes + filters", line: "Keyword, vector, hybrid hints with structured filters and rerank." },
          { title: "Web search", line: "First-party web_search that never writes to the corpus." },
        ],
        snippet: {
          lang: "bash",
          code: 'docker compose up -d digisearch\ncurl -s -X POST http://127.0.0.1:8002/query -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d \'{"text":"gold carry systematic trading","index_name":"default","mode":"hybrid","top_k":5}\'',
        },
        proof: [
          { term: "port", value: "8002" },
          { term: "liveness", value: "GET /healthz" },
          { term: "shape", value: "POST /query · /ingest · /docs" },
        ],
      };
    case "digichat":
      return {
        stages: fromFlow,
        capabilities: [
          { title: "/embed + widget", line: "Drop-in iframe or bottom-right launcher on any page you own." },
          { title: "Tenant registry", line: "Hostname-keyed tenants with theme, accent, and model access." },
          { title: "Auth.js humans", line: "OIDC login plus dev providers; stateless encrypted session cookie." },
          { title: "Digikey + BYOK", line: "Per-turn exchange; visitor provider keys live for the request only." },
          { title: "Tool catalog", line: "Force-tool, disabled-tools, and MCP servers per session." },
          { title: "Sources + threads", line: "Grounded answers with Sources cards; threads in localStorage + Postgres." },
        ],
        snippet: {
          lang: "bash",
          code: "make up-digichat\ncurl -sf http://127.0.0.1:3005/api/health | python3 -m json.tool",
        },
        proof: [
          { term: "embed", value: "/embed?host=…&theme=" },
          { term: "health", value: "GET /api/health" },
          { term: "release", value: "v2.3.2" },
        ],
      };
    case "digikey":
      return {
        stages: [
          { label: "issue key", detail: "Operator creates a scoped dgk_live_ secret, shown once." },
          { label: "exchange", detail: "Key or BFF session traded at /v1/oauth/token for a 15-minute JWT." },
          { label: "verify locally", detail: "Each service checks signature + scopes against cached JWKS." },
          { label: "forward", detail: "digigraph passes the same JWT to digiquant and digisearch." },
          { label: "revoke", detail: "Key or session blocklisted in Redis; new exchanges refused." },
        ],
        capabilities: [
          { title: "RS256 JWTs", line: "15-minute tokens, kid header, tenant + scope claims." },
          { title: "JWKS", line: "Public key set served locally; services verify without calling back." },
          { title: "Two grants", line: "api_key for machines, bff_session for logged-in humans." },
          { title: "Scope language", line: "Wildcards, service prefixes, exact match — plus downscoping." },
          { title: "Revocation", line: "Key and session revoke endpoints with a Redis blocklist." },
          { title: "Middleware", line: "One Starlette middleware with per-service path-scope tables." },
        ],
        snippet: {
          lang: "bash",
          code: 'curl -s http://127.0.0.1:8005/v1/oauth/token -H \'Content-Type: application/json\' -d \'{"grant_type":"api_key","api_key":"dgk_live_..."}\'\ncurl -s http://127.0.0.1:8005/.well-known/jwks.json',
        },
        proof: [
          { term: "port", value: "8005" },
          { term: "scopes", value: "digigraph:workflow · digiquant:backtest · …" },
          { term: "ttl", value: "900s" },
        ],
      };
    case "digismith":
      return {
        stages: [
          { label: "decorate", detail: "One @traceable on the LLM entry point." },
          { label: "redact", detail: "Emails, key prefixes, phones scrubbed pre-export." },
          { label: "export", detail: "Spans batch to LangSmith — or no-op when unconfigured." },
          { label: "inspect", detail: "GET /v1/status answers “is tracing on?” with zero secrets." },
        ],
        capabilities: [
          { title: "Opt-in tracing", line: "Decorator is a pure no-op without a LangSmith key — zero overhead." },
          { title: "PII redaction", line: "Native LangSmith hooks replace emails, keys, phones before export." },
          { title: "Secret-free status", line: "SmithStatus model: version, flags, hostname-only host, request id." },
          { title: "Metrics", line: "Prometheus request/latency/in-flight series per service." },
          { title: "Request IDs", line: "X-Request-ID threaded through spans, logs, and status bodies." },
          { title: "Opt-in OTel", line: "Service HTTP spans only, strictly off unless an endpoint is set." },
        ],
        snippet: {
          lang: "bash",
          code: "docker compose up -d digismith\ncurl -s http://localhost:8003/healthz\ncurl -s http://localhost:8003/v1/status",
        },
        proof: [
          { term: "port", value: "8003" },
          { term: "status", value: "GET /v1/status (never a secret)" },
          { term: "receives traces", value: "no — export is SDK-direct" },
        ],
      };
    case "digiclaw":
      return {
        stages: [
          { label: "probe", detail: "Ping digigraph + digiquant health every 30 minutes." },
          { label: "gate", detail: "Auth-gated drift check; re-optimize only on detected drift." },
          { label: "tick", detail: "Cron + continuous scheduler wakes digisearch monitors." },
          { label: "append", detail: "Redacted JSONL audit line; optional sink mirror." },
        ],
        capabilities: [
          { title: "Single-shot heartbeat", line: "One cycle, exit 0/1. Not a daemon, no server, no UI." },
          { title: "Append-only audit", line: "One JSONL trail every service shares; secrets redacted pre-write." },
          { title: "Scheduler", line: "Cron + continuous agents with start/stop/pause/resume lifecycle." },
          { title: "Drift guardrail", line: "ADDM check behind digikey auth; skipped cleanly without a key." },
          { title: "Monitors tick", line: "Wakes scheduled digisearch watches every 60 seconds." },
        ],
        snippet: {
          lang: "bash",
          code: "docker compose --profile heartbeat up -d\npython -m digiclaw\ncat digiquant/results/audit/events.jsonl | head -20",
        },
        proof: [
          { term: "cadence", value: "every 30 minutes" },
          { term: "events", value: "heartbeat · reoptimize_triggered · …" },
          { term: "server", value: "none — CLI only" },
        ],
      };
    case "digivault":
      return {
        stages: [
          { label: "collect", detail: "Crawl + classify client sites, APIs, repos." },
          { label: "file", detail: "Frontmatter, [[wikilinks]], tags, taxonomy." },
          { label: "check", detail: "Lint backlinks, orphans, duplicates." },
          { label: "publish", detail: "Sync the vault to D1 or serve the local root." },
          { label: "cite", detail: "Search excerpt, load whole note, ground the reply." },
        ],
        capabilities: [
          { title: "Note CRUD", line: "List, read, create, rename — links rewritten on rename." },
          { title: "Link graph", line: "Backlinks, tag search, neighbors across the vault." },
          { title: "Vault lint", line: "Unresolved links, missing frontmatter, orphans — in CI." },
          { title: "Three stores", line: "Filesystem default; D1 FTS or Supabase behind env." },
          { title: "Orchestrator tools", line: "Search-then-load pair digigraph calls per turn." },
          { title: "MCP sidecar", line: "Notes tools for IDE agents; writes key-gated." },
        ],
        snippet: {
          lang: "bash",
          code: "docker compose --profile digivault up -d digivault\nexport DIGIVAULT_ROOT=/tmp/demo-vault\ndigivault init --root \"$DIGIVAULT_ROOT\"\ndigivault new-note hello --title \"Hello\" --root \"$DIGIVAULT_ROOT\"",
        },
        proof: [
          { term: "port", value: "8004" },
          { term: "tools", value: "digivault_search_notes · digivault_get_note" },
          { term: "auth", value: "digikey JWT (reads need a scope)" },
        ],
      };
    case "digibase":
      return {
        stages: [
          { label: "import", detail: "One package every Python service installs." },
          { label: "standardize", detail: "Same error envelope on every route." },
          { label: "correlate", detail: "Same X-Request-ID across hops." },
          { label: "redact", detail: "Same secret scrubbing before any audit write." },
          { label: "observe", detail: "Same /metrics labels fleet-wide." },
        ],
        capabilities: [
          { title: "Error envelope", line: "{error: {code, message, request_id, service}} everywhere." },
          { title: "Request IDs", line: "Middleware reads, generates, and forwards them." },
          { title: "Bounded HTTP", line: "Shared client with connect/read/write/pool timeouts." },
          { title: "Metrics", line: "One installer for request, latency, and in-flight series." },
          { title: "Audit + CORS", line: "Redacting JSONL emitter and a deny-by-default CORS helper." },
          { title: "Service auth", line: "Machine-key → digikey JWT exchange with retries." },
        ],
        snippet: {
          lang: "python",
          code: "pip install -e \"./digibase\"\nfrom digibase.http import install_request_id_middleware\ninstall_request_id_middleware(app)",
        },
        proof: [
          { term: "port", value: "none — it is a library" },
          { term: "import", value: "from digibase.http import …" },
          { term: "consumers", value: "all 7 Python services" },
        ],
      };
    case "digistore":
      return {
        planned: true,
        stages: [
          { label: "declare", detail: "Name the data and its backend, once." },
          { label: "route", detail: "Blobs to S3, rows to Postgres, sessions to SQLite." },
          { label: "persist", detail: "Versioned writes with a draft-to-final lifecycle." },
          { label: "index", detail: "digisearch indexes only finalized documents." },
          { label: "serve", detail: "Same get/put/list anywhere in the stack." },
        ],
        capabilities: [
          { title: "Backend registry", line: "SQLite locally, Postgres/S3 in production — config, not code." },
          { title: "Content routing", line: "Research, exports, and artifacts each land where they belong." },
          { title: "Draft → final", line: "Selective indexing fires on the draft-to-final transition." },
          { title: "OpenBB underneath", line: "Retrieval from ~100 sources; digistore persists what it fetches." },
          { title: "Profiles + keys", line: "User profiles and per-user BYOK keys, encrypted." },
          { title: "Vault backing", line: "A digivault vault on Supabase/S3, not just local disk." },
        ],
        proof: [
          { term: "status", value: "roadmap — vision + scaffold plan" },
          { term: "today", value: "session cache inside digigraph only" },
          { term: "runnable", value: "not yet" },
        ],
      };
    default: // digilink
      return {
        planned: true,
        stages: [
          { label: "define once", detail: "Capability + schema registered in one place." },
          { label: "generate", detail: "REST, MCP tool, CLI, Docker from the registry." },
          { label: "call anywhere", detail: "curl, Claude Desktop, terminal, container." },
        ],
        capabilities: [
          { title: "Central registry", line: "Name, schema, handler — one source of truth." },
          { title: "MCP generation", line: "Any capability becomes a desktop-AI tool." },
          { title: "CLI generation", line: "Endpoints become digithings <capability> commands." },
          { title: "Desktop connectors", line: "Tested configs for Claude Desktop, Cursor, Windsurf." },
          { title: "Webhooks", line: "Async triggers for runs and third-party events." },
          { title: "Docker entrypoints", line: "Each capability callable as a container." },
        ],
        proof: [
          { term: "status", value: "roadmap — vision + scaffold plan" },
          { term: "today", value: "MCP built into each module" },
          { term: "trading", value: "never — protocol translation only" },
        ],
      };
  }
}
