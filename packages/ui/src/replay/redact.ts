/**
 * Strip credentials before they can land in a replay file.
 *
 * Labeled secrets (auth headers, embed tokens, invite keys, API keys) are
 * removed even when the value has no recognizable prefix. Known token shapes
 * are removed wherever they sit in prose or tool JSON.
 */

const SENSITIVE_KEY =
  /^(authorization|proxy-authorization|cookie|set-cookie|x-api-key|x-embed-token|x-embed-chat-token|x-invite-key|x-digichat-session|api[-_]?key|embed[-_]?(?:key|token)|invite[-_]?(?:key|token)|access[-_]?token|refresh[-_]?token|id[-_]?token|auth[-_]?secret|nextauth[-_]?secret|password|secret|session)$/i;

/** `token`, `authToken`, `client_secret`, `privateKey`… (not `tokens` / `max_tokens`). */
const SENSITIVE_KEY_SUFFIX =
  /(?:token|secret|secret[-_]?key|password|passwd|api[-_]?key|private[-_]?key|credentials?|session[-_]?id|cookie)$/i;

const TOKEN_SHAPES: readonly RegExp[] = [
  // Separators and values use bounded runs so long inputs stay linear
  // (CodeQL js/polynomial-redos). Authorization and Cookie are in LABELED below.
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
  // OCC invite keys are a standalone 48-hex token. A shorter or longer hex
  // run (a git sha, a 32-byte hex secret) does not match.
  /\b[0-9a-fA-F]{48}\b/g,
  /(?:x-api-key|x-embed-token|x-embed-chat-token|x-invite-key|api[_-]?key|embed[_-]?(?:key|token)|invite[_-]?(?:key|token)|access[_-]?token|refresh[_-]?token|auth[_-]?secret|nextauth[_-]?secret|client[_-]?secret|private[_-]?key|password|passwd|(?<![A-Za-z0-9_?&-])token)["']?[ \t]{0,8}[:=][ \t]{0,8}["']?(?!\[redacted\])[^"'\s,}&]{6,}/gi,
];

/**
 * A query secret ends at `&`, `#`, whitespace or a quote.
 *
 * A `)` inside the value belongs to the secret when the value continues after
 * it, so a secret that contains a parenthesis cannot leak its tail
 * (`?token=abc)def` redacts the whole value). A `)` that closes a link
 * (`?token=abc)`) or that sits in front of sentence punctuation
 * (`?token=abc).`) stays outside the value: the continuation character must
 * look like part of a secret, not like prose.
 */
const QUERY_SECRET =
  /([?&](?:token|api_key|apikey|access_token|invite|invite_key|embed_token|key|x-amz-signature|x-amz-credential|x-amz-security-token|awsaccesskeyid|x-goog-signature|x-goog-credential|signature|sig|key-pair-id)=)(?:[^&#\s"')]|\)[^\s&#"'.,;:!?\)])*/gi;

/**
 * Header-style labels whose value is replaced but whose label stays, so the
 * transcript still reads. Authorization takes a scheme (Bearer, Basic, Token,
 * …) and then a credential; without a scheme the value must contain a digit,
 * so prose such as "Authorization: the user signs in" is left alone.
 */
const LABELED: readonly RegExp[] = [
  /(\b(?:proxy-)?authorization["']?[ \t]{0,8}[:=][ \t]{0,8}["']?)(?:(?:bearer|basic|token|digest|apikey|negotiate)[ \t]{1,4}(?:token=)?[^\s"',}]{3,2048}|(?=[^\s"',}]{0,2048}\d)[A-Za-z0-9\-._~+/=:]{8,2048})/gi,
  /(\b(?:set-cookie|cookie|x-digichat-session)["']?[ \t]{0,8}:[ \t]{0,8}["']?)[^"'\n\r]{1,4096}/gi,
  // A backtick inside a session value belongs to the value when the value
  // continues after it, so a secret that contains a backtick cannot leak its
  // tail (`session=abc`def`). A backtick that closes a code span
  // (`session=abc``) stays outside the value.
  /((?<![A-Za-z0-9_-])(?:session(?:[_-]?id)?|sid|csrftoken|connect\.sid)=)(?:[^;\s"',&`]|`[^\s;&"'.,!?:`)]){4,512}/gi,
  // scheme://user:password@host (DSNs, URLs with userinfo).
  /(\b[a-z][a-z0-9+.-]{1,20}:\/\/[^\s:/@"']{1,256}:)[^\s@/"']{1,256}(?=@)/gi,
];

export const REDACTED = "[redacted]";

export function redactString(value: string): string {
  let out = value;
  for (const pattern of TOKEN_SHAPES) {
    pattern.lastIndex = 0;
    out = out.replace(pattern, REDACTED);
  }
  for (const pattern of LABELED) {
    pattern.lastIndex = 0;
    out = out.replace(pattern, `$1${REDACTED}`);
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
