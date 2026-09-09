/**
 * Load digichat deployment config: file + env secret overlay + DIGICHAT_EMBED_TENANTS compat.
 *
 * Canonical path: DIGICHAT_CONFIG_PATH → /app/config/digichat.yaml
 * Fail closed on invalid file / invalid tenants JSON.
 *
 * Server-only — never import from client components (use `@/lib/deploy-config`
 * for schema / client projection / force-tool helpers). Not re-exported from
 * `index.ts` so the client bundle cannot pull `node:fs`.
 */

import { readFileSync, existsSync } from "node:fs";
import { load as loadYaml } from "js-yaml";
// js-yaml v4 — default safe schema via load() with no schema override.
import {
  parseDigichatConfig,
  parseWelcomeCopy,
  welcomeTitle,
  type DigichatConfig,
  type DigichatDeployment,
} from "./schema";
import { parseEmbedTenants, type EmbedTenantConfig } from "@/lib/embed-tenants";
import {
  isThreadSkin,
  defaultThreadSkinForTenant,
  threadSkinChoices,
} from "@/lib/thread-skins";
import { DEFAULT_LANGUAGE_CODE } from "@/lib/languages";

export const DEFAULT_CONFIG_PATH = "/app/config/digichat.yaml";

function resolveConfigPath(
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): string {
  const raw = env.DIGICHAT_CONFIG_PATH?.trim();
  return raw || DEFAULT_CONFIG_PATH;
}

function parseYamlOrJson(raw: string, ctx: string): unknown {
  const trimmed = raw.trim();
  if (!trimmed) throw new Error(`${ctx}: empty file`);
  if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
    try {
      return JSON.parse(trimmed);
    } catch (e) {
      throw new Error(`${ctx}: invalid JSON: ${(e as Error).message}`);
    }
  }
  try {
    return loadYaml(trimmed);
  } catch (e) {
    throw new Error(`${ctx}: invalid YAML: ${(e as Error).message}`);
  }
}

/** Map legacy EmbedTenantConfig → DigichatDeployment (compat hydrate). */
export function embedTenantToDeployment(cfg: EmbedTenantConfig): DigichatDeployment {
  const catalog: NonNullable<DigichatDeployment["tools"]>["catalog"] = [];
  if (cfg.webSearch === true) {
    catalog.push({ id: "web_search", default: false, label: "Web search" });
  }
  catalog.push(
    { id: "digisearch", default: true, label: "Search corpus" },
    { id: "digivault", default: true, label: "Vault" },
  );

  const chromeMode =
    cfg.layout === "page" ? ("app" as const) : ("embed" as const);

  return {
    slug: cfg.slug,
    aliases: cfg.aliases,
    chrome: {
      mode: chromeMode,
      theme: cfg.theme,
      skin: cfg.skin ?? defaultThreadSkinForTenant({ slug: cfg.slug, aliases: cfg.aliases }),
      title: cfg.title,
      welcome: parseWelcomeCopy(cfg.welcome),
      suggestions: cfg.suggestions,
      placeholder: cfg.placeholder,
      accent: cfg.accent,
      attribution: cfg.attribution,
      defaultLanguage: DEFAULT_LANGUAGE_CODE,
      transcript: { userAlign: "right" },
    },
    persistence: "none",
    auth: "anonymous",
    features: {
      attachments: false,
      dictation: false,
      speech: false,
      reasoning: "collapsed",
      toolCalls: "collapsed",
      sources: true,
      modelPicker: false,
      branchPicker: true,
    },
    models: { available: [] },
    cli: { enabled: false },
    backend: cfg.backend,
    tools: { allowUserToggle: true, catalog },
    mcp: {
      servers: cfg.mcp?.servers ?? [],
      allowUserServers: cfg.mcp?.allowUserServers ?? false,
      allowAddForm: cfg.mcp?.allowAddForm ?? false,
    },
    gate: {
      mode: cfg.gateMode,
      activityDetail: cfg.activityDetail,
      llmAccess: cfg.llmAccess,
      consumeUrl: cfg.gate?.consumeUrl,
      lockedContact: cfg.lockedContact,
      showByok: cfg.showByok,
      showLanguageSelector: cfg.showLanguageSelector,
      webSearch: cfg.webSearch,
      requiredPlanTier: cfg.requiredPlanTier,
    },
    token: cfg.token,
  };
}

/** Reverse: DigichatDeployment → EmbedTenantConfig for existing BFF paths. */
export function deploymentToEmbedTenant(dep: DigichatDeployment): EmbedTenantConfig {
  return {
    slug: dep.slug,
    aliases: dep.aliases,
    backend: dep.backend,
    gateMode: dep.gate.mode,
    theme: dep.chrome.theme,
    skin: dep.chrome.skin,
    accent: dep.chrome.accent,
    attribution: dep.chrome.attribution === true,
    title: dep.chrome.title,
    welcome: welcomeTitle(dep.chrome.welcome),
    suggestions: dep.chrome.suggestions,
    placeholder: dep.chrome.placeholder,
    lockedContact: dep.gate.lockedContact,
    activityDetail: dep.gate.activityDetail,
    showByok: dep.gate.showByok,
    showLanguageSelector: dep.gate.showLanguageSelector,
    webSearch:
      dep.gate.webSearch === true ||
      dep.tools?.catalog?.some((t) => t.id === "web_search") === true,
    layout: dep.chrome.mode === "app" || dep.chrome.mode === "sidebar" ? "page" : "embed",
    llmAccess: dep.gate.llmAccess,
    token: dep.token ?? "",
    tools: dep.tools,
    mcp: dep.mcp,
    models: dep.models,
    ...(dep.gate.requiredPlanTier
      ? { requiredPlanTier: dep.gate.requiredPlanTier }
      : {}),
    ...(dep.gate.consumeUrl ? { gate: { consumeUrl: dep.gate.consumeUrl } } : {}),
  };
}

function applyEnvOverlay(
  config: DigichatConfig,
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
): DigichatConfig {
  const next: DigichatConfig = {
    version: 1,
    deployment: config.deployment ? structuredClone(config.deployment) : undefined,
    hosts: config.hosts ? structuredClone(config.hosts) : undefined,
  };

  const token = env.DIGICHAT_EMBED_TOKEN?.trim();
  if (token && next.deployment && !next.deployment.token) {
    next.deployment.token = token;
  }

  const skinRaw = env.DIGICHAT_CHROME_SKIN?.trim().toLowerCase();
  if (skinRaw) {
    if (!isThreadSkin(skinRaw)) {
      throw new Error(
        `DIGICHAT_CHROME_SKIN must be one of ${threadSkinChoices()} (got ${env.DIGICHAT_CHROME_SKIN})`,
      );
    }
    const applySkin = (dep: DigichatDeployment): DigichatDeployment => ({
      ...dep,
      chrome: { ...dep.chrome, skin: skinRaw },
    });
    if (next.deployment) {
      next.deployment = applySkin(next.deployment);
    }
    if (next.hosts) {
      for (const [hostKey, dep] of Object.entries(next.hosts)) {
        next.hosts[hostKey] = applySkin(dep);
      }
    }
  }

  // Optional: DIGICHAT_HOST_<SLUG>_TOKEN overlays matching host entry tokens.
  if (next.hosts) {
    for (const [hostKey, dep] of Object.entries(next.hosts)) {
      const slugEnv = env[`DIGICHAT_HOST_${dep.slug.toUpperCase().replace(/-/g, "_")}_TOKEN`]?.trim();
      if (slugEnv && !dep.token) {
        next.hosts[hostKey] = { ...dep, token: slugEnv };
      }
    }
  }

  return next;
}

function mergeEmbedTenantsOverlay(
  config: DigichatConfig | null,
  tenantsRaw: string | undefined,
): DigichatConfig {
  const registry = parseEmbedTenants(tenantsRaw);
  if (registry.size === 0) {
    if (config) return config;
    throw new Error("digichat config: no file and no DIGICHAT_EMBED_TENANTS");
  }

  const hosts: Record<string, DigichatDeployment> = {
    ...(config?.hosts ? structuredClone(config.hosts) : {}),
  };

  // Registry is host → config. New hosts hydrate fully. Existing YAML hosts
  // keep chrome, but copy `requiredPlanTier` when YAML omitted it so a baked
  // example file cannot drop the live DIGICHAT_EMBED_TENANTS Desk+ gate (#3662).
  for (const [host, cfg] of registry) {
    if (!hosts[host]) {
      hosts[host] = embedTenantToDeployment(cfg);
      continue;
    }
    if (cfg.requiredPlanTier && !hosts[host].gate.requiredPlanTier) {
      hosts[host] = {
        ...hosts[host],
        gate: { ...hosts[host].gate, requiredPlanTier: cfg.requiredPlanTier },
      };
    }
  }

  return parseDigichatConfig(
    {
      version: 1,
      ...(config?.deployment ? { deployment: config.deployment } : {}),
      hosts,
    },
    "digichat config (tenants merge)",
  );
}

export type LoadDigichatConfigOptions = {
  env?: NodeJS.ProcessEnv | Record<string, string | undefined>;
  /** Inject file contents in tests (skip fs). */
  fileContents?: string | null;
  /** When true, missing file is OK if tenants env supplies hosts. */
  allowMissingFile?: boolean;
};

/**
 * Load + validate config. Throws on invalid content (fail closed).
 * Missing file is OK when allowMissingFile (default) and tenants/env provide shape.
 */
export function loadDigichatConfig(opts: LoadDigichatConfigOptions = {}): DigichatConfig {
  const env = opts.env ?? process.env;
  const path = resolveConfigPath(env);
  const allowMissing = opts.allowMissingFile !== false;

  let fromFile: DigichatConfig | null = null;
  const contents =
    opts.fileContents !== undefined
      ? opts.fileContents
      : existsSync(path)
        ? readFileSync(path, "utf8")
        : null;

  if (contents != null && contents.trim()) {
    const parsed = parseYamlOrJson(contents, path);
    fromFile = parseDigichatConfig(parsed, path);
  } else if (contents != null && !contents.trim()) {
    throw new Error(`${path}: empty file`);
  } else if (!allowMissing && opts.fileContents === undefined && !existsSync(path)) {
    throw new Error(`${path}: file not found`);
  }

  const tenantsRaw = env.DIGICHAT_EMBED_TENANTS;
  let merged: DigichatConfig;
  if (tenantsRaw?.trim()) {
    merged = mergeEmbedTenantsOverlay(fromFile, tenantsRaw);
  } else if (fromFile) {
    merged = fromFile;
  } else {
    // Dev default: single anonymous embed deployment (digigraph), no token.
    merged = parseDigichatConfig(
      {
        version: 1,
        deployment: {
          slug: "local",
          chrome: { mode: "embed", theme: "light" },
          persistence: "none",
          auth: "anonymous",
          backend: { type: "digigraph" },
          gate: { mode: "ungated", activityDetail: "labels" },
        },
      },
      "digichat config (dev default)",
    );
  }

  return applyEnvOverlay(merged, env);
}

let cached: DigichatConfig | null = null;
let loadError: Error | null = null;

/** Process-wide singleton. Fail closed: first load error sticks until reset. */
export function getDigichatConfig(): DigichatConfig {
  if (loadError) throw loadError;
  if (!cached) {
    try {
      cached = loadDigichatConfig();
    } catch (e) {
      loadError = e instanceof Error ? e : new Error(String(e));
      throw loadError;
    }
  }
  return cached;
}

/** Eager validate at startup; logs and rethrows so Next.js fails closed. */
export function initDigichatConfigAtStartup(): DigichatConfig {
  const cfg = getDigichatConfig();
  const hostCount = cfg.hosts ? Object.keys(cfg.hosts).length : 0;
  console.log(
    `[digichat-config] loaded version=${cfg.version} deployment=${cfg.deployment?.slug ?? "(none)"} hosts=${hostCount}`,
  );
  return cfg;
}

export function resetDigichatConfigForTests(): void {
  cached = null;
  loadError = null;
}

/** Test hook — inject a parsed config without touching disk. */
export function setDigichatConfigForTests(cfg: DigichatConfig | null): void {
  cached = cfg;
  loadError = null;
}

/**
 * True when this process is a single-install client container (YAML `deployment`
 * or DIGICHAT_CHROME_SKIN overlay), not the synthetic no-file dev default.
 * Hosts-only multi-tenant configs stay on DIGICHAT_EMBED_TENANTS.
 */
export function isExplicitClientInstall(
  config: DigichatConfig = getDigichatConfig(),
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): boolean {
  if (!config.deployment || config.deployment.auth === "session") return false;
  if (env.DIGICHAT_CHROME_SKIN?.trim()) return true;
  return existsSync(resolveConfigPath(env));
}

/**
 * Anonymous product install for `/embed` + `POST /api/chat`.
 * Only the YAML `deployment` block (never hosts[0]) — a multi-tenant container
 * must not leak the first host to unknown parents.
 */
export function getAnonymousClientInstall(
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): DigichatDeployment | null {
  try {
    const cfg = getDigichatConfig();
    if (!isExplicitClientInstall(cfg, env)) return null;
    return cfg.deployment ?? null;
  } catch {
    return null;
  }
}

function normalizeConfigHost(hostOrOrigin: string): string | null {
  let host = hostOrOrigin.trim().toLowerCase();
  try {
    if (host.includes("://")) host = new URL(host).hostname;
    else host = host.split("/")[0].split(":")[0];
  } catch {
    return null;
  }
  host = host.replace(/\.$/, "");
  return host || null;
}

/**
 * Match a `hosts` entry (YAML + DIGICHAT_EMBED_TENANTS merge). Does **not**
 * fall back to `deployment` — unknown parents must not inherit the first host.
 */
export function matchHostDeployment(
  hostOrOrigin: string | null | undefined,
  config: DigichatConfig = getDigichatConfig(),
): DigichatDeployment | null {
  if (!hostOrOrigin?.trim() || !config.hosts) return null;
  const host = normalizeConfigHost(hostOrOrigin);
  if (!host) return null;
  if (config.hosts[host]) return config.hosts[host];
  for (const [key, dep] of Object.entries(config.hosts)) {
    const keyHost = normalizeConfigHost(key) ?? key.split(":")[0];
    if (keyHost === host) return dep;
    if (dep.aliases?.some((a) => a.toLowerCase() === host || a.toLowerCase().includes(host))) {
      return dep;
    }
  }
  return null;
}

export function resolveDeploymentForHost(
  hostOrOrigin: string | null | undefined,
  config: DigichatConfig = getDigichatConfig(),
): DigichatDeployment | null {
  if (!hostOrOrigin?.trim()) {
    return config.deployment ?? null;
  }
  return matchHostDeployment(hostOrOrigin, config) ?? config.deployment ?? null;
}

/** Default / single-install deployment (no host). */
export function getPrimaryDeployment(
  config: DigichatConfig = getDigichatConfig(),
): DigichatDeployment | null {
  if (config.deployment) return config.deployment;
  const hosts = config.hosts ? Object.values(config.hosts) : [];
  return hosts[0] ?? null;
}
