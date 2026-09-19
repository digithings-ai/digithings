/**
 * Single source of truth for digithings modules — drives the landing cards,
 * the architecture/scrollytelling graph, the per-module detail pages, and the
 * stack rows. Content is codebase-accurate (real packages, docker
 * commands, init snippets). digistore/digilink are tier "roadmap".
 */

export type Tier = "core" | "support" | "roadmap";

export interface StackItem {
  name: string;
  /** Simple Icons slug, or null to render a monogram chip. */
  icon: string | null;
  /** 2–4 char monogram used when icon is null. */
  mono?: string;
}

export interface ModuleNode {
  id: string;
  name: string;
  tier: Tier;
  graphOrder: number;
  graph: { x: number; y: number; r: number; hub?: boolean };
  emblem: string;
  role: string;
  tagline: string;
  summary: string[];
  stack: StackItem[];
  dockerCmd: string | null;
  initSnippet: { lang: string; code: string };
  api: { label?: string; code: string }[];
  links: { label: string; href: string }[];
  related: string[];
}

export const edges: { a: string; b: string }[] = [
  { a: "digigraph", b: "digiquant" },
  { a: "digigraph", b: "digisearch" },
  { a: "digigraph", b: "digichat" },
  { a: "digigraph", b: "digikey" },
  { a: "digigraph", b: "digismith" },
  { a: "digigraph", b: "digiclaw" },
  { a: "digigraph", b: "digivault" },
  { a: "digiquant", b: "digistore" },
  { a: "digisearch", b: "digistore" },
  { a: "digiquant", b: "digilink" },
  { a: "digisearch", b: "digibase" },
  { a: "digichat", b: "digikey" },
  { a: "digichat", b: "digisearch" },
  { a: "digiclaw", b: "digiquant" },
  { a: "digismith", b: "digichat" },
];

export const modules: ModuleNode[] = [
  {
    id: "digigraph",
    name: "digigraph",
    tier: "core",
    graphOrder: 0,
    graph: { x: 460, y: 280, r: 34, hub: true },
    emblem: "digigraph",
    role: "Orchestration · LangGraph state machine",
    tagline: "A declarative graph decides what runs next — profile in, path out.",
    summary: [
      "A LangGraph state machine routes each request to the right sub-graph — quant research, retrieval, or chat — through conditional edges keyed on the request profile and the run's state. DIGI_SUPERVISOR=1 adds an entry node that stamps the run and enforces a recursion budget; it does not pick the branch, and unset, requests enter the research graph directly.",
      "Speaks the OpenAI API so existing clients work unchanged; LiteLLM handles routing, caching, and checkpointed state across hops.",
    ],
    stack: [
      { name: "LangGraph", icon: "langchain" },
      { name: "FastAPI", icon: "fastapi" },
      { name: "LiteLLM", icon: null, mono: "LL" },
      { name: "Pydantic", icon: "pydantic" },
      { name: "Polars", icon: "polars" },
      { name: "OpenAI SDK", icon: "openai" },
    ],
    dockerCmd: "docker compose up -d digigraph",
    initSnippet: {
      lang: "python",
      code: "from digigraph.server import app\n# uvicorn digigraph.server:app",
    },
    api: [
      { label: "Run a workflow", code: "POST /workflow" },
      { label: "Chat completions", code: "POST /v1/chat/completions" },
    ],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digiquant", "digisearch", "digichat"],
  },
  {
    id: "digiquant",
    name: "digiquant",
    tier: "core",
    graphOrder: 1,
    graph: { x: 300, y: 175, r: 26 },
    emblem: "digiquant",
    role: "Quant engine · NautilusTrader",
    tagline: "Strategy research that ends in a reproducible backtest, not a markdown file.",
    summary: [
      "Scheduled research turns into a sized book; backtests run on a real NautilusTrader engine with Optuna driving the parameter search.",
      "Every run writes an append-only audit trail and a tearsheet. No broker adapter ships wired — the IB, Alpaca, and QuantConnect adapters are declared stubs, so reaching a live venue is your own deliberate integration.",
    ],
    stack: [
      { name: "NautilusTrader", icon: null, mono: "NT" },
      { name: "Optuna", icon: "optuna" },
      { name: "LangGraph", icon: "langchain" },
      { name: "Polars", icon: "polars" },
      { name: "yfinance", icon: null, mono: "yf" },
      { name: "Supabase", icon: "supabase" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: {
      lang: "python",
      code: "from digiquant.strategies.registry import register\nregister(name, StrategyCls, ConfigCls, default_params)",
    },
    api: [
      { label: "Register a strategy", code: "register(name, StrategyCls, ConfigCls, default_params)" },
    ],
    links: [
      { label: "digiquant.io", href: "https://digiquant.io" },
      { label: "Source", href: "https://github.com/digithings-ai" },
    ],
    related: ["digigraph", "digistore", "digilink"],
  },
  {
    id: "digisearch",
    name: "digisearch",
    tier: "core",
    graphOrder: 2,
    graph: { x: 620, y: 175, r: 26 },
    emblem: "digisearch",
    role: "Vector retrieval · multi-backend",
    tagline: "Production RAG without a stack rewrite when you switch vector DB.",
    summary: [
      "One client over Chroma or Azure AI Search, with backend-neutral entities so you swap engines without touching business code.",
      "Dense, sparse, and hybrid retrieval are first-class; BeautifulSoup and pdfplumber handle ingest, Polars throughout.",
    ],
    stack: [
      { name: "Chroma", icon: null, mono: "Ch" },
      { name: "Azure AI Search", icon: null, mono: "AZ" },
      { name: "OpenAI", icon: "openai" },
      { name: "BeautifulSoup", icon: null, mono: "BS4" },
      { name: "pdfplumber", icon: null, mono: "PDF" },
      { name: "LangGraph", icon: "langchain" },
      { name: "FastAPI", icon: "fastapi" },
    ],
    dockerCmd: "docker compose up -d digisearch",
    initSnippet: {
      lang: "python",
      code: "from digisearch.server import app\nDigiSearch().query(text, index)",
    },
    api: [{ label: "Query an index", code: "DigiSearch().query(text, index)" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digigraph", "digistore", "digibase"],
  },
  {
    id: "digichat",
    name: "digichat",
    tier: "core",
    graphOrder: 3,
    graph: { x: 460, y: 440, r: 26 },
    emblem: "digichat",
    role: "Chat surface · Next.js BFF · BYOK",
    tagline: "Talk to your stack with your keys, your models, your audit log.",
    summary: [
      "A Next.js and React BFF streaming digigraph through the Vercel AI SDK, your key forwarded per request — never stored, never logged.",
      "NextAuth handles identity; Postgres and Drizzle persist sessions for humans and agents alike.",
    ],
    stack: [
      { name: "Next.js", icon: "nextdotjs" },
      { name: "React", icon: "react" },
      { name: "Vercel AI SDK", icon: "vercel" },
      { name: "NextAuth", icon: null, mono: "Auth" },
      { name: "Postgres", icon: "postgresql" },
      { name: "Drizzle", icon: "drizzle" },
    ],
    dockerCmd: "docker compose --profile digichat up -d",
    initSnippet: {
      lang: "bash",
      code: "make up-digichat   # start the chat stack\n# then open the local URL it prints",
    },
    api: [{ label: "Stream a turn", code: "streamText({ model, messages })" }],
    links: [
      { label: "Open digichat", href: "/chat" },
      { label: "Source", href: "https://github.com/digithings-ai" },
    ],
    related: ["digigraph", "digikey", "digisearch"],
  },
  {
    id: "digikey",
    name: "digikey",
    tier: "support",
    graphOrder: 4,
    graph: { x: 150, y: 120, r: 20 },
    emblem: "digikey",
    role: "Auth · RS256 JWTs · scoped API keys",
    tagline: "Identity, JWTs, and scoped keys — one issuer for humans and machines.",
    summary: [
      "RS256-signed JWTs with a published JWKS, organization and project membership, and row-level scopes baked into the token.",
      "SQLAlchemy over Postgres stores keys, bcrypt hashes them, and an optional Redis blocklist handles revocation.",
    ],
    stack: [
      { name: "PyJWT", icon: null, mono: "JWT" },
      { name: "cryptography", icon: null, mono: "crypto" },
      { name: "bcrypt", icon: null, mono: "bcrypt" },
      { name: "SQLAlchemy", icon: null, mono: "SQLA" },
      { name: "Postgres", icon: "postgresql" },
      { name: "Redis", icon: "redis" },
    ],
    dockerCmd: "docker compose up -d digikey",
    initSnippet: {
      lang: "python",
      code: "from digikey.server import app\n# DIGIKEY_ISSUER=https://auth.example.com",
    },
    api: [{ label: "Issuer config", code: "DIGIKEY_ISSUER=https://…" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digichat", "digigraph", "digismith"],
  },
  {
    id: "digismith",
    name: "digismith",
    tier: "support",
    graphOrder: 5,
    graph: { x: 95, y: 300, r: 20 },
    emblem: "digismith",
    role: "Observability · spans · correlation IDs",
    tagline: "Correlation IDs across every hop — and prompts logged by length, never by text.",
    summary: [
      "Structured logging, Prometheus metrics, and OpenTelemetry spans thread through every request so a multi-hop run is traceable end to end.",
      "Audit events record a prompt's length and its IDs, never the prompt itself — tail events.jsonl and check. Optional LangSmith export runs a regex PII redactor on the way out.",
    ],
    stack: [
      { name: "LangSmith", icon: null, mono: "LS" },
      { name: "OpenTelemetry", icon: "opentelemetry" },
      { name: "Prometheus", icon: "prometheus" },
      { name: "FastAPI", icon: "fastapi" },
    ],
    dockerCmd: "docker compose up -d digismith",
    initSnippet: {
      lang: "python",
      code: "from digibase.http import install_request_id_middleware\ninstall_request_id_middleware(app)",
    },
    api: [{ label: "Middleware", code: "install_request_id_middleware(app)" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digigraph", "digiclaw", "digibase"],
  },
  {
    id: "digiclaw",
    name: "digiclaw",
    tier: "support",
    graphOrder: 6,
    graph: { x: 250, y: 475, r: 20 },
    emblem: "digiclaw",
    role: "Always-on runtime · heartbeat · audit",
    tagline: "The always-on agent runtime — heartbeats, scheduling, append-only audit.",
    summary: [
      "A heartbeat service that keeps agents running: research-runner scheduling and drift detection, calling digigraph over HTTP on an interval.",
      "Every action lands in an append-only audit log, and it runs no LLM of its own.",
    ],
    stack: [
      { name: "HTTPx", icon: null, mono: "hx" },
      { name: "digibase", icon: null, mono: "DB" },
    ],
    dockerCmd: "docker compose --profile heartbeat up -d heartbeat",
    initSnippet: { lang: "bash", code: "python -m digiclaw   # runs on an interval" },
    api: [{ label: "Run the daemon", code: "python -m digiclaw" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digiquant", "digismith"],
  },
  {
    id: "digibase",
    name: "digibase",
    tier: "support",
    graphOrder: 7,
    graph: { x: 670, y: 475, r: 20 },
    emblem: "digibase",
    role: "Shared HTTP + audit library",
    tagline: "The shared Python library every service builds on — and nothing more.",
    summary: [
      "Not a service but a deliberately minimal library: request-ID middleware and logging, CORS and error handlers, an audit redaction helper, and a Prometheus metrics endpoint.",
      "Imported by every other module so they all behave consistently, with optional OpenTelemetry setup. Auth middleware is digikey's job, not digibase's.",
    ],
    stack: [
      { name: "Pydantic", icon: "pydantic" },
      { name: "FastAPI", icon: "fastapi" },
      { name: "Prometheus", icon: "prometheus" },
      { name: "OpenTelemetry", icon: "opentelemetry" },
    ],
    dockerCmd: null,
    initSnippet: {
      lang: "python",
      code: "from digibase.audit import redact_mapping\nfrom digibase.http import install_request_id_middleware",
    },
    api: [{ label: "Import", code: "from digibase.audit import redact_mapping" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digismith", "digisearch"],
  },
  {
    id: "digivault",
    name: "digivault",
    tier: "support",
    graphOrder: 8,
    graph: { x: 460, y: 80, r: 20 },
    emblem: "digivault",
    role: "Markdown vault · wikilinks · backlinks",
    tagline: "A folder of markdown notes, served over HTTP — frontmatter, wikilinks and backlinks.",
    summary: [
      "An Obsidian-style vault service: it manages a folder of markdown notes with YAML frontmatter, wikilinks, tags and a folder taxonomy, and answers over HTTP rather than asking callers to walk the filesystem.",
      "Routes cover listing, reading and creating notes, renaming with backlink repair, backlink and tag lookups, and a lint report. Two more — orchestrator_tools and orchestrator_invoke — expose the vault to digigraph as callable tools. Runs behind the `digivault` compose profile, so it is opt-in rather than up by default.",
    ],
    stack: [
      { name: "FastAPI", icon: "fastapi" },
      { name: "Pydantic", icon: "pydantic" },
      { name: "PyYAML", icon: null, mono: "YM" },
    ],
    dockerCmd: "docker compose --profile digivault up -d digivault",
    initSnippet: {
      lang: "bash",
      code: "curl -s localhost:8004/v1/notes | jq '.notes[].name'",
    },
    api: [
      { label: "List notes", code: "GET /v1/notes" },
      { label: "Backlinks", code: "GET /v1/notes/{name}/backlinks" },
      { label: "Lint the vault", code: "GET /v1/lint" },
    ],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digigraph", "digisearch", "digibase"],
  },
  {
    id: "digistore",
    name: "digistore",
    tier: "roadmap",
    graphOrder: 9,
    graph: { x: 770, y: 120, r: 20 },
    emblem: "digistore",
    role: "Storage abstraction · roadmap",
    tagline: "One storage API over S3, MinIO, Postgres, or SQLite.",
    summary: [
      "Roadmap: a storage abstraction so business code never binds to a backend, today a session-scoped dataset manager living inside digigraph.",
      "Run SQLite on a laptop, then swap to S3 and Postgres in production without rewriting.",
    ],
    stack: [
      { name: "Postgres", icon: "postgresql" },
      { name: "SQLite", icon: "sqlite" },
      { name: "S3", icon: null, mono: "S3" },
      { name: "MinIO", icon: null, mono: "Mi" },
    ],
    dockerCmd: null,
    initSnippet: { lang: "python", code: 'digistore.configure(backend="s3")  # planned' },
    api: [{ label: "Configure backend", code: 'digistore.configure(backend="s3")' }],
    links: [{ label: "Roadmap", href: "https://github.com/digithings-ai" }],
    related: ["digiquant", "digisearch"],
  },
  {
    id: "digilink",
    name: "digilink",
    tier: "roadmap",
    graphOrder: 10,
    graph: { x: 825, y: 300, r: 20 },
    emblem: "digilink",
    role: "MCP protocol bridge · roadmap",
    tagline: "A protocol bridge so non-native transports speak MCP.",
    summary: [
      "Roadmap: a translation layer registering adapters that turn REST, gRPC, or bespoke transports into MCP tools.",
      "Today MCP is built into individual modules; this keeps the stack open instead of locked to one protocol.",
    ],
    stack: [
      { name: "MCP", icon: null, mono: "MCP" },
      { name: "HTTPx", icon: null, mono: "hx" },
    ],
    dockerCmd: null,
    initSnippet: { lang: "python", code: 'digilink.register_adapter("rest", …)  # planned' },
    api: [{ label: "Register an adapter", code: 'digilink.register_adapter("rest", …)' }],
    links: [{ label: "Roadmap", href: "https://github.com/digithings-ai" }],
    related: ["digigraph", "digiquant"],
  },
];

export const moduleById = (id: string) => modules.find((m) => m.id === id);
