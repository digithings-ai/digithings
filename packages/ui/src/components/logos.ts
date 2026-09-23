/**
 * Static registry of the vendor logos referenced by the module/subsystem
 * manifests. Named imports (not `import * as`) keep this tree-shakeable so only
 * these ~18 icons ship — not the whole simple-icons set. Any slug NOT in this
 * map falls back to a monogram chip in StackLogo (e.g. coingecko, and the
 * no-mark names like NautilusTrader, LiteLLM, LangSmith, Cheaper Inference,
 * Assistant UI — those publish no single-path monochrome SVG, which is what
 * StackLogo needs).
 */
import {
  siAnthropic, siDatadog, siDocker, siDrizzle, siElastic, siFastapi, siGrafana,
  siGooglegemini, siGooglecloud, siLangchain, siLanggraph, siModelcontextprotocol,
  siMongodb, siNextdotjs, siOpenai, siOpentelemetry, siOptuna, siPolars,
  siPostgresql, siPrometheus, siPydantic, siReact, siRedis, siSnowflake, siSqlite,
  siStripe, siSupabase, siVercel,
} from "simple-icons";

export interface SimpleIcon { hex: string; path: string }

export const ICONS: Record<string, SimpleIcon> = {
  anthropic: siAnthropic,
  datadog: siDatadog,
  docker: siDocker,
  drizzle: siDrizzle,
  elastic: siElastic,
  fastapi: siFastapi,
  grafana: siGrafana,
  googlegemini: siGooglegemini,
  googlecloud: siGooglecloud,
  langchain: siLangchain,
  langgraph: siLanggraph,
  modelcontextprotocol: siModelcontextprotocol,
  mongodb: siMongodb,
  nextdotjs: siNextdotjs,
  openai: siOpenai,
  opentelemetry: siOpentelemetry,
  optuna: siOptuna,
  polars: siPolars,
  postgresql: siPostgresql,
  prometheus: siPrometheus,
  pydantic: siPydantic,
  react: siReact,
  redis: siRedis,
  snowflake: siSnowflake,
  sqlite: siSqlite,
  stripe: siStripe,
  supabase: siSupabase,
  vercel: siVercel,
};
