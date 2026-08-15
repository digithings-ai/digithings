/** Shared AbortController-based fetch timeout. Extracted from
 * app/api/byok/test/route.ts so app/api/byok/models/route.ts doesn't
 * duplicate it — see docs/superpowers/specs/2026-08-13-digichat-byok-model-catalog-design.md.
 */

export const DEFAULT_FETCH_TIMEOUT_MS = 10_000;

export async function fetchWithTimeout(
  url: string,
  init: RequestInit,
  timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS,
): Promise<globalThis.Response> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timeout);
  }
}

export function abortOrMessage(e: unknown, timeoutMs: number = DEFAULT_FETCH_TIMEOUT_MS): string {
  if (e instanceof Error) {
    return e.name === "AbortError" ? `Request timed out after ${timeoutMs / 1000} s.` : e.message;
  }
  return "Unknown error";
}
