/**
 * Browser-side client for the local digiquant gateway (127.0.0.1:8792).
 *
 * The gateway is local-only and intentionally never exposed to the public
 * internet. This client enforces that invariant at the URL and page-origin
 * level before making any network request, so a misconfigured env var or a
 * production deployment can never accidentally reach the gateway.
 *
 * Reads NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL (inlined at Next.js build time for
 * static exports). All exported functions are safe to call from React
 * components: they never throw, and every failure carries an explicit reason.
 */

// ─── Gateway state ────────────────────────────────────────────────────────

/**
 * Why the gateway is unavailable. Exposed on results so callers can show an
 * appropriate message rather than a generic "offline" error.
 *
 * - "unset"         — NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL is empty / not set.
 * - "unsafe"        — The configured URL fails the loopback+HTTP validation.
 * - "nonlocal-page" — The current page is not served from loopback; opening a
 *                     connection to the gateway would cross origins and is
 *                     refused by the browser or simply pointless in production.
 */
export type GatewayUnavailableReason = "unset" | "unsafe" | "nonlocal-page";

export interface GatewayAvailable {
  available: true;
  baseUrl: string;
}

export interface GatewayUnavailable {
  available: false;
  reason: GatewayUnavailableReason;
}

export type GatewayState = GatewayAvailable | GatewayUnavailable;

// ─── Probe envelope (mirrors make_envelope in live_gateway.py) ────────────

/** Typed response envelope returned by every /v1/probe/* route. */
export interface ProbeEnvelope {
  id: string;
  tool: string | null;
  args: Record<string, unknown>;
  ok: boolean;
  latencyMs: number;
  cached: boolean;
  fetchedAt: string;
  attribution: string[];
  delayNote: string | null;
  empty: string | null;
  data: unknown;
  error: { code: string; message: string } | null;
}

// ─── Result types ─────────────────────────────────────────────────────────

/** Result of a /healthz check. */
export type HealthzResult = { ok: true } | { ok: false; error: string };

/** Result of a /v1/probe/* call. */
export type ProbeResult = { ok: true; envelope: ProbeEnvelope } | { ok: false; error: string };

// ─── URL validation ────────────────────────────────────────────────────────

const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1", "[::1]"]);

/**
 * Returns true only when `raw` is a plain HTTP URL with an exact loopback
 * host and no username, password, query string, or hash fragment.
 *
 * Pure function — no side effects, safe to call in tests and SSR.
 */
export function validateGatewayUrl(raw: string): boolean {
  if (!raw.trim()) return false;
  let url: URL;
  try {
    url = new URL(raw);
  } catch {
    return false;
  }
  if (url.protocol !== "http:") return false;
  if (url.username || url.password) return false;
  if (url.pathname !== "/") return false;
  if (url.search) return false;
  if (url.hash) return false;
  // url.hostname normalises "[::1]" to "[::1]" for IPv6 literals.
  if (!LOOPBACK_HOSTS.has(url.hostname)) return false;
  return true;
}

// ─── State resolution ──────────────────────────────────────────────────────

function gatewayEnvUrl(): string {
  return (process.env.NEXT_PUBLIC_DIGIQUANT_GATEWAY_URL ?? "").trim().replace(/\/+$/, "");
}

const LOOPBACK_PAGE_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

function isLoopbackPageHost(hostname: string): boolean {
  return LOOPBACK_PAGE_HOSTS.has(hostname);
}

/**
 * Resolves whether the gateway is available from the current context.
 *
 * Pass `pageHostname` explicitly in tests (or on the server) to avoid the
 * `window.location` access. When omitted and `window` is not defined (node /
 * SSR), the state is `nonlocal-page` — the gateway must not be called.
 */
export function resolveGatewayState(pageHostname?: string): GatewayState {
  const raw = gatewayEnvUrl();
  if (!raw) return { available: false, reason: "unset" };
  if (!validateGatewayUrl(raw)) return { available: false, reason: "unsafe" };

  let host = pageHostname;
  if (host === undefined) {
    try {
      host = window.location.hostname;
    } catch {
      return { available: false, reason: "nonlocal-page" };
    }
  }

  if (!isLoopbackPageHost(host)) return { available: false, reason: "nonlocal-page" };
  return { available: true, baseUrl: raw };
}

// ─── Fetch helpers ─────────────────────────────────────────────────────────

/**
 * Checks gateway liveness via `GET /healthz`.
 *
 * Never throws — all failures are reflected in the return value.
 */
export async function fetchHealthz(pageHostname?: string): Promise<HealthzResult> {
  const state = resolveGatewayState(pageHostname);
  if (!state.available) return { ok: false, error: state.reason };
  try {
    const res = await fetch(`${state.baseUrl}/healthz`);
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const body = (await res.json()) as { ok?: unknown };
    return body.ok === true
      ? { ok: true }
      : { ok: false, error: "unexpected health response" };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}

/**
 * Calls `GET /v1/probe/luxalgoSearch?query=…&limit=…`.
 *
 * Returns the full probe envelope on success so callers can display
 * `attribution`, `delayNote`, and `data`. Never throws.
 */
export async function fetchLuxalgoSearch(
  query: string,
  limit: number,
  pageHostname?: string,
): Promise<ProbeResult> {
  const state = resolveGatewayState(pageHostname);
  if (!state.available) return { ok: false, error: state.reason };
  const params = new URLSearchParams({ query, limit: String(limit) });
  try {
    const res = await fetch(`${state.baseUrl}/v1/probe/luxalgoSearch?${params}`);
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const envelope = (await res.json()) as ProbeEnvelope;
    if (!envelope.ok) {
      return { ok: false, error: envelope.error?.message ?? "probe returned ok: false" };
    }
    return { ok: true, envelope };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : String(err) };
  }
}
