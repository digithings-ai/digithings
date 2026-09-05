/**
 * Embed tenant registry — one env var (DIGICHAT_EMBED_TENANTS, JSON keyed by
 * hostname) drives embed host→tenant resolution, backend routing, gate mode,
 * theme, accent, attribution, and CSP frame-ancestors.
 * Spec: docs/superpowers/specs/2026-07-02-digichat-embed-external-backend-design.md
 *
 * NOTE: `/embed` CSP `frame-ancestors` is set at request time by `src/proxy.ts`
 * (`embedFrameAncestorsCsp()` in security-headers.ts), which re-reads
 * `DIGICHAT_EMBED_HOSTS` / `DIGICHAT_EMBED_TENANTS` from `process.env` on each
 * call. `next.config.ts` only bakes fail-closed `frame-ancestors 'none'` — tenant
 * env need not be present at image build for framing. Registry lookups below are
 * also runtime (lazy cache on first `getEmbedTenantRegistry()`).
 */

import type { ActivityDetail } from "@/lib/chat-activity";

/**
 * digichat Node backends: digigraph (digithings stack) or foundry (client Azure).
 * Optional digigraph corpus fields isolate multi-tenant embeds on one digigraph
 * (e.g. occ.digithings.ai → occ_help + clients/online-compliance-center).
 */
export type EmbedBackendConfig =
  | {
      type: "digigraph";
      /** digisearch index_name forwarded as X-Digi-Corpus-Index */
      digisearchIndex?: string;
      /** digivault path prefix forwarded as X-Digi-Vault-Prefix */
      vaultPathPrefix?: string;
    }
  | { type: "foundry"; projectEndpoint: string; agentName: string };

/**
 * How this tenant expects visitors to pay for LLM spend.
 * - `free_then_byok` — operator free tier until quota → in-chat BYOK (digithings.ai)
 * - `byok_only` — require a user key before send
 * - `backend_only` — no digichat BYOK; foundry/DataTap-style backends own spend
 * - `operator` — operator/backend keys only (no visitor BYOK handoff)
 */
export type EmbedLlmAccess = "free_then_byok" | "byok_only" | "backend_only" | "operator";

const LLM_ACCESS: readonly EmbedLlmAccess[] = [
  "free_then_byok",
  "byok_only",
  "backend_only",
  "operator",
];

export type EmbedTenantConfig = {
  slug: string;
  aliases?: string[];
  backend: EmbedBackendConfig;
  gateMode: "turn_limited" | "ungated" | "trial_form";
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
   * How much of the agent's thinking chain this tenant's visitors see.
   * "off" emits nothing, "labels" emits step labels only, "full" adds the
   * retrieved document titles. Gated server-side, so lower levels never put
   * documents on the wire. Defaults to "labels" — a tenant nobody configured
   * should not stream retrieved titles to anonymous visitors.
   */
  activityDetail: ActivityDetail;
  /** When true, embed shows BYOK/settings. Independent of gateMode. */
  showByok?: boolean;
  /**
   * When true (or unset — see toEmbedClientConfig), the embed shows a
   * language dropdown in the header. Independent of gateMode/showByok.
   * Only an explicit `false` here turns it off for this tenant.
   */
  showLanguageSelector?: boolean;
  /**
   * When true, this tenant may offer opt-in web search (#3420). Default off —
   * corpus-only. User preference is a separate localStorage flag; both must
   * be on before digichat sends X-Digi-Enable-Web-Search.
   */
  webSearch?: boolean;
  /** page = full content chrome inside iframe; embed = compact iframe child. */
  layout?: "page" | "embed";
  /**
   * LLM spend policy for this embed. Independent of gateMode — digithings.ai
   * is `ungated` + `free_then_byok` so free-quota errors still open BYOK.
   */
  llmAccess?: EmbedLlmAccess;
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
  /**
   * Optional server-side quota provider. When set, /api/chat spends one message per request
   * against this endpoint instead of trusting the client-asserted unlock header. Tenants without
   * it keep the in-memory free-turn behaviour unchanged — this must stay opt-in, since digichat
   * serves tenants that have no such service.
   */
  gate?: { consumeUrl: string };
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
    let digisearchIndex: string | undefined;
    let vaultPathPrefix: string | undefined;
    if (backend.digisearchIndex !== undefined) {
      if (typeof backend.digisearchIndex !== "string" || !backend.digisearchIndex.trim()) {
        throw new Error(`${ctx}: digigraph backend.digisearchIndex must be a non-empty string`);
      }
      digisearchIndex = backend.digisearchIndex.trim();
    }
    if (backend.vaultPathPrefix !== undefined) {
      if (typeof backend.vaultPathPrefix !== "string" || !backend.vaultPathPrefix.trim()) {
        throw new Error(`${ctx}: digigraph backend.vaultPathPrefix must be a non-empty string`);
      }
      vaultPathPrefix = backend.vaultPathPrefix.trim().replace(/^\/+|\/+$/g, "");
    }
    backendCfg = {
      type: "digigraph",
      ...(digisearchIndex ? { digisearchIndex } : {}),
      ...(vaultPathPrefix ? { vaultPathPrefix } : {}),
    };
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
    throw new Error(`${ctx}: backend.type must be "digigraph" or "foundry"`);
  }

  if (v.gateMode !== "turn_limited" && v.gateMode !== "ungated" && v.gateMode !== "trial_form") {
    throw new Error(`${ctx}: gateMode must be "turn_limited", "ungated", or "trial_form"`);
  }

  let gate: EmbedTenantConfig["gate"];
  if (v.gate !== undefined) {
    const consumeUrl = (v.gate as { consumeUrl?: unknown } | null)?.consumeUrl;
    if (typeof consumeUrl !== "string" || !consumeUrl.startsWith("https://")) {
      throw new Error(`${ctx}: gate.consumeUrl must be an https URL`);
    }
    gate = { consumeUrl };
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

  if (
    v.activityDetail !== undefined &&
    v.activityDetail !== "off" &&
    v.activityDetail !== "labels" &&
    v.activityDetail !== "full"
  ) {
    throw new Error(`${ctx}: activityDetail must be "off", "labels", or "full"`);
  }

  if (v.showByok !== undefined && typeof v.showByok !== "boolean") {
    throw new Error(`${ctx}: showByok must be a boolean`);
  }
  if (v.showLanguageSelector !== undefined && typeof v.showLanguageSelector !== "boolean") {
    throw new Error(`${ctx}: showLanguageSelector must be a boolean`);
  }
  if (v.webSearch !== undefined && typeof v.webSearch !== "boolean") {
    throw new Error(`${ctx}: webSearch must be a boolean`);
  }
  if (v.layout !== undefined && v.layout !== "page" && v.layout !== "embed") {
    throw new Error(`${ctx}: layout must be "page" or "embed"`);
  }
  if (v.llmAccess !== undefined) {
    if (typeof v.llmAccess !== "string" || !LLM_ACCESS.includes(v.llmAccess as EmbedLlmAccess)) {
      throw new Error(
        `${ctx}: llmAccess must be "free_then_byok", "byok_only", "backend_only", or "operator"`,
      );
    }
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
    activityDetail: (v.activityDetail as ActivityDetail | undefined) ?? "labels",
    showByok: typeof v.showByok === "boolean" ? v.showByok : undefined,
    showLanguageSelector:
      typeof v.showLanguageSelector === "boolean" ? v.showLanguageSelector : undefined,
    webSearch: typeof v.webSearch === "boolean" ? v.webSearch : undefined,
    layout: v.layout === "page" || v.layout === "embed" ? v.layout : undefined,
    llmAccess: LLM_ACCESS.includes(v.llmAccess as EmbedLlmAccess)
      ? (v.llmAccess as EmbedLlmAccess)
      : undefined,
    gate,
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
