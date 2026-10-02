/** Chat-screen reads. Same routes the desk uses. Nothing here invents a thread. */

export const ROUTES = {
  sessions: "/chat/sessions",
  current: "/chat/sessions/current",
  messages: "/chat/sessions/current/messages",
} as const;

export const DASH = "—";
export const WELCOME = "What should we inspect?";
export const PLACEHOLDER = "Ask digichat…";
export const CREDIT = "powered by digichat — a digithings product.";
export const UNREACHABLE = "the official API could not be reached.";

export type ChatRole = "user" | "assistant";

export type ChatSession = { id: string; title: string };

export type ChatMessage = { id: string; role: ChatRole; text: string };

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
};

function row(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function errorMessage(body: unknown): string {
  const message = row(body)?.error;
  const text = row(message)?.message;
  return typeof text === "string" ? text.trim() : "";
}

/** 502 and 503 are an empty read. Any other non-2xx is an error. Data stays null either way. */
export function interpretStatus(status: number, body: unknown): Interpreted {
  if (status === 502 || status === 503) {
    return { kind: "empty", data: null, note: errorMessage(body) };
  }
  if (status < 200 || status >= 300) {
    const why = errorMessage(body);
    return { kind: "error", data: null, note: why || `failed (${status})` };
  }
  const data = row(body)?.data ?? null;
  return { kind: "data", data, note: "" };
}

export function sessionRows(data: unknown): ChatSession[] {
  const sessions = row(data)?.sessions;
  if (!Array.isArray(sessions)) return [];
  const out: ChatSession[] = [];
  for (const item of sessions) {
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

function messageText(rec: Record<string, unknown>): string {
  const text = rec.text;
  if (typeof text === "string" && text.trim()) return text;
  const tool = row(rec.tool);
  const name = tool?.name;
  if (typeof name === "string" && name.trim()) return name;
  return DASH;
}

export function messageRows(data: unknown): ChatMessage[] {
  const messages = row(data)?.messages;
  if (!Array.isArray(messages)) return [];
  const out: ChatMessage[] = [];
  messages.forEach((item, index) => {
    const rec = row(item);
    if (!rec) return;
    const id = rec.id;
    const role = rec.role === "user" ? "user" : "assistant";
    out.push({
      id: typeof id === "string" && id.length > 0 ? id : `row-${index}`,
      role,
      text: messageText(rec),
    });
  });
  return out;
}

/** One screen from the three desk reads. A closed or failed read paints no thread. */
export function assembleScreen(sessions: Interpreted, current: Interpreted, messages: Interpreted): ChatScreen {
  const parts = [sessions, current, messages];
  const error = parts.find((part) => part.kind === "error");
  if (error) {
    return { status: "error", sessions: [], currentId: null, messages: [], note: error.note, welcome: false };
  }
  const closed = parts.find((part) => part.kind === "empty");
  if (closed) {
    return { status: "empty", sessions: [], currentId: null, messages: [], note: closed.note, welcome: false };
  }
  const list = sessionRows(sessions.data);
  const transcript = messageRows(messages.data);
  const id = sessionId(current.data);
  return {
    status: transcript.length > 0 ? "ok" : "empty",
    sessions: list,
    currentId: id,
    messages: transcript,
    note: "",
    welcome: transcript.length === 0,
  };
}

export function sessionRoute(id: string): string {
  return `/chat/sessions/${encodeURIComponent(id)}`;
}

export function messageRoute(id: string): string {
  return `/chat/sessions/${encodeURIComponent(id)}/messages`;
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
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { kind: "error", data: null, note: "" };
    return { kind: "error", data: null, note: UNREACHABLE };
  }
  return interpretStatus(res.status, await readJson(res));
}

/** Reply text from a successful send. Absent means the API sent none. */
export function replyText(data: unknown): string | null {
  const reply = row(data)?.reply;
  return typeof reply === "string" && reply.trim() ? reply : null;
}

export async function postRoute(api: string, route: string, payload: unknown, signal?: AbortSignal): Promise<Interpreted> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal,
    });
  } catch {
    if (signal?.aborted) return { kind: "error", data: null, note: "" };
    return { kind: "error", data: null, note: UNREACHABLE };
  }
  return interpretStatus(res.status, await readJson(res));
}
