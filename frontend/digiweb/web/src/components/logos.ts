/**
 * Static registry of the vendor logos referenced by the module/subsystem
 * manifests. Named imports (not `import * as`) keep this tree-shakeable so only
 * these ~15 icons ship — not the whole simple-icons set. Any slug NOT in this
 * map falls back to a monogram chip in StackLogo (e.g. coingecko, and the
 * internal/no-mark names like NautilusTrader, LiteLLM, LangGraph, LangSmith).
 */
import {
  siDrizzle, siFastapi, siLangchain, siNextdotjs, siOpenai, siOpentelemetry,
  siPolars, siPostgresql, siPrometheus, siPydantic, siReact, siRedis,
  siSqlite, siSupabase, siVercel,
} from "simple-icons";

export interface SimpleIcon { hex: string; path: string }

export const ICONS: Record<string, SimpleIcon> = {
  drizzle: siDrizzle,
  fastapi: siFastapi,
  langchain: siLangchain,
  nextdotjs: siNextdotjs,
  openai: siOpenai,
  opentelemetry: siOpentelemetry,
  polars: siPolars,
  postgresql: siPostgresql,
  prometheus: siPrometheus,
  pydantic: siPydantic,
  react: siReact,
  redis: siRedis,
  sqlite: siSqlite,
  supabase: siSupabase,
  vercel: siVercel,
};
