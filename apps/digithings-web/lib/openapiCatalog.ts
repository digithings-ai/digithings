/**
 * Public OpenAPI explorer catalog — one entry per committed spec under
 * docs/openapi/*.json (synced into public/openapi/ at digithings-web prebuild).
 * digiclaw has no HTTP OpenAPI and is intentionally omitted.
 */

export interface OpenApiService {
  id: string;
  port?: number;
  role: string;
  /** True when the committed JSON is authored rather than FastAPI-exported. */
  authored?: boolean;
}

export const OPENAPI_SERVICES: OpenApiService[] = [
  { id: "digigraph", port: 8000, role: "LangGraph orchestration · OpenAI-compatible API" },
  { id: "digikey", port: 8005, role: "JWT + scoped API keys · JWKS" },
  { id: "digisearch", port: 8002, role: "RAG ingest · query · research" },
  { id: "digivault", port: 8004, role: "Markdown vault · wikilinks · lint" },
  { id: "digiquant", port: 8001, role: "NautilusTrader backtest · optimize" },
  { id: "digismith", port: 8003, role: "Observability · health · status" },
  {
    id: "digichat",
    port: 3005,
    role: "Next.js BFF · chat · Auth.js",
    authored: true,
  },
];

export const OPENAPI_SERVICE_IDS = OPENAPI_SERVICES.map((s) => s.id);

export function openApiSpecPath(id: string): string {
  return `/openapi/${id}.json`;
}
