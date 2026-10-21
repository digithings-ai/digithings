/**
 * Strip credentials before they can land in a replay file.
 *
 * Labeled secrets (auth headers, embed tokens, invite keys, API keys) are
 * removed even when the value has no recognizable prefix. Known token shapes
 * are removed wherever they sit in prose or tool JSON.
 */

const SENSITIVE_KEY =
  /^(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-embed-token|x-embed-chat-token|x-invite-key|x-digichat-session|api[-_]?key|embed[-_]?(?:key|token)|invite[-_]?(?:key|token)|access[-_]?token|refresh[-_]?token|id[-_]?token|auth[-_]?secret|nextauth[-_]?secret|password|secret)$/i;

const TOKEN_SHAPES: readonly RegExp[] = [
  /\b(?:dgk_live_|digi_live_|dgs_live_)[A-Za-z0-9_\-]{6,}\b/g,
  /\bsk-(?:ant-|or-|proj-)?[A-Za-z0-9_\-]{8,}\b/g,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
  /\bBearer\s+[A-Za-z0-9\-._~+/]{8,}={0,2}/gi,
  /(?:authorization|x-api-key|x-embed-token|x-embed-chat-token|x-invite-key|api[_-]?key|embed[_-]?(?:key|token)|invite[_-]?(?:key|token)|access[_-]?token|refresh[_-]?token|auth[_-]?secret|nextauth[_-]?secret)\s*["']?\s*[:=]\s*["']?[^"'\s,}&]{6,}/gi,
];

const QUERY_SECRET =
  /([?&](?:token|api_key|apikey|access_token|invite|invite_key|embed_token|key)=)[^&#\s"']*/gi;

export const REDACTED = "[redacted]";

export function redactString(value: string): string {
  let out = value;
  for (const pattern of TOKEN_SHAPES) {
    pattern.lastIndex = 0;
    out = out.replace(pattern, REDACTED);
  }
  QUERY_SECRET.lastIndex = 0;
  return out.replace(QUERY_SECRET, `$1${REDACTED}`);
}

export function redactValue<T>(value: T): T {
  return walk(value) as T;
}

function walk(value: unknown): unknown {
  if (typeof value === "string") return redactString(value);
  if (Array.isArray(value)) return value.map((item) => walk(item));
  if (!value || typeof value !== "object") return value;
  const out: Record<string, unknown> = {};
  for (const [key, inner] of Object.entries(value as Record<string, unknown>)) {
    if (SENSITIVE_KEY.test(key)) {
      out[key] = REDACTED;
      continue;
    }
    out[key] = walk(inner);
  }
  return out;
}
