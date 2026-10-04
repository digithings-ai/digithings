/**
 * Operator MCP servers from deploy YAML (#3736).
 * URLs never reach the browser; the BFF forwards allowlisted https(s) URLs
 * to digigraph. Client-supplied MCP URLs are ignored.
 */

import type { DigichatDeployment } from "./schema";

const MCP_ID = /^[a-z0-9][a-z0-9-]{0,63}$/;
const METADATA_HOSTS = new Set([
  "169.254.169.254",
  "100.100.100.200",
  "metadata.google.internal",
  "metadata.goog",
  "metadata",
  "localhost",
  "localtest.me",
  "lvh.me",
  "vcap.me",
]);
const LOOPBACK_DNS_SUFFIXES = [".localtest.me", ".lvh.me", ".vcap.me"];
const REBIND_SUFFIXES = [".nip.io", ".sslip.io", ".xip.io"];
const EMBEDDED_IPV4 = /(?:^|\.)((?:\d{1,3}\.){3}\d{1,3})(?:\.|$)/;

function parseIPv4Octets(host: string): number[] | null {
  const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(host);
  if (!m) return null;
  const oct = m.slice(1).map(Number);
  if (oct.some((n) => n > 255)) return null;
  return oct;
}

function ipv4FromIntegerHost(host: string): number[] | null {
  if (/^0x[0-9a-f]+$/i.test(host)) {
    const n = Number.parseInt(host, 16);
    if (!Number.isInteger(n) || n < 0 || n > 0xffffffff) return null;
    return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
  }
  if (/^\d+$/.test(host)) {
    const n = Number(host);
    if (!Number.isInteger(n) || n < 0 || n > 0xffffffff) return null;
    return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
  }
  return null;
}

function parseHostPart(part: string): number | null {
  if (/^0x[0-9a-f]+$/i.test(part)) {
    const n = Number.parseInt(part, 16);
    return Number.isInteger(n) && n >= 0 ? n : null;
  }
  if (/^\d+$/.test(part)) {
    const n = Number(part);
    return Number.isInteger(n) && n >= 0 ? n : null;
  }
  return null;
}

/** WHATWG-style IPv4 so 127.1 / 0x7f.0x0.0x0.0x1 match Node's URL parser. */
function coerceIPv4(host: string): number[] | null {
  const dotted = parseIPv4Octets(host);
  if (dotted) return dotted;
  const integer = ipv4FromIntegerHost(host);
  if (integer) return integer;
  const parts = host.split(".");
  if (parts.length < 2 || parts.length > 4) return null;
  const nums: number[] = [];
  for (const p of parts) {
    const n = parseHostPart(p);
    if (n === null) return null;
    nums.push(n);
  }
  if (nums.length === 2) {
    if (nums[0]! > 255 || nums[1]! > 0xffffff) return null;
    const n = ((nums[0]! << 24) | nums[1]!) >>> 0;
    return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
  }
  if (nums.length === 3) {
    if (nums[0]! > 255 || nums[1]! > 255 || nums[2]! > 0xffff) return null;
    const n = ((nums[0]! << 24) | (nums[1]! << 16) | nums[2]!) >>> 0;
    return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255];
  }
  if (nums.some((n) => n > 255)) return null;
  return nums;
}

function ipv4IsBlocked(oct: number[]): boolean {
  const a = oct[0] ?? 0;
  const b = oct[1] ?? 0;
  if (a === 0 || a === 10 || a === 127) return true;
  if (a === 169 && b === 254) return true;
  if (a === 192 && b === 168) return true;
  if (a === 172 && b >= 16 && b <= 31) return true;
  if (a === 100 && b === 100 && (oct[2] ?? 0) === 100 && (oct[3] ?? 0) === 200) return true;
  if (a >= 224) return true;
  return false;
}

function mappedIpv4(host: string): number[] | null {
  const dotted = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(host);
  if (dotted) return parseIPv4Octets(dotted[1] ?? "");
  const hex = /^::ffff:([0-9a-f]{1,4}):([0-9a-f]{1,4})$/i.exec(host);
  if (!hex) return null;
  const hi = Number.parseInt(hex[1] ?? "0", 16);
  const lo = Number.parseInt(hex[2] ?? "0", 16);
  return [(hi >> 8) & 255, hi & 255, (lo >> 8) & 255, lo & 255];
}

function hostnameIsBlocked(host: string): boolean {
  const h = host.replace(/^\[|\]$/g, "").toLowerCase().replace(/\.$/, "");
  if (!h || METADATA_HOSTS.has(h)) return true;
  if (h === "::" || h === "::1") return true;
  if (h.includes(":")) {
    if (h.startsWith("fe80:") || h.startsWith("ff")) return true;
    if (h.startsWith("fc") || h.startsWith("fd")) return true;
  }
  if (h.endsWith(".internal") || h.endsWith(".localhost")) return true;
  if (LOOPBACK_DNS_SUFFIXES.some((s) => h.endsWith(s))) return true;
  if (REBIND_SUFFIXES.some((s) => h.endsWith(s))) return true;
  const mapped = mappedIpv4(h);
  if (mapped) return ipv4IsBlocked(mapped);
  const coerced = coerceIPv4(h);
  if (coerced) return ipv4IsBlocked(coerced);
  const embedded = EMBEDDED_IPV4.exec(h);
  if (embedded) {
    const oct = parseIPv4Octets(embedded[1] ?? "");
    if (oct && ipv4IsBlocked(oct)) return true;
  }
  return false;
}

/** Operator YAML MCP URL — https/http, no userinfo, no loopback/metadata. */
export function isAllowedMcpServerUrl(raw: string): boolean {
  let u: URL;
  try {
    u = new URL(raw.trim());
  } catch {
    return false;
  }
  if (u.protocol !== "http:" && u.protocol !== "https:") return false;
  if (u.username || u.password) return false;
  return !hostnameIsBlocked(u.hostname);
}

/**
 * Session client URLs must be https. Parse rather than string-match so a valid
 * mixed-case scheme (`HTTPS://host`) is accepted — WHATWG lowercases `protocol`,
 * matching the `new URL`-based `isAllowedMcpServerUrl` check.
 */
function isHttpsUrl(raw: string): boolean {
  try {
    return new URL(raw).protocol === "https:";
  } catch {
    return false;
  }
}

export type McpServerForward = {
  id: string;
  url: string;
  /** Operator-static secret, already resolved by the loader (#3841). */
  token?: string;
  /** Custom outbound header name for `token`, e.g. "X-API-Key" (#3841). */
  authHeader?: string;
  /**
   * MCP setup values applied when this server's tools are registered (e.g.
   * the digisearch index name or the digivault path prefix). Forwarded to
   * digigraph; the model never sees or supplies them.
   */
  setup?: Record<string, string>;
  /**
   * Operator tool allowlist for this server row (DIG-284). Remote tool names,
   * exact match, no globs. Absent means deny-by-default upstream: zero tools
   * are offered, which is the same as an empty list. Operator-only — the
   * session overlay can never set this.
   */
  allowedTools?: string[];
  /**
   * Subset of `allowedTools` whose tools mutate remote state (DIG-284).
   * Operator-only, same rules as `allowedTools`.
   */
  mutatingTools?: string[];
};

export type McpSessionOverlayItem = {
  id: string;
  url?: string;
  auth?: string;
  token?: string;
  // Deliberately no `allowedTools` / `mutatingTools` (DIG-284), extending the
  // `authHeader` invariant pinned by the #3841 test in mcp-servers.test.ts.
  // These are operator-only: a visitor attaching a session connector gets zero
  // tools, and a session overlay can never widen an operator row's allowlist.
  // `url` is bounded the same way — it can only ever introduce a new row, never
  // repoint an operator one.
};

export type McpUpstreamServer = {
  id: string;
  url: string;
  auth?: string;
  token?: string;
  /** Operator-only — session overlay can never set this (#3841). */
  authHeader?: string;
  /**
   * MCP setup values applied when this server's tools are registered (e.g.
   * the digisearch index name or the digivault path prefix). Forwarded to
   * digigraph; the model never sees or supplies them.
   */
  setup?: Record<string, string>;
  /** Operator-only — session overlay can never set this (DIG-284). */
  allowedTools?: string[];
  /** Operator-only — session overlay can never set this (DIG-284). */
  mutatingTools?: string[];
};

const MCP_AUTH = new Set(["none", "bearer", "oauth"]);
const MAX_SESSION_SERVERS = 8;
const MAX_OVERLAY_JSON = 8_192;
const MAX_UPSTREAM_JSON = 16_384;
const MAX_TOKEN = 4_096;

/**
 * Bounds on the operator tool allowlists (`allowedTools`, `mutatingTools`).
 * These live here, next to the header guard that has to honour them, and
 * `schema.ts` imports them so the zod bound and the projection bound can never
 * drift apart — if they could, "config parses but the whole upstream header is
 * silently dropped" is exactly the invisibility DIG-284 exists to remove.
 *
 * 64 characters matches digigraph's `prefixed_tool_name` truncation width, so a
 * name that fits here is one digigraph can prefix unambiguously. 64 entries is
 * the scale of a real MCP tool catalog. `MAX_UPSTREAM_JSON` stays the backstop:
 * an over-budget config fails closed, the same as an over-long `token` does
 * today.
 */
export const MAX_MCP_TOOL_ENTRIES = 64;
export const MAX_MCP_TOOL_NAME_LENGTH = 64;

/**
 * Copy an operator allowlist for the wire, or `undefined` when it must not be
 * forwarded. An out-of-bounds list is dropped whole rather than truncated: a
 * partial allowlist would quietly deny tools the operator asked for while still
 * looking configured, and "drop everything" is the fail-closed answer. Dropped
 * is not the same as empty-on-the-wire — callers omit the key, and once
 * DIG-284 leaf 284.1 lands digigraph treats an absent allowlist as zero tools.
 * Until then digigraph ignores these keys entirely (see ARCHITECTURE.md), so
 * this is the wire contract, not an enforced gate.
 */
function boundedToolAllowlist(value: readonly string[] | undefined): string[] | undefined {
  if (!value || value.length === 0) return undefined;
  if (value.length > MAX_MCP_TOOL_ENTRIES) return undefined;
  if (value.some((name) => typeof name !== "string" || name.length > MAX_MCP_TOOL_NAME_LENGTH)) {
    return undefined;
  }
  return [...value];
}

/** Operator URL wins. Session client URLs only when allowUserServers, https-only. */
export function resolveMcpOAuthResourceUrl(opts: {
  operator: readonly McpServerForward[];
  id: string;
  clientUrl: string;
  allowUserServers: boolean;
}): string {
  const op = opts.operator.find((s) => s.id === opts.id);
  if (op?.url) return op.url;
  if (!opts.allowUserServers) return "";
  const url = opts.clientUrl.trim();
  if (!isHttpsUrl(url) || !isAllowedMcpServerUrl(url)) return "";
  return url;
}

export function operatorMcpServersForUpstream(
  dep: DigichatDeployment | null | undefined,
): McpServerForward[] {
  const out: McpServerForward[] = [];
  const seen = new Set<string>();
  for (const s of dep?.mcp?.servers ?? []) {
    const id = s.id.trim().toLowerCase();
    if (!MCP_ID.test(id) || seen.has(id)) continue;
    if (!isAllowedMcpServerUrl(s.url)) continue;
    seen.add(id);
    const row: McpServerForward = { id, url: s.url.trim() };
    const token = s.token?.trim();
    if (token && token.length <= MAX_TOKEN) {
      row.token = token;
      if (s.authHeader?.trim()) row.authHeader = s.authHeader.trim();
    }
    if (s.setup && Object.keys(s.setup).length) row.setup = { ...s.setup };
    // Operator tool allowlists. Re-checked here, not only in zod, exactly like
    // `token` above: the projection is the last place the bound can be enforced
    // before the bytes go on the wire. Over budget ⇒ omitted ⇒ zero tools.
    const allowedTools = boundedToolAllowlist(s.allowedTools);
    if (allowedTools) row.allowedTools = allowedTools;
    const mutatingTools = boundedToolAllowlist(s.mutatingTools);
    if (mutatingTools) row.mutatingTools = mutatingTools;
    out.push(row);
  }
  return out;
}

export function mcpServersHeaderValue(
  dep: DigichatDeployment | null | undefined,
): string | undefined {
  return mcpUpstreamHeaderValue(operatorMcpServersForUpstream(dep));
}

export function parseMcpSessionOverlay(raw: string | null | undefined): McpSessionOverlayItem[] {
  if (!raw?.trim() || raw.length > MAX_OVERLAY_JSON) return [];
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(data)) return [];
  const out: McpSessionOverlayItem[] = [];
  const seen = new Set<string>();
  for (const item of data) {
    if (!item || typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    const id = String(rec.id ?? "")
      .trim()
      .toLowerCase();
    if (!MCP_ID.test(id) || seen.has(id)) continue;
    seen.add(id);
    const row: McpSessionOverlayItem = { id };
    const auth = String(rec.auth ?? "")
      .trim()
      .toLowerCase();
    if (MCP_AUTH.has(auth) && auth !== "none") row.auth = auth;
    const token = String(rec.token ?? "").trim();
    if (token && token.length <= MAX_TOKEN) row.token = token;
    const url = String(rec.url ?? "").trim();
    if (url) row.url = url;
    out.push(row);
  }
  return out;
}

/**
 * Operator URL always wins. Overlay may attach a token to an operator id.
 * Session URLs are added only when allowSessionUrls (mcp.allowUserServers)
 * and must be https (same rule as resolveMcpOAuthResourceUrl). Operator YAML
 * URLs remain server-side and may still be http (e.g. docker DNS).
 */
export function mergeMcpSessionOverlay(opts: {
  operator: readonly McpServerForward[];
  overlay: readonly McpSessionOverlayItem[];
  allowSessionUrls: boolean;
}): McpUpstreamServer[] {
  const out: McpUpstreamServer[] = opts.operator.map((s) => {
    const row: McpUpstreamServer = { id: s.id, url: s.url };
    if (s.token) row.token = s.token;
    if (s.authHeader) row.authHeader = s.authHeader;
    if (s.setup) row.setup = { ...s.setup };
    // Re-bound here too, not just in operatorMcpServersForUpstream: this is
    // the path that trusts its input, so "enforced on every construction
    // path" has to be true of the merge as well as the projection. Inputs are
    // already bounded and the overlay cannot inject, so this is defence in
    // depth rather than a live fix (review #5061 S1).
    const allowed = boundedToolAllowlist(s.allowedTools);
    if (allowed) row.allowedTools = allowed;
    const mutating = boundedToolAllowlist(s.mutatingTools);
    if (mutating) row.mutatingTools = mutating;
    return row;
  });
  const byId = new Map(out.map((s) => [s.id, s]));
  let sessionCount = 0;
  for (const item of opts.overlay) {
    const existing = byId.get(item.id);
    if (existing) {
      if (item.auth === "bearer" || item.auth === "oauth") existing.auth = item.auth;
      if (item.token) existing.token = item.token;
      continue;
    }
    if (!opts.allowSessionUrls) continue;
    const url = (item.url ?? "").trim();
    if (!isHttpsUrl(url) || !isAllowedMcpServerUrl(url)) continue;
    if (sessionCount >= MAX_SESSION_SERVERS) continue;
    sessionCount += 1;
    const row: McpUpstreamServer = { id: item.id, url };
    if (item.auth === "bearer" || item.auth === "oauth") row.auth = item.auth;
    if (item.token) row.token = item.token;
    out.push(row);
    byId.set(item.id, row);
  }
  return out;
}

export function mcpUpstreamHeaderValue(
  servers: readonly McpUpstreamServer[],
): string | undefined {
  if (!servers.length) return undefined;
  const json = JSON.stringify(
    servers.map((s) => {
      const row: Record<string, string | string[] | Record<string, string>> = {
        id: s.id,
        url: s.url,
      };
      if (s.auth) row.auth = s.auth;
      if (s.token) row.token = s.token;
      if (s.authHeader) row.authHeader = s.authHeader;
      if (s.setup && Object.keys(s.setup).length) row.setup = s.setup;
      if (s.allowedTools?.length) row.allowedTools = s.allowedTools;
      if (s.mutatingTools?.length) row.mutatingTools = s.mutatingTools;
      return row;
    }),
  );
  if (json.length > MAX_UPSTREAM_JSON) return undefined;
  return json;
}
