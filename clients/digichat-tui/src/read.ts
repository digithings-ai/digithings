/**
 * DigiChat TUI ↔ DigiChat BFF (Surfaces 1.0 C1 / ADR D3).
 * Threads: /api/conversations. Send/stream: /api/v1/chat.
 */

import { endpoint } from "../../../packages/surface-config/src/endpoints.ts";

export const ROUTES = {
  conversations: "/api/conversations",
  chat: "/api/v1/chat",
} as const;

export const DASH = "—";
export const WELCOME = "What should we inspect?";
export const PLACEHOLDER = "Ask digichat…";
export const CREDIT = "powered by digichat — a digithings product.";
export const UNREACHABLE = "the official API could not be reached.";
export const AUTH_REQUIRED =
  "sign in or set DIGICHAT_API_KEY (Bearer digi_live_…) for the DigiChat BFF.";

export type ChatRole = "user" | "assistant";

export type ChatSession = { id: string; title: string };

export type ChatTool = { name: string; status: string; detail: string };

export type ChatMessage = {
  id: string;
  role: ChatRole;
  text: string;
  tool: ChatTool | null;
  reasoning: string;
  at: string;
};

export type Interpreted = {
  kind: "data" | "empty" | "error";
  data: unknown;
  note: string;
};

export type ChatScreen = {
  status: "ok" | "empty" | "error";
  sessions: ChatSession[];
  currentId: string | null;
  messages: ChatMessage[];
  note: string;
  /** Welcome copy only when the reads settled and the thread is empty. */
  welcome: boolean;
  /** False only when the current session says can_send is false. */
  canSend: boolean;
};

function row(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function errorMessage(body: unknown): string {
  const rec = row(body);
  if (!rec) return "";
  if (typeof rec.message === "string" && rec.message.trim()) return rec.message.trim();
  if (typeof rec.error === "string" && rec.error.trim()) return rec.error.trim();
  const nested = row(rec.error);
  const text = nested?.message;
  return typeof text === "string" ? text.trim() : "";
}

/** 502 and 503 are an empty read. Any other non-2xx is an error. Data stays null either way. */
export function interpretStatus(status: number, body: unknown): Interpreted {
  if (status === 401) {
    return { kind: "error", data: null, note: errorMessage(body) || AUTH_REQUIRED };
  }
  if (status === 502 || status === 503) {
    return { kind: "empty", data: null, note: errorMessage(body) };
  }
  if (status < 200 || status >= 300) {
    const why = errorMessage(body);
    return { kind: "error", data: null, note: why || `failed (${status})` };
  }
  return { kind: "data", data: body, note: "" };
}

export function chatBaseUrl(env: NodeJS.ProcessEnv = process.env): string {
  return endpoint("chat", env);
}

/** Machine key for the BFF. Never log or print this value. */
export function authHeaders(env: NodeJS.ProcessEnv = process.env): Record<string, string> {
  const key = env.DIGICHAT_API_KEY?.trim() || env.DIGI_CHAT_API_KEY?.trim();
  if (!key) return {};
  return { authorization: `Bearer ${key}` };
}

export function conversationRoute(id: string): string {
  return `${ROUTES.conversations}/${encodeURIComponent(id)}`;
}

export function sessionRows(data: unknown): ChatSession[] {
  const conversations = row(data)?.conversations;
  if (!Array.isArray(conversations)) return [];
  const out: ChatSession[] = [];
  for (const item of conversations) {
    const rec = row(item);
    const id = rec?.id;
    if (typeof id !== "string" || id.length === 0) continue;
    const title = rec?.title;
    const text = typeof title === "string" ? title.trim() : "";
    out.push({ id, title: text || DASH });
  }
  return out;
}

export function sessionId(data: unknown): string | null {
  const id = row(data)?.id;
  return typeof id === "string" && id.length > 0 ? id : null;
}

function textFromParts(parts: unknown): string {
  if (!Array.isArray(parts)) return "";
  const chunks: string[] = [];
  for (const part of parts) {
    const rec = row(part);
    if (!rec) continue;
    if (rec.type === "text" && typeof rec.text === "string" && rec.text.trim()) {
      chunks.push(rec.text);
    }
  }
  return chunks.join("");
}

function toolOf(rec: Record<string, unknown>): ChatTool | null {
  const tool = row(rec.tool);
  if (tool) {
    const name = tool.name;
    if (typeof name === "string" && name.trim()) {
      return {
        name: name.trim(),
        status: typeof tool.status === "string" ? tool.status.trim() : "",
        detail: typeof tool.detail === "string" ? tool.detail.trim() : "",
      };
    }
  }
  const parts = rec.parts;
  if (!Array.isArray(parts)) return null;
  for (const part of parts) {
    const p = row(part);
    if (!p || typeof p.type !== "string") continue;
    if (!p.type.startsWith("tool-")) continue;
    const name =
      (typeof p.toolName === "string" && p.toolName.trim()) ||
      (typeof p.name === "string" && p.name.trim()) ||
      p.type.slice("tool-".length);
    if (!name) continue;
    const state = typeof p.state === "string" ? p.state : "";
    const detail =
      typeof p.output === "string"
        ? p.output
        : typeof p.errorText === "string"
          ? p.errorText
          : "";
    return { name, status: state, detail };
  }
  return null;
}

function reasoningOf(rec: Record<string, unknown>): string {
  if (typeof rec.reasoning === "string") return rec.reasoning.trim();
  const parts = rec.parts;
  if (!Array.isArray(parts)) return "";
  const chunks: string[] = [];
  for (const part of parts) {
    const p = row(part);
    if (!p) continue;
    if (p.type === "reasoning" && typeof p.text === "string") chunks.push(p.text);
  }
  return chunks.join("").trim();
}

function messageText(rec: Record<string, unknown>, tool: ChatTool | null): string {
  const direct = rec.text;
  if (typeof direct === "string" && direct.trim()) return direct;
  const fromParts = textFromParts(rec.parts);
  if (fromParts.trim()) return fromParts;
  if (tool?.name) return tool.name;
  return DASH;
}

export function messageRows(data: unknown): ChatMessage[] {
  const messages = row(data)?.messages;
  if (!Array.isArray(messages)) return [];
  const out: ChatMessage[] = [];
  messages.forEach((item, index) => {
    const rec = row(item);
    if (!rec) return;
    const roleRaw = rec.role;
    if (roleRaw !== "user" && roleRaw !== "assistant") return;
    const id = rec.id;
    const tool = toolOf(rec);
    out.push({
      id: typeof id === "string" && id.length > 0 ? id : `row-${index}`,
      role: roleRaw,
      text: messageText(rec, tool),
      tool,
      reasoning: reasoningOf(rec),
      at: typeof rec.at === "string" ? rec.at.trim() : "",
    });
  });
  return out;
}

/** Build a screen from a conversations list + optional current conversation body. */
export function assembleFromBff(
  list: Interpreted,
  current: Interpreted | null,
  preferredId: string | null,
): ChatScreen {
  if (list.kind === "error") {
    return {
      status: "error",
      sessions: [],
      currentId: null,
      messages: [],
      note: list.note,
      welcome: false,
      canSend: true,
    };
  }
  if (list.kind === "empty") {
    return {
      status: "empty",
      sessions: [],
      currentId: null,
      messages: [],
      note: list.note,
      welcome: false,
      canSend: true,
    };
  }
  const sessions = sessionRows(list.data);
  const currentId =
    preferredId && sessions.some((s) => s.id === preferredId)
      ? preferredId
      : sessions[0]?.id ?? null;

  if (!currentId) {
    return {
      status: "empty",
      sessions,
      currentId: null,
      messages: [],
      note: "",
      welcome: true,
      canSend: true,
    };
  }

  if (!current || current.kind === "empty") {
    return {
      status: "empty",
      sessions,
      currentId,
      messages: [],
      note: current?.note ?? "",
      welcome: !current?.note,
      canSend: true,
    };
  }
  if (current.kind === "error") {
    return {
      status: "error",
      sessions,
      currentId,
      messages: [],
      note: current.note,
      welcome: false,
      canSend: true,
    };
  }

  const transcript = messageRows(current.data);
  return {
    status: transcript.length > 0 ? "ok" : "empty",
    sessions,
    currentId,
    messages: transcript,
    note: "",
    welcome: transcript.length === 0,
    canSend: true,
  };
}


async function readJson(res: Response): Promise<unknown> {
  try {
    return await res.json();
  } catch {
    return null;
  }
}

export async function readRoute(api: string, route: string, signal?: AbortSignal): Promise<Interpreted> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, {
      signal,
      headers: { ...authHeaders(), accept: "application/json" },
    });
  } catch {
    if (signal?.aborted) return { kind: "error", data: null, note: "" };
    return { kind: "error", data: null, note: UNREACHABLE };
  }
  return interpretStatus(res.status, await readJson(res));
}

export async function postRoute(
  api: string,
  route: string,
  payload: unknown,
  signal?: AbortSignal,
  extraHeaders?: Record<string, string>,
): Promise<Interpreted> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
        ...authHeaders(),
        ...extraHeaders,
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch {
    if (signal?.aborted) return { kind: "error", data: null, note: "" };
    return { kind: "error", data: null, note: UNREACHABLE };
  }
  return interpretStatus(res.status, await readJson(res));
}

export async function putRoute(
  api: string,
  route: string,
  payload: unknown,
  signal?: AbortSignal,
): Promise<Interpreted> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, {
      method: "PUT",
      headers: {
        "content-type": "application/json",
        accept: "application/json",
        ...authHeaders(),
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch {
    if (signal?.aborted) return { kind: "error", data: null, note: "" };
    return { kind: "error", data: null, note: UNREACHABLE };
  }
  if (res.status === 204) return { kind: "data", data: {}, note: "" };
  return interpretStatus(res.status, await readJson(res));
}

export type UiTextPart = { type: "text"; text: string };
export type UiFilePart = {
  type: "file";
  filename: string;
  mediaType: string;
  url: string;
};
export type UiPart = UiTextPart | UiFilePart;

export type UiChatMessage = {
  id: string;
  role: "user" | "assistant";
  parts: UiPart[];
};

export function toUiMessages(messages: readonly ChatMessage[]): UiChatMessage[] {
  return messages
    .filter((m) => !m.tool && m.text.trim() && m.text !== DASH)
    .map((m) => ({
      id: m.id,
      role: m.role,
      parts: [{ type: "text" as const, text: m.text }],
    }));
}

const MAX_ATTACH_BYTES = 2_000_000;

function guessMediaType(name: string): string {
  const lower = name.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".pdf")) return "application/pdf";
  if (lower.endsWith(".md")) return "text/markdown";
  if (lower.endsWith(".json")) return "application/json";
  if (lower.endsWith(".html") || lower.endsWith(".htm")) return "text/html";
  if (lower.endsWith(".txt") || lower.endsWith(".csv")) return "text/plain";
  return "application/octet-stream";
}

export function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}

/** Read local paths into AI SDK file parts (data URLs). Skips missing/oversized files. */
export async function filePartsFromPaths(
  paths: readonly string[],
): Promise<{ parts: UiFilePart[]; skipped: string[] }> {
  const parts: UiFilePart[] = [];
  const skipped: string[] = [];
  for (const path of paths) {
    const trimmed = path.trim();
    if (!trimmed) continue;
    try {
      const file = Bun.file(trimmed);
      const size = file.size;
      if (!Number.isFinite(size) || size <= 0 || size > MAX_ATTACH_BYTES) {
        skipped.push(basename(trimmed));
        continue;
      }
      const buf = new Uint8Array(await file.arrayBuffer());
      const mediaType = file.type || guessMediaType(trimmed);
      const b64 = Buffer.from(buf).toString("base64");
      parts.push({
        type: "file",
        filename: basename(trimmed),
        mediaType,
        url: `data:${mediaType};base64,${b64}`,
      });
    } catch {
      skipped.push(basename(trimmed));
    }
  }
  return { parts, skipped };
}

export type ByokModel = { id: string; label: string };

/** Parse GET /api/byok/models buckets into a flat pick list (ids only, no secrets). */
export function modelRowsFromByok(body: unknown): ByokModel[] {
  const rec = row(body);
  if (!rec || rec.ok === false) return [];
  const out: ByokModel[] = [];
  const seen = new Set<string>();
  for (const key of ["free", "flagship", "opensource", "other", "models"] as const) {
    const bucket = rec[key];
    if (!Array.isArray(bucket)) continue;
    for (const item of bucket) {
      const m = row(item);
      const id = typeof m?.id === "string" ? m.id.trim() : "";
      if (!id || seen.has(id)) continue;
      seen.add(id);
      const name = typeof m?.name === "string" ? m.name.trim() : "";
      out.push({ id, label: name || id });
    }
  }
  return out;
}

export async function fetchByokModels(
  api: string,
  provider: string,
  signal?: AbortSignal,
): Promise<{ kind: "ok"; models: ByokModel[] } | { kind: "error"; detail: string }> {
  const id = provider.trim().toLowerCase() || "openrouter";
  const interpreted = await readRoute(api, `/api/byok/models?provider=${encodeURIComponent(id)}`, signal);
  if (interpreted.kind !== "data") {
    return { kind: "error", detail: interpreted.note || "models unavailable" };
  }
  return { kind: "ok", models: modelRowsFromByok(interpreted.data) };
}

export type McpServerRow = { id: string; label: string };

export function mcpRowsFromTenantConfig(body: unknown): McpServerRow[] {
  const mcp = row(row(body)?.mcp);
  const servers = mcp?.servers;
  if (!Array.isArray(servers)) return [];
  const out: McpServerRow[] = [];
  for (const item of servers) {
    const rec = row(item);
    const id = typeof rec?.id === "string" ? rec.id.trim() : "";
    if (!id) continue;
    const label = typeof rec?.label === "string" && rec.label.trim() ? rec.label.trim() : id;
    out.push({ id, label });
  }
  return out;
}

/** MCP ids/labels from embed tenant-config (URLs never projected). */
export async function fetchMcpServers(
  api: string,
  signal?: AbortSignal,
): Promise<{ kind: "ok"; servers: McpServerRow[] } | { kind: "error"; detail: string }> {
  const interpreted = await readRoute(api, "/api/embed/tenant-config", signal);
  if (interpreted.kind !== "data") {
    return { kind: "error", detail: interpreted.note || "mcp list unavailable" };
  }
  return { kind: "ok", servers: mcpRowsFromTenantConfig(interpreted.data) };
}

function parseLoose(raw: string): unknown {
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function interpretChatStream(
  status: number,
  raw: string,
  contentType: string,
): { kind: "text"; text: string } | { kind: "error"; detail: string } {
  if (status === 401) {
    return { kind: "error", detail: errorMessage(parseLoose(raw)) || AUTH_REQUIRED };
  }
  if (status < 200 || status >= 300) {
    return { kind: "error", detail: errorMessage(parseLoose(raw)) || `chat ${status}` };
  }
  if (contentType.includes("application/json")) {
    const body = parseLoose(raw);
    if (!body) return { kind: "error", detail: "chat unreadable" };
    const why = errorMessage(body);
    if (why) return { kind: "error", detail: why };
    return { kind: "error", detail: "chat empty" };
  }
  const deltas: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const payload = line.startsWith("data:") ? line.slice(5).trim() : "";
    if (!payload || payload === "[DONE]") continue;
    const parsed = row(parseLoose(payload));
    if (!parsed || parsed.type !== "text-delta") continue;
    const bit = parsed.delta ?? parsed.textDelta ?? parsed.text;
    if (typeof bit === "string" && bit.length > 0) deltas.push(bit);
  }
  if (deltas.length === 0) return { kind: "error", detail: "chat empty" };
  return { kind: "text", text: deltas.join("") };
}

/** Session prefs → DigiChat BFF headers (same names as web chat-panel / embed). */
export function prefsHeaders(prefs: {
  webSearch: boolean;
  digisearch: boolean;
  digivault: boolean;
  language: string;
  effort: string;
  searchEngine: string;
  model: string;
}): Record<string, string> {
  const headers: Record<string, string> = {};
  if (prefs.webSearch) headers["X-Digi-Enable-Web-Search"] = "1";
  if (prefs.digisearch) headers["X-Digi-Force-Tool"] = "digisearch";
  else if (prefs.digivault) headers["X-Digi-Force-Tool"] = "digivault";
  if (prefs.language && prefs.language !== "en") headers["X-Digi-Language"] = prefs.language;
  if (prefs.effort) headers["X-Digi-Effort"] = prefs.effort;
  if (prefs.model.trim()) headers["X-Digi-Model"] = prefs.model.trim();
  const engine = prefs.searchEngine.trim().toLowerCase();
  if (
    engine &&
    ["auto", "internal", "exa", "tavily", "parallel", "firecrawl", "tinyfish"].includes(engine)
  ) {
    headers["X-Digi-Search-Engine"] = engine;
  }
  return headers;
}

export async function postChat(
  api: string,
  sessionId: string,
  messages: UiChatMessage[],
  signal?: AbortSignal,
  prefs?: {
    webSearch: boolean;
    digisearch: boolean;
    digivault: boolean;
    language: string;
    effort: string;
    searchEngine: string;
    model: string;
  },
): Promise<{ kind: "text"; text: string } | { kind: "error"; detail: string }> {
  try {
    const res = await fetch(`${api}${ROUTES.chat}`, {
      method: "POST",
      signal,
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream, application/json",
        "x-digichat-session": sessionId,
        ...authHeaders(),
        ...(prefs ? prefsHeaders(prefs) : {}),
      },
      body: JSON.stringify({ messages }),
    });
    const text = await res.text();
    if (res.status === 401) {
      return { kind: "error", detail: errorMessage(parseLoose(text)) || AUTH_REQUIRED };
    }
    return interpretChatStream(res.status, text, res.headers.get("content-type") ?? "");
  } catch {
    if (signal?.aborted) return { kind: "error", detail: "" };
    return { kind: "error", detail: UNREACHABLE };
  }
}

/** Reply text from a successful send. Absent means the API sent none. */
export function replyText(data: unknown): string | null {
  const reply = row(data)?.reply;
  return typeof reply === "string" && reply.trim() ? reply : null;
}
