/**
 * Strip credentials before they can land in a replay file.
 *
 * Labeled secrets (auth headers, embed tokens, invite keys, API keys) are
 * removed even when the value has no recognizable prefix. Known token shapes
 * are removed wherever they sit in prose or tool JSON.
 */

const SENSITIVE_KEY =
  /^(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-embed-token|x-embed-chat-token|x-invite-key|x-digichat-session|api[-_]?key|embed[-_]?(?:key|token)|invite[-_]?(?:key|token)|access[-_]?token|refresh[-_]?token|id[-_]?token|auth[-_]?secret|nextauth[-_]?secret|password|secret)$/i;

/** `token`, `authToken`, `client_secret`, `privateKey`… (not `tokens` / `max_tokens`). */
const SENSITIVE_KEY_SUFFIX = /(?:token|secret|password|passwd|api[-_]?key|private[-_]?key)$/i;

const TOKEN_SHAPES: readonly RegExp[] = [
  // A whole Authorization header value, whatever the scheme (Bearer, Basic,
  // helpdesk-style `Token token=…`), up to the end of the quoted value or line.
  // Separators use bounded runs so long inputs stay linear (CodeQL js/polynomial-redos).
  /\b(?:proxy-)?authorization\b["']?[ \t]{0,8}[:=][ \t]{0,8}["']?[^"'\n\r,}]{1,2048}/gi,
  /\bToken\s+token=[^\s"',}&]+/gi,
  /\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b/g,
  /\bgithub_pat_[A-Za-z0-9_]{20,}\b/g,
  /\bxox[abposr]-[A-Za-z0-9-]{10,}\b/g,
  /\bAKIA[0-9A-Z]{16}\b/g,
  /\bAIza[0-9A-Za-z_-]{35}\b/g,
  /\bglpat-[A-Za-z0-9_-]{20,}\b/g,
  /\b(?:dgk_live_|digi_live_|dgs_live_)[A-Za-z0-9_\-]{6,}\b/g,
  /\bsk-(?:ant-|or-|proj-)?[A-Za-z0-9_\-]{8,}\b/g,
  /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b/g,
  /\bBearer\s+[A-Za-z0-9\-._~+/]{8,}={0,2}/gi,
  /(?:authorization|x-api-key|x-embed-token|x-embed-chat-token|x-invite-key|api[_-]?key|embed[_-]?(?:key|token)|invite[_-]?(?:key|token)|access[_-]?token|refresh[_-]?token|auth[_-]?secret|nextauth[_-]?secret|client[_-]?secret|private[_-]?key|password|passwd|(?<![A-Za-z0-9_?&-])token)["']?[ \t]{0,8}[:=][ \t]{0,8}["']?[^"'\s,}&]{6,}/gi,
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
    if (SENSITIVE_KEY.test(key) || SENSITIVE_KEY_SUFFIX.test(key)) {
      out[key] = REDACTED;
      continue;
    }
    out[key] = walk(inner);
  }
  return out;
}
