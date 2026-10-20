/**
 * Financial digichat session for the digiquant desk.
 *
 * A turn goes to the digichat BFF (`POST {origin}/api/chat`, the route in
 * apps/digichat/src/app/api/chat/route.ts) as one UIMessage, authenticated with
 * a digichat machine key (`digi_live_…`) for the digiquant tenant. That key is
 * the session's only credential: the tenant pins the cheap model and owns the
 * MCP servers (Gloomberb, LuxAlgo, dashboard), so no provider key is held here.
 * The reply is read from the AI SDK UI-message stream the route answers with.
 *
 * Tenant config is a Cloudflare KV record (key `digiquant`). The machine key is
 * a worker secret (`DIGICHAT_MACHINE_KEY`). Neither value is read from the repo.
 * Chat stays fail-closed until both are present. The key is sent only as an
 * Authorization header to the tenant origin and is never copied into a
 * response or a JSON body.
 */

export const TENANT_KV_KEY = "digiquant";
export const MACHINE_KEY_ENV = "DIGICHAT_MACHINE_KEY";
/** Digichat machine-key prefix the BFF accepts on Authorization (request-auth.ts). */
export const MACHINE_KEY_PREFIX = "digi_live_";
/** Upper bound on one forwarded turn, so a stalled stream cannot hold the worker. */
export const TURN_TIMEOUT_MS = 60_000;

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
  DIGICHAT_MACHINE_KEY?: string;
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

const GLOOMBERB_TOOL = /^gloomberb_[a-z0-9_]{1,80}$/;
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
    if (typeof item !== "string" || !GLOOMBERB_TOOL.test(item)) return null;
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
  // The bearer key goes only to a digithings host, or to loopback in local dev.
  const house = url.hostname === "digithings.ai" || url.hostname.endsWith(".digithings.ai");
  if (url.protocol === "https:" && (house || loopback)) return url.origin;
  if (url.protocol === "http:" && loopback) return url.origin;
  return null;
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
): Promise<{ config: TenantConfig; session: FinancialSession; machineKey: string } | null> {
  const machineKey = env.DIGICHAT_MACHINE_KEY?.trim() ?? "";
  if (!machineKey.startsWith(MACHINE_KEY_PREFIX) || machineKey.length <= MACHINE_KEY_PREFIX.length) return null;
  const raw = await env.DIGICHAT_TENANT?.get(TENANT_KV_KEY);
  const config = parseTenantConfig(raw);
  if (!config) return null;
  return { config, session: buildFinancialSession(config, desk), machineKey };
}

export interface ForwardedTurn {
  reply: string;
}

/**
 * The desk context, read paths and tool families, as a lead-in to the user's text.
 * The BFF takes no system field from the client, and its MCP servers come from the
 * tenant config, so this names what to use; it grants nothing by itself.
 */
export function turnPreamble(session: FinancialSession): string {
  const families = ["LuxAlgo", ...(session.tools.gloomberb.length > 0 ? ["Gloomberb"] : [])];
  return [
    `digiquant ${session.context}.`,
    `Dashboard reads: ${session.tools.app.join(", ")}.`,
    `Tools: ${families.join(" and ")} via MCP.`,
  ].join(" ");
}

/** The JSON body `POST /api/chat` accepts: `messages` as UIMessage entries with text parts. */
export function turnBody(session: FinancialSession, text: string): string {
  return JSON.stringify({
    messages: [
      {
        id: crypto.randomUUID(),
        role: "user",
        parts: [{ type: "text", text: `${turnPreamble(session)}\n\n${text}` }],
      },
    ],
  });
}

/** POST the turn to the tenant digichat BFF. The key stays on the header. */
export async function forwardFinancialTurn(
  config: TenantConfig,
  machineKey: string,
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
        accept: "text/event-stream",
        authorization: `Bearer ${machineKey}`,
        "x-digi-caller": "digiquant-desk",
        "x-digi-model": session.cheapModel,
      },
      body: turnBody(session, text),
      signal: AbortSignal.timeout(TURN_TIMEOUT_MS),
    });
  } catch {
    return { error: "digichat could not be reached" };
  }
  if (!res.ok) return { error: "digichat returned no reply" };
  let raw: string;
  try {
    raw = await res.text();
  } catch {
    return { error: "digichat could not be reached" };
  }
  const reply = readStreamReply(raw);
  if (!reply) return { error: "digichat returned no reply" };
  return { reply };
}

/**
 * Assistant text from an AI SDK UI-message stream (SSE `data:` lines carrying
 * `text-delta` chunks, ending in `[DONE]`). An `error` chunk means no reply.
 */
export function readStreamReply(raw: string): string | null {
  let text = "";
  for (const line of raw.split(/\r?\n/)) {
    if (!line.startsWith("data:")) continue;
    const data = line.slice(5).trim();
    if (!data || data === "[DONE]") continue;
    let chunk: unknown;
    try {
      chunk = JSON.parse(data);
    } catch {
      continue;
    }
    if (!isRecord(chunk)) continue;
    if (chunk.type === "error") return null;
    if (chunk.type === "text-delta" && typeof chunk.delta === "string") text += chunk.delta;
  }
  const reply = text.trim();
  return reply ? reply : null;
}
