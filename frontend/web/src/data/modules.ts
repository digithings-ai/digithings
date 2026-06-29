/**
 * Single source of truth for DigiThings modules — drives the landing cards,
 * the architecture/scrollytelling graph, the per-module detail pages, and the
 * stack rows. Content is codebase-accurate (real packages, ports, docker
 * commands, init snippets). DigiStore/DigiLink are tier "roadmap".
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
  port: string | null;
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
    port: "8000",
    graphOrder: 0,
    graph: { x: 460, y: 280, r: 34, hub: true },
    emblem: "digigraph",
    role: "Orchestration · LangGraph supervisor",
    tagline: "One supervisor decides which specialist runs. Every time.",
    summary: [
      "A LangGraph supervisor inspects each request and routes it to the right sub-graph — quant, retrieval, or chat — through a declarative tool registry.",
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
      code: "from digigraph.server import app\n# uvicorn digigraph.server:app --port 8000",
    },
    api: [
      { label: "Run a workflow", code: "POST /v1/workflow" },
      { label: "Register a tool", code: "POST /v1/orchestrator_tools" },
    ],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digiquant", "digisearch", "digichat"],
  },
  {
    id: "digiquant",
    name: "digiquant",
    tier: "core",
    port: "8001",
    graphOrder: 1,
    graph: { x: 300, y: 175, r: 26 },
    emblem: "digiquant",
    role: "Quant engine · NautilusTrader",
    tagline: "Strategy research that ends in an order, not a markdown file.",
    summary: [
      "Atlas runs scheduled research, Hermes turns it into signals, Kairos executes on a NautilusTrader core, with Optuna driving optimization.",
      "Every step writes an immutable audit trail; live trading stays loopback-only until a human flips the gate.",
    ],
    stack: [
      { name: "NautilusTrader", icon: null, mono: "NT" },
      { name: "Optuna", icon: null, mono: "Op" },
      { name: "LangGraph", icon: "langchain" },
      { name: "Polars", icon: "polars" },
      { name: "yfinance", icon: null, mono: "yf" },
      { name: "Supabase", icon: "supabase" },
    ],
    dockerCmd: "docker compose up -d digiquant",
    initSnippet: {
      lang: "python",
      code: 'from digiquant.server import app\n# register a strategy\nregister("strategy", cls, cfg)',
    },
    api: [{ label: "Register a strategy", code: 'register("strategy", cls, cfg)' }],
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
    port: "8002",
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
    port: "3005",
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
      code: "make up-digichat   # DigiGraph + DigiChat on :3005\n# visit http://localhost:3005",
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
    port: "8005",
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
    port: "8003",
    graphOrder: 5,
    graph: { x: 95, y: 300, r: 20 },
    emblem: "digismith",
    role: "Observability · spans · PII redaction",
    tagline: "Correlation IDs across every span; PII redacted before logs hit disk.",
    summary: [
      "Structured logging, Prometheus metrics, and OpenTelemetry spans thread through every request so a multi-hop run is traceable end to end.",
      "PII is redacted before anything is written, with optional LangSmith trace export.",
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
      code: "from digismith.server import app\napp.add_middleware(DigiSmithRequestIdMiddleware)",
    },
    api: [{ label: "Middleware", code: "DigiSmithRequestIdMiddleware" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digigraph", "digiclaw", "digibase"],
  },
  {
    id: "digiclaw",
    name: "digiclaw",
    tier: "support",
    port: null,
    graphOrder: 6,
    graph: { x: 250, y: 475, r: 20 },
    emblem: "digiclaw",
    role: "Always-on runtime · heartbeat · audit",
    tagline: "The always-on agent runtime — heartbeats, scheduling, immutable audit.",
    summary: [
      "A heartbeat service that keeps agents running: Atlas runner scheduling and drift detection, calling digigraph over HTTP on an interval.",
      "Every action lands in an immutable audit log, and it runs no LLM of its own.",
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
    port: null,
    graphOrder: 7,
    graph: { x: 670, y: 475, r: 20 },
    emblem: "digibase",
    role: "Shared HTTP + audit library",
    tagline: "The shared Python library every service builds on — and nothing more.",
    summary: [
      "Not a service but a deliberately minimal library: auth middleware, error handlers, request-ID logging, and a Prometheus metrics endpoint.",
      "Imported by every other module so they all behave consistently, with optional OpenTelemetry setup.",
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
      code: "from digibase.audit import redact_mapping\nfrom digibase.middleware import DigiAuthMiddleware",
    },
    api: [{ label: "Import", code: "from digibase.audit import redact_mapping" }],
    links: [{ label: "Source", href: "https://github.com/digithings-ai" }],
    related: ["digismith", "digisearch"],
  },
  {
    id: "digistore",
    name: "digistore",
    tier: "roadmap",
    port: null,
    graphOrder: 8,
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
    initSnippet: { lang: "python", code: 'DigiStore.configure(backend="s3")  # planned' },
    api: [{ label: "Configure backend", code: 'DigiStore.configure(backend="s3")' }],
    links: [{ label: "Roadmap", href: "https://github.com/digithings-ai" }],
    related: ["digiquant", "digisearch"],
  },
  {
    id: "digilink",
    name: "digilink",
    tier: "roadmap",
    port: null,
    graphOrder: 9,
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
