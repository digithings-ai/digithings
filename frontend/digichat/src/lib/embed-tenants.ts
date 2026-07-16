/**
 * Embed tenant registry — one env var (DIGICHAT_EMBED_TENANTS, JSON keyed by
 * hostname) drives embed host→tenant resolution, backend routing, gate mode,
 * theme, accent, attribution, and CSP frame-ancestors.
 * Spec: docs/superpowers/specs/2026-07-02-digichat-embed-external-backend-design.md
 *
 * NOTE: security-headers.ts imports this at next.config.ts evaluation time,
 * so the env var must be present AT BUILD as well as at runtime.
 */

export type EmbedBackendConfig =
  | { type: "digigraph" }
  | { type: "external-relay"; url: string }
  | { type: "foundry"; projectEndpoint: string; agentName: string };

export type EmbedTenantConfig = {
  slug: string;
  aliases?: string[];
  backend: EmbedBackendConfig;
  gateMode: "turn_limited" | "ungated";
  theme: "dark" | "light";
  accent?: { color: string; foreground: string };
  attribution: boolean;
  /** Branded embed header title (e.g. "Chat for Help"). */
  title?: string;
  /** Default welcome intro when the iframe URL has no ?welcome= */
  welcome?: string;
  /** Default suggestion chips (URL ?suggestions= wins). */
  suggestions?: string[];
  /** Default input placeholder (URL ?placeholder= wins). */
  placeholder?: string;
  /**
   * Contact email shown when the free-turn gate locks (turn_limited tenants).
   * When set, the paywall becomes a "contact us" message with a mailto link
   * instead of the default bring-your-own-key prompt — for tenants who'd
   * rather route capped visitors to sales than offer BYOK.
   */
  lockedContact?: string;
  /**
   * Per-tenant secret. Knowing a tenant's host string is public (it's the
   * tenant's own domain) so registry membership alone must never grant
   * embed access — callers must also present this value as X-Embed-Token.
   * Provisioned out-of-band and baked into the tenant's own embed snippet
   * (e.g. `<iframe src=".../embed?token=...">`), analogous to a Stripe
   * publishable key: not secret from that tenant's own visitors, but not
   * guessable by an unrelated caller either.
   */
  token: string;
};

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;
const SLUG = /^[a-z0-9][a-z0-9-]*$/;

export function normalizeEmbedHost(input: string | null | undefined): string | null {
  if (!input) return null;
  const raw = input.trim().toLowerCase();
  if (!raw) return null;
  // Only trust URL parsing when a real scheme separator is present:
  // new URL("localhost:8080") parses "localhost:" as a SCHEME (empty hostname).
  if (raw.includes("://")) {
    try {
      return new URL(raw).hostname.replace(/\.$/, "") || null;
    } catch {
      return null;
    }
  }
  const host = raw.split("/")[0].split(":")[0].replace(/\.$/, "");
  return host || null;
}

function validateEntry(hostKey: string, value: unknown): EmbedTenantConfig {
  const ctx = `DIGICHAT_EMBED_TENANTS["${hostKey}"]`;
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${ctx}: entry must be an object`);
  }
  const v = value as Record<string, unknown>;

  if (typeof v.slug !== "string" || !SLUG.test(v.slug)) {
    throw new Error(`${ctx}: "slug" must be lowercase alphanumeric/hyphens`);
  }

  const backend = v.backend as Record<string, unknown> | undefined;
  let backendCfg: EmbedBackendConfig;
  if (backend?.type === "digigraph") {
    backendCfg = { type: "digigraph" };
  } else if (backend?.type === "external-relay") {
    if (typeof backend.url !== "string") {
      throw new Error(`${ctx}: external-relay backend requires a "url"`);
    }
    let parsed: URL;
    try {
      parsed = new URL(backend.url);
    } catch {
      throw new Error(`${ctx}: backend.url is not a valid URL`);
    }
    if (parsed.protocol !== "https:") {
      throw new Error(`${ctx}: backend.url must be https`);
    }
    backendCfg = { type: "external-relay", url: backend.url };
  } else if (backend?.type === "foundry") {
    if (typeof backend.projectEndpoint !== "string" || !backend.projectEndpoint.trim()) {
      throw new Error(`${ctx}: foundry backend requires a "projectEndpoint"`);
    }
    let parsed: URL;
    try {
      parsed = new URL(backend.projectEndpoint);
    } catch {
      throw new Error(`${ctx}: backend.projectEndpoint is not a valid URL`);
    }
    if (parsed.protocol !== "https:") {
      throw new Error(`${ctx}: backend.projectEndpoint must be https`);
    }
    if (typeof backend.agentName !== "string" || !backend.agentName.trim()) {
      throw new Error(`${ctx}: foundry backend requires an "agentName"`);
    }
    backendCfg = { type: "foundry", projectEndpoint: backend.projectEndpoint, agentName: backend.agentName };
  } else {
    throw new Error(`${ctx}: backend.type must be "digigraph", "external-relay", or "foundry"`);
  }

  if (v.gateMode !== "turn_limited" && v.gateMode !== "ungated") {
    throw new Error(`${ctx}: gateMode must be "turn_limited" or "ungated"`);
  }

  if (v.theme !== undefined && v.theme !== "dark" && v.theme !== "light") {
    throw new Error(`${ctx}: theme must be "dark" or "light"`);
  }

  let accent: EmbedTenantConfig["accent"];
  if (v.accent !== undefined) {
    const a = v.accent as Record<string, unknown> | null;
    if (
      typeof a?.color !== "string" ||
      !HEX_COLOR.test(a.color) ||
      typeof a?.foreground !== "string" ||
      !HEX_COLOR.test(a.foreground)
    ) {
      throw new Error(`${ctx}: accent.color / accent.foreground must be #rrggbb hex`);
    }
    accent = { color: a.color, foreground: a.foreground };
  }

  if (v.aliases !== undefined && (!Array.isArray(v.aliases) || v.aliases.some((x) => typeof x !== "string"))) {
    throw new Error(`${ctx}: aliases must be an array of strings`);
  }

  if (typeof v.token !== "string" || !v.token.trim()) {
    throw new Error(`${ctx}: "token" must be a non-empty string`);
  }

  let suggestions: string[] | undefined;
  if (v.suggestions !== undefined) {
    if (!Array.isArray(v.suggestions) || v.suggestions.some((x) => typeof x !== "string")) {
      throw new Error(`${ctx}: suggestions must be an array of strings`);
    }
    suggestions = (v.suggestions as string[]).map((s) => s.trim()).filter(Boolean);
  }

  if (v.title !== undefined && typeof v.title !== "string") {
    throw new Error(`${ctx}: title must be a string`);
  }
  if (v.welcome !== undefined && typeof v.welcome !== "string") {
    throw new Error(`${ctx}: welcome must be a string`);
  }
  if (v.placeholder !== undefined && typeof v.placeholder !== "string") {
    throw new Error(`${ctx}: placeholder must be a string`);
  }
  if (v.lockedContact !== undefined && typeof v.lockedContact !== "string") {
    throw new Error(`${ctx}: lockedContact must be a string`);
  }

  return {
    slug: v.slug,
    aliases: v.aliases as string[] | undefined,
    backend: backendCfg,
    gateMode: v.gateMode,
    theme: (v.theme as "dark" | "light" | undefined) ?? "dark",
    accent,
    attribution: v.attribution === true,
    token: v.token,
    title: typeof v.title === "string" ? v.title : undefined,
    welcome: typeof v.welcome === "string" ? v.welcome : undefined,
    suggestions,
    placeholder: typeof v.placeholder === "string" ? v.placeholder : undefined,
    lockedContact: typeof v.lockedContact === "string" ? v.lockedContact : undefined,
  };
}

export function parseEmbedTenants(raw: string | undefined): Map<string, EmbedTenantConfig> {
  const registry = new Map<string, EmbedTenantConfig>();
  if (!raw || !raw.trim()) return registry;

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (e) {
    throw new Error(`DIGICHAT_EMBED_TENANTS is not valid JSON: ${(e as Error).message}`);
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("DIGICHAT_EMBED_TENANTS must be a JSON object keyed by hostname");
  }

  for (const [hostKey, value] of Object.entries(parsed as Record<string, unknown>)) {
    const cfg = validateEntry(hostKey, value);
    const hosts = [hostKey, ...(cfg.aliases ?? [])];
    for (const candidate of hosts) {
      const host = normalizeEmbedHost(candidate);
      if (!host) throw new Error(`DIGICHAT_EMBED_TENANTS["${hostKey}"]: invalid host/alias "${candidate}"`);
      if (registry.has(host)) throw new Error(`DIGICHAT_EMBED_TENANTS: duplicate host/alias "${host}"`);
      registry.set(host, cfg);
    }
  }
  return registry;
}

let cachedRegistry: Map<string, EmbedTenantConfig> | null = null;

export function getEmbedTenantRegistry(): Map<string, EmbedTenantConfig> {
  if (!cachedRegistry) {
    cachedRegistry = parseEmbedTenants(process.env.DIGICHAT_EMBED_TENANTS);
    if (cachedRegistry.size > 0) {
      console.log(
        `[embed-tenants] loaded ${cachedRegistry.size} host mapping(s): ${[...cachedRegistry.keys()].join(", ")}`
      );
    }
  }
  return cachedRegistry;
}

/** Test hook — clears the module-level cache so stubbed envs take effect. */
export function resetEmbedTenantRegistryForTests(): void {
  cachedRegistry = null;
}

export function resolveEmbedTenantByHost(
  hostOrOrigin: string | null | undefined
): EmbedTenantConfig | null {
  const host = normalizeEmbedHost(hostOrOrigin);
  if (!host) return null;
  return getEmbedTenantRegistry().get(host) ?? null;
}
