/**
 * Build POST /api/chat request URL + headers for the digichat Ink CLI.
 * Pure helpers — unit-tested without a TTY or live server.
 */

export type DigichatCliAuth =
  | { kind: "embed"; token: string; host?: string }
  | { kind: "api_key"; apiKey: string }
  | { kind: "none" };

export type DigichatCliRequestOptions = {
  baseUrl: string;
  auth: DigichatCliAuth;
  language?: string;
  model?: string;
  sessionId?: string;
};

/** Normalize DIGICHAT_URL / --url to an origin without trailing slash. */
export function normalizeDigichatBaseUrl(raw: string): string {
  const trimmed = raw.trim().replace(/\/+$/, "");
  if (!trimmed) {
    throw new Error("DIGICHAT_URL / --url is required");
  }
  let url: URL;
  try {
    url = new URL(trimmed.includes("://") ? trimmed : `http://${trimmed}`);
  } catch {
    throw new Error(`invalid digichat URL: ${raw}`);
  }
  return url.origin;
}

export function digichatChatUrl(baseUrl: string): string {
  return `${normalizeDigichatBaseUrl(baseUrl)}/api/chat`;
}

export function buildDigichatChatHeaders(
  opts: DigichatCliRequestOptions,
): Record<string, string> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
    accept: "text/event-stream, application/json",
    "x-digi-caller": "digichat-cli",
  };
  if (opts.sessionId?.trim()) {
    headers["x-digichat-session"] = opts.sessionId.trim();
  }
  if (opts.language?.trim() && opts.language.trim() !== "en") {
    headers["x-digi-language"] = opts.language.trim();
  }
  if (opts.model?.trim()) {
    headers["x-digi-model"] = opts.model.trim();
  }
  if (opts.auth.kind === "embed") {
    headers["x-embed-token"] = opts.auth.token;
    if (opts.auth.host?.trim()) {
      headers["x-embed-host"] = opts.auth.host.trim();
    }
  } else if (opts.auth.kind === "api_key") {
    headers["authorization"] = `Bearer ${opts.auth.apiKey}`;
  }
  return headers;
}

/**
 * Fail closed when the operator points at a YAML with `cli.enabled: false`.
 * Missing `cli` defaults to disabled (advisory → enforced for this binary).
 */
export function assertCliEnabled(
  config: { cli?: { enabled?: boolean } } | null | undefined,
  source = "digichat config",
): void {
  if (config?.cli?.enabled === true) return;
  throw new Error(
    `${source}: cli.enabled is not true — refuse to start Ink CLI (set cli.enabled: true or omit --config)`,
  );
}
