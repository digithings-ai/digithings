/**
 * Financial digichat session for the digiquant desk.
 *
 * Tenant config is a Cloudflare KV record (key `digiquant`). The cheap
 * inference key is a worker secret (`DIGICHAT_CHEAP_INFERENCE_KEY`). Neither
 * value is read from the repo. Chat stays fail-closed until both are present.
 * The key is sent only as an Authorization header to the tenant origin and
 * is never copied into a response or a JSON body.
 */

export const TENANT_KV_KEY = "digiquant";
export const CHEAP_INFERENCE_KEY_ENV = "DIGICHAT_CHEAP_INFERENCE_KEY";

/** LuxAlgo tools registered and audited on the digiquant MCP server. */
export const LUXALGO_TOOLS = [
  "luxalgo_edge_presets",
  "luxalgo_edge_report",
  "luxalgo_edge_symbols",
  "luxalgo_library_get_concept",
  "luxalgo_library_get_indicator",
  "luxalgo_library_list_concepts",
  "luxalgo_library_list_families",
  "luxalgo_library_list_indicators",
  "luxalgo_library_list_tags",
  "luxalgo_library_search",
  "luxalgo_trackers_datasets",
  "luxalgo_trackers_latest",
  "luxalgo_trackers_ticker",
] as const;

/** Dashboard reads the session may call. Research is the theses route. */
export const APP_DATA_PATHS = {
  baseline: ["/portfolio", "/pipeline/runs/latest", "/theses"],
  fx: ["/fx/summary", "/fx/pairs", "/fx/ideas"],
} as const;

export type FinancialDesk = "baseline" | "fx";

export interface TenantKv {
  get(key: string): Promise<string | null>;
}

export interface FinancialSessionEnv {
  DIGICHAT_TENANT?: TenantKv;
  DIGICHAT_CHEAP_INFERENCE_KEY?: string;
}

export interface TenantConfig {
  slug: string;
  cheapModel: string;
  digichatOrigin: string;
  gloomberbTools: string[];
}

export interface FinancialTools {
  gloomberb: string[];
  luxalgo: string[];
  app: string[];
}

export interface FinancialSession {
  id: string;
  desk: FinancialDesk;
  context: string;
  cheapModel: string;
  tools: FinancialTools;
}

const SECRET_FIELDS = new Set([
  "key",
  "apikey",
  "api_key",
  "token",
  "secret",
  "inferencekey",
  "inference_key",
  "authorization",
]);

const TOOL_NAME = /^[a-z][a-z0-9_]{0,80}$/;
const MODEL_NAME = /^[a-z0-9][a-z0-9._/-]{0,80}$/i;

export function financialDeskFrom(value: string | null | undefined): FinancialDesk {
  return value === "fx" ? "fx" : "baseline";
}

export function financialContext(desk: FinancialDesk): string {
  return desk === "fx" ? "FX Hub" : "baseline desk run";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function toolNames(value: unknown): string[] | null {
  if (value === undefined) return [];
  if (!Array.isArray(value)) return null;
  const names: string[] = [];
  for (const item of value) {
    if (typeof item !== "string" || !TOOL_NAME.test(item)) return null;
    names.push(item);
  }
  return names;
}

function originOk(raw: string): string | null {
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return null;
  }
  if (url.username || url.password || url.search || url.hash) return null;
  const loopback = url.hostname === "127.0.0.1" || url.hostname === "localhost";
  const https = url.protocol === "https:";
  const localHttp = url.protocol === "http:" && loopback;
  if (!https && !localHttp) return null;
  return url.origin;
}

/** Parse a KV tenant record. A secret field, or a bad origin, is refuse-closed. */
export function parseTenantConfig(raw: string | null | undefined): TenantConfig | null {
  if (!raw) return null;
  let value: unknown;
  try {
    value = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(value)) return null;
  for (const field of Object.keys(value)) {
    if (SECRET_FIELDS.has(field.toLowerCase())) return null;
  }
  const slug = value.slug;
  const cheapModel = value.cheapModel;
  const digichatOrigin = value.digichatOrigin;
  if (typeof slug !== "string" || slug.length === 0 || slug.length > 64) return null;
  if (typeof cheapModel !== "string" || !MODEL_NAME.test(cheapModel)) return null;
  if (typeof digichatOrigin !== "string") return null;
  const origin = originOk(digichatOrigin);
  if (!origin) return null;
  const gloomberbTools = toolNames(value.gloomberbTools);
  if (!gloomberbTools) return null;
  return { slug, cheapModel, digichatOrigin: origin, gloomberbTools };
}

export function buildFinancialSession(config: TenantConfig, desk: FinancialDesk): FinancialSession {
  return {
    id: `fin-${desk}`,
    desk,
    context: financialContext(desk),
    cheapModel: config.cheapModel,
    tools: {
      gloomberb: [...config.gloomberbTools],
      luxalgo: [...LUXALGO_TOOLS],
      app: [...APP_DATA_PATHS[desk]],
    },
  };
}

export async function loadFinancialSession(
  env: FinancialSessionEnv,
  desk: FinancialDesk,
): Promise<{ config: TenantConfig; session: FinancialSession; inferenceKey: string } | null> {
  const inferenceKey = env.DIGICHAT_CHEAP_INFERENCE_KEY?.trim() ?? "";
  if (!inferenceKey) return null;
  const raw = await env.DIGICHAT_TENANT?.get(TENANT_KV_KEY);
  const config = parseTenantConfig(raw);
  if (!config) return null;
  return { config, session: buildFinancialSession(config, desk), inferenceKey };
}

export interface ForwardedTurn {
  reply: string;
}

/** POST the turn to the tenant digichat origin. The key stays on the header. */
export async function forwardFinancialTurn(
  config: TenantConfig,
  inferenceKey: string,
  session: FinancialSession,
  text: string,
  fetchFn: typeof fetch = fetch,
): Promise<ForwardedTurn | { error: string }> {
  const url = new URL("/api/chat", config.digichatOrigin);
  let res: Response;
  try {
    res = await fetchFn(url, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: `Bearer ${inferenceKey}`,
      },
      body: JSON.stringify({
        model: session.cheapModel,
        desk: session.desk,
        context: session.context,
        tools: session.tools,
        messages: [{ role: "user", content: text }],
      }),
    });
  } catch {
    return { error: "digichat could not be reached" };
  }
  if (!res.ok) return { error: "digichat returned no reply" };
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    return { error: "digichat returned no reply" };
  }
  const reply = readReply(body);
  if (!reply) return { error: "digichat returned no reply" };
  return { reply };
}

function readReply(body: unknown): string | null {
  if (!isRecord(body)) return null;
  if (typeof body.reply === "string" && body.reply.trim()) return body.reply.trim();
  const data = isRecord(body.data) ? body.data : null;
  if (data && typeof data.reply === "string" && data.reply.trim()) return data.reply.trim();
  return null;
}
