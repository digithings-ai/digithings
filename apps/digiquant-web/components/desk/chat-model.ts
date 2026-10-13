/** Shapes painted from the official chat reads. Missing text is an em dash. */

export const CHAT_ROUTES = {
  sessions: "/chat/sessions",
  current: "/chat/sessions/current",
  messages: "/chat/sessions/current/messages",
} as const;

export type DeskMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export type DeskThread = {
  status: "regular";
  id: string;
  title: string;
};

function row(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

export function sessionRows(data: unknown): DeskThread[] {
  const sessions = row(data)?.sessions;
  if (!Array.isArray(sessions)) return [];
  const out: DeskThread[] = [];
  for (const item of sessions) {
    const rec = row(item);
    const id = rec?.id;
    if (typeof id !== "string" || id.length === 0) continue;
    const title = rec?.title;
    out.push({
      status: "regular",
      id,
      title: typeof title === "string" && title.trim() ? title : "—",
    });
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
  return "—";
}

export function messageRows(data: unknown): DeskMessage[] {
  const messages = row(data)?.messages;
  if (!Array.isArray(messages)) return [];
  const out: DeskMessage[] = [];
  messages.forEach((item, index) => {
    const rec = row(item);
    if (!rec) return;
    const id = rec.id;
    const role = rec.role === "user" ? "user" : "assistant";
    out.push({
      id: typeof id === "string" && id.length > 0 ? id : `row-${index}`,
      role,
      content: messageText(rec),
    });
  });
  return out;
}

/** A reply string from a successful send. Absent means the API sent none. */
export function replyText(data: unknown): string | null {
  const reply = row(data)?.reply;
  return typeof reply === "string" && reply.trim() ? reply : null;
}

export function messageRoute(id: string): string {
  return `/chat/sessions/${encodeURIComponent(id)}/messages`;
}
