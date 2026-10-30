/**
 * Load digichat deployment config: env document + file + env secret overlay +
 * DIGICHAT_EMBED_TENANTS compat.
 *
 * Document precedence: `DIGICHAT_CONFIG_YAML` > `DIGICHAT_CONFIG_PATH` file
 * (default `/app/config/digichat.yaml`) > house `defaults.yaml`.
 *
 * `DIGICHAT_CONFIG_YAML` is the deployment document itself, forwarded by the
 * Cloudflare Worker from the `config-yaml` key of `DIGICHAT_TENANTS_KV` so
 * config lives outside both the image and the Worker and can be edited without
 * a redeploy. It holds no secret values: credentials stay named env refs
 * (`tokenEnv`) resolved from the process environment. A set but blank value
 * counts as absent, so the file is still read. `DIGICHAT_EMBED_TENANTS` is
 * merged over whichever document won, exactly as before.
 *
 * Fail closed on invalid document / invalid tenants JSON.
 *
 * Server-only — never import from client components (use `@/lib/deploy-config`
 * for schema / client projection / force-tool helpers). Not re-exported from
 * `index.ts` so the client bundle cannot pull `node:fs`.
 */

import { readFileSync, existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { load as loadYaml } from "js-yaml";
import { expandExtendsDocument } from "./extends-merge";
import { DEFAULT_PREMIUM_WINDOW_SECONDS } from "@/lib/premium-budget/budget";
// js-yaml v4 — default safe schema via load() with no schema override.
import {
  parseDigichatConfig,
  parseWelcomeCopy,
  welcomeBodyLines,
  welcomeTitle,
  type DigichatConfig,
  type DigichatDeployment,
} from "./schema";
import { BASELINE_EMBED_WELCOME } from "@/lib/baseline-embed";
import { FIRST_PARTY_EMBED_HOSTS } from "@/lib/embed-first-party";
import { parseEmbedTenants, type EmbedTenantConfig } from "@/lib/embed-tenants";
import { DEFAULT_THINKING_MODE, DEFAULT_VIEW_MODE } from "@/lib/view-modes";
import {
  isThreadSkin,
  defaultThreadSkinForTenant,
  threadSkinChoices,
} from "@digithings/ui/chat/skins";
import { DEFAULT_LANGUAGE_CODE } from "@/lib/languages";

export const DEFAULT_CONFIG_PATH = "/app/config/digichat.yaml";

/**
 * Env var carrying the deployment document itself (YAML or JSON text),
 * forwarded from the Worker's KV `config-yaml` key. Non-secret by design.
 */
export const CONFIG_YAML_ENV = "DIGICHAT_CONFIG_YAML";

/**
 * How long a loaded document is reused before it is re-read.
 *
 * Deployment config is changed in KV without a redeploy: the Worker re-reads
 * KV on every Container boot (its Durable Object re-arms on `onStop`), and
 * this bound stops a long-lived process from serving a document forever. A
 * few seconds is the staleness ceiling; re-parsing one small document that
 * often is cheap, so this is a freshness choice rather than a CPU trade-off.
 */
export const CONFIG_CACHE_TTL_MS = 5_000;

const MODULE_DIR = dirname(fileURLToPath(import.meta.url));

/** Checked-in house document. A missing DIGICHAT_CONFIG_PATH loads this. */
export function defaultsYamlCandidates(): string[] {
  return [
    resolve(MODULE_DIR, "../../../config/defaults.yaml"),
    resolve(process.cwd(), "config", "defaults.yaml"),
    resolve(process.cwd(), "apps", "digichat", "config", "defaults.yaml"),
    "/app/config/defaults.yaml",
  ];
}

function digichatConfigDir(): string {
  const hit = defaultsYamlCandidates().find((path) => existsSync(path));
  if (!hit) {
    throw new Error(
      `digichat defaults.yaml not found (looked in ${defaultsYamlCandidates().join(", ")})`,
    );
  }
  return dirname(hit);
}

function readExtendsName(name: string): unknown {
  const file = name.endsWith(".yaml") || name.endsWith(".yml") ? name : `${name}.yaml`;
  const path = resolve(digichatConfigDir(), file);
  if (!existsSync(path)) throw new Error(`extends: ${name} not found at ${path}`);
  return parseYamlOrJson(readFileSync(path, "utf8"), path);
}

/** Expand `extends` before schema parse. No-op when the document does not extend. */
export function expandDigichatDocument(input: unknown): unknown {
  return expandExtendsDocument(input, readExtendsName);
}

export function materializeDigichatConfig(
  input: unknown,
  ctx = "digichat config",
  opts?: { openRouterConfigured?: boolean },
): DigichatConfig {
  return parseDigichatConfig(expandDigichatDocument(input), ctx, opts);
}

function loadDefaultsDocument(
  ctx: string,
  opts?: { openRouterConfigured?: boolean },
): DigichatConfig {
  const path = defaultsYamlCandidates().find((candidate) => existsSync(candidate));
  if (!path) {
    throw new Error(`${ctx}: defaults.yaml not found`);
  }
  return materializeDigichatConfig(parseYamlOrJson(readFileSync(path, "utf8"), path), path, opts);
}

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
  const catalog: NonNullable<DigichatDeployment["tools"]>["catalog"] = [
    ...(cfg.tools?.catalog ?? []),
  ];
  if (cfg.webSearch === true && !catalog.some((t) => t.id === "web_search")) {
    catalog.push({ id: "web_search", default: true, label: "Web search" });
  }

  const chromeMode =
    cfg.layout === "page" ? ("app" as const) : ("embed" as const);

  const welcome = parseWelcomeCopy(
    cfg.welcomeBody?.length
      ? { title: cfg.welcome?.trim() || BASELINE_EMBED_WELCOME, body: cfg.welcomeBody }
      : cfg.welcome,
  );

  return {
    slug: cfg.slug,
    aliases: cfg.aliases,
    chrome: {
      mode: chromeMode,
      theme: cfg.theme,
      skin: cfg.skin ?? defaultThreadSkinForTenant({ slug: cfg.slug, aliases: cfg.aliases }),
      title: cfg.title,
      welcome,
      suggestions: cfg.suggestions,
      ...(cfg.chatSlug ? { slug: cfg.chatSlug } : {}),
      ...(typeof cfg.productChat === "boolean" ? { productChat: cfg.productChat } : {}),
      placeholder: cfg.placeholder,
      accent: cfg.accent,
      ...(cfg.fonts ? { fonts: cfg.fonts } : {}),
      attribution: cfg.attribution,
      defaultLanguage: cfg.defaultLanguage ?? DEFAULT_LANGUAGE_CODE,
      toolbar: cfg.toolbar !== false,
      scrollbars: cfg.scrollbars ?? "always",
      loading: "banner",
      scroll: cfg.scroll ?? { mode: "follow" },
      transcript: { userAlign: "right" },
    },
    persistence: "none",
    // A registry tenant with a token is reachable only with that token, so it
    // is never an anonymous deployment (DIG-3585): `resolveAnonymousDeploymentChat`
    // refuses it and the chrome route asks for the token.
    auth: cfg.token?.trim() ? "session" : "anonymous",
    features: {
      attachments: cfg.attachments === true,
      // Feature parity (#4532): carry the tenant's flags instead of dropping
      // them. The off-by-default pair is explicit-true-only; the on-by-default
      // pair honours an explicit false — the same asymmetry as the projection.
      dictation: cfg.dictation === true,
      speech: cfg.speech === true,
      view: cfg.view ?? DEFAULT_VIEW_MODE,
      thinking: cfg.thinking ?? DEFAULT_THINKING_MODE,
      density: cfg.density ?? "default",
      effort: cfg.effort ?? "medium",
      sources: cfg.sources !== false,
      modelPicker: false,
      branchPicker: cfg.branchPicker !== false,
      pageContext: cfg.pageContext ?? "visible",
      // Private mode is opt-in per tenant: absent means the tenant never
      // offers it, so the embed cannot enter it from the URL or `/private`.
      privateMode: cfg.privateMode === true,
    },
    models: {
      ...(cfg.models?.default ? { default: cfg.models.default } : {}),
      available: [...(cfg.models?.available ?? [])],
      ...(typeof cfg.models?.allowPicker === "boolean"
        ? { allowPicker: cfg.models.allowPicker }
        : {}),
      ...(cfg.models?.catalog === true ? { catalog: true as const } : {}),
      ...(typeof cfg.models?.occPicker === "boolean" ? { occPicker: cfg.models.occPicker } : {}),
      ...(typeof cfg.models?.premiumMeter === "boolean"
        ? { premiumMeter: cfg.models.premiumMeter }
        : {}),
      ...(typeof cfg.models?.priceCapUsdPerMillion === "number"
        ? { priceCapUsdPerMillion: cfg.models.priceCapUsdPerMillion }
        : {}),
      ...(typeof cfg.models?.premiumCapUsdPerMillion === "number"
        ? { premiumCapUsdPerMillion: cfg.models.premiumCapUsdPerMillion }
        : {}),
      ...(cfg.models?.costPerWindow
        ? {
            costPerWindow: {
              usd: cfg.models.costPerWindow.usd,
              windowSeconds:
                cfg.models.costPerWindow.windowSeconds ?? DEFAULT_PREMIUM_WINDOW_SECONDS,
            },
          }
        : {}),
      ...(cfg.models?.presets ? { presets: [...cfg.models.presets] } : {}),
      ...(typeof cfg.models?.showFullList === "boolean"
        ? { showFullList: cfg.models.showFullList }
        : {}),
      ...(typeof cfg.models?.minContextTokens === "number"
        ? { minContextTokens: cfg.models.minContextTokens }
        : {}),
      // A resolved tenant carries its picker; without it a preset:<id> pick
      // through the fallback deployment would be refused.
      ...(cfg.models?.picker ? { picker: structuredClone(cfg.models.picker) } : {}),
    },
    cli: { enabled: false },
    backend: cfg.backend,
    ...(cfg.guardrails ? { guardrails: cfg.guardrails } : {}),
    ...(cfg.limits ? { limits: cfg.limits } : {}),
    ...(catalog.length || cfg.tools?.exclusive === true
      ? {
          tools: {
            allowUserToggle: cfg.tools?.allowUserToggle ?? true,
            catalog,
            ...(cfg.tools?.exclusive === true ? { exclusive: true } : {}),
          },
        }
      : {}),
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
      ...(typeof cfg.showContextMeter === "boolean"
        ? { showContextMeter: cfg.showContextMeter }
        : {}),
      lockSessionControls: cfg.lockSessionControls,
      webSearch: cfg.webSearch,
      ...(cfg.searchEngine ? { searchEngine: cfg.searchEngine } : {}),
      requiredPlanTier: cfg.requiredPlanTier,
    },
    token: cfg.token,
    ...(cfg.access ? { access: structuredClone(cfg.access) } : {}),
  };
}

/** Reverse: DigichatDeployment → EmbedTenantConfig for existing BFF paths. */
export function deploymentToEmbedTenant(dep: DigichatDeployment): EmbedTenantConfig {
  return {
    slug: dep.slug,
    aliases: dep.aliases,
    backend: dep.backend,
    ...(dep.guardrails ? { guardrails: dep.guardrails } : {}),
    ...(dep.limits ? { limits: dep.limits } : {}),
    gateMode: dep.gate.mode,
    theme: dep.chrome.theme,
    skin: dep.chrome.skin,
    accent: dep.chrome.accent,
    ...(dep.chrome.fonts ? { fonts: dep.chrome.fonts } : {}),
    attribution: dep.chrome.attribution !== false,
    title: dep.chrome.title,
    welcome: welcomeTitle(dep.chrome.welcome),
    welcomeBody: welcomeBodyLines(dep.chrome.welcome),
    suggestions: dep.chrome.suggestions,
    ...(dep.chrome.slug ? { chatSlug: dep.chrome.slug } : {}),
    ...(typeof dep.chrome.productChat === "boolean"
      ? { productChat: dep.chrome.productChat }
      : {}),
    ...(dep.access ? { access: dep.access } : {}),
    placeholder: dep.chrome.placeholder,
    lockedContact: dep.gate.lockedContact,
    activityDetail: dep.gate.activityDetail,
    showByok: dep.gate.showByok,
    showLanguageSelector: dep.gate.showLanguageSelector,
    ...(typeof dep.gate.showContextMeter === "boolean"
      ? { showContextMeter: dep.gate.showContextMeter }
      : {}),
    lockSessionControls: dep.gate.lockSessionControls,
    attachments: dep.features.attachments === true,
    // Feature parity (#4532): the reverse direction must carry the same flags,
    // or the /embed first paint loses what the tenant set. Only non-default
    // values are projected, so a tenant that set nothing keeps the client
    // config it had before.
    dictation: dep.features.dictation === true ? true : undefined,
    speech: dep.features.speech === true ? true : undefined,
    sources: dep.features.sources === false ? false : undefined,
    branchPicker: dep.features.branchPicker === false ? false : undefined,
    privateMode: dep.features.privateMode === true ? true : undefined,
    defaultLanguage:
      dep.chrome.defaultLanguage === DEFAULT_LANGUAGE_CODE
        ? undefined
        : dep.chrome.defaultLanguage,
    pageContext: dep.features.pageContext,
    view: dep.features.view,
    thinking: dep.features.thinking,
    ...(dep.features.density !== "default" ? { density: dep.features.density } : {}),
    ...(dep.features.effort !== "medium" ? { effort: dep.features.effort } : {}),
    ...(dep.chrome.toolbar === false ? { toolbar: false as const } : {}),
    ...(dep.chrome.scrollbars === "auto" ? { scrollbars: "auto" as const } : {}),
    ...(dep.chrome.palette && dep.chrome.palette !== "default"
      ? { palette: dep.chrome.palette }
      : {}),
    ...(dep.gate.searchEngine ? { searchEngine: dep.gate.searchEngine } : {}),
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

  // Resolve `mcp.servers[].tokenEnv` → `.token` (operator-static MCP auth, #3841).
  if (next.deployment) {
    next.deployment = resolveDeploymentTokenEnv(
      resolveMcpServerTokens(next.deployment, env),
      env,
    );
  }
  if (next.hosts) {
    for (const [hostKey, dep] of Object.entries(next.hosts)) {
      next.hosts[hostKey] = resolveDeploymentTokenEnv(resolveMcpServerTokens(dep, env), env);
    }
  }

  return next;
}

/** Fills `token` from `tokenEnv` when the slug env and `token` are both unset. */
function resolveDeploymentTokenEnv(
  dep: DigichatDeployment,
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
): DigichatDeployment {
  if (dep.token || !dep.tokenEnv) return dep;
  const value = env[dep.tokenEnv]?.trim();
  if (!value) return dep;
  return { ...dep, token: value };
}

/** Fills each `mcp.servers[].token` from its `tokenEnv` when `token` is unset (#3841). */
function resolveMcpServerTokens(
  dep: DigichatDeployment,
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
): DigichatDeployment {
  const servers = dep.mcp?.servers;
  if (!servers?.length) return dep;
  let changed = false;
  const next = servers.map((s) => {
    if (s.token || !s.tokenEnv) return s;
    const resolved = env[s.tokenEnv]?.trim();
    if (!resolved) return s;
    changed = true;
    return { ...s, token: resolved };
  });
  return changed ? { ...dep, mcp: { ...dep.mcp!, servers: next } } : dep;
}

function openRouterConfigured(
  env: NodeJS.ProcessEnv | Record<string, string | undefined>,
): boolean {
  const key = env["OPENROUTER_API_KEY"];
  return typeof key === "string" && key.trim().length > 0;
}

/** Drop a resolved catalog so a second parse fills it again instead of refusing the list. */
function unresolveCatalog(dep: DigichatDeployment): DigichatDeployment {
  if (!dep.models?.catalog) return dep;
  const models = { ...dep.models, available: [] };
  delete models.picker;
  return { ...dep, models };
}

/**
 * Merge one registry tenant onto a deployment so that ONE artefact decides
 * both the session lock and the model allowlist (DIG-4589).
 *
 * Rules, each chosen so a merge can never drop a restriction:
 * - `gate.lockSessionControls`: true when EITHER source says true. A lock is
 *   a restriction, so the merge keeps the stricter of the two.
 * - `models.available`: the tenant's curated list when it is non-empty, else
 *   the deployment's list. A parsed tenant list is always an array (possibly
 *   empty), so "non-empty wins" is the only usable rule. The projection in
 *   `embed-bridge.ts` consumes THIS merged artefact, so the list the client
 *   is shown is the list the server enforces.
 * - `models.default` / `models.allowPicker` and every other model field: the
 *   tenant's when it sets one, else the deployment's. The registry's own
 *   models block is spread on top, so the picker, the catalog and the
 *   premium meter still travel to a host that also has a deployment entry.
 * - `models.catalog`: dropped when the tenant curates a list. A catalog
 *   policy and a hand-written list cannot coexist - `applyModelCatalog`
 *   ignores the hand list and pins the tenant's `default` against a catalog
 *   that does not know it, which throws. The tenant's curation is the more
 *   specific statement, so it wins, exactly as it does in
 *   `withProductPickerDefaults`.
 *

 * `gate.requiredPlanTier` is NOT merged here: #3662 keeps its own rule in
 * `mergeEmbedTenantsOverlay` (the registry fills it in only when the
 * deployment omitted it).
 */
function mergeEmbedTenantIntoDeployment(
  dep: DigichatDeployment,
  cfg: EmbedTenantConfig,
): DigichatDeployment {
  // The registry's models block is only meaningful when the tenant has one:
  // `embedTenantToDeployment` always fills `available`, so spreading an
  // absent block would wipe the deployment's own list.
  const fromRegistry = cfg.models ? embedTenantToDeployment(cfg).models : undefined;
  const tenantAvailable = cfg.models?.available ?? [];
  const tenantDefault = cfg.models?.default?.trim() || undefined;
  const tenantAllowPicker = cfg.models?.allowPicker;

  const available =
    tenantAvailable.length > 0
      ? [...tenantAvailable]
      : [...(dep.models?.available ?? [])];
  const defaultModel = tenantDefault ?? dep.models?.default;
  const allowPicker = tenantAllowPicker ?? dep.models?.allowPicker;

  const models: DigichatDeployment["models"] = {
    ...dep.models,
    ...(fromRegistry ?? {}),
    ...(defaultModel ? { default: defaultModel } : {}),
    available,
    ...(allowPicker === undefined ? {} : { allowPicker }),
  };

  // A catalog policy and a hand-written list are mutually exclusive:
  // `applyModelCatalog` warns that the hand list is ignored, lets the
  // catalog win, and pins the tenant's `default` against a catalog that does
  // not know it - which throws and takes the whole config down with it. The
  // tenant's curation is the more specific statement, so when the tenant
  // curates a list the deployment's catalog policy is dropped and the hand
  // list is left alone - the same precedence `withProductPickerDefaults`
  // gives a hand-written list over the product-chat default policy. When the
  // tenant curates nothing the deployment's catalog stays and resolves as
  // before.
  if (tenantAvailable.length > 0 && models.catalog) {
    delete models.catalog;
  }

  // Tenant chrome identity and the server-only access block come from the
  // registry row when it sets them, so a baked file for the same host cannot
  // drop a gate or a chat slug the live row declares.
  const chrome: DigichatDeployment["chrome"] = {
    ...dep.chrome,
    ...(cfg.chatSlug ? { slug: cfg.chatSlug } : {}),
    ...(typeof cfg.productChat === "boolean" ? { productChat: cfg.productChat } : {}),
  };

  return {
    ...dep,
    chrome,
    ...(cfg.access ? { access: structuredClone(cfg.access) } : {}),
    models,
    gate: {
      ...dep.gate,
      lockSessionControls:
        dep.gate.lockSessionControls === true || cfg.lockSessionControls === true
          ? true
          : dep.gate.lockSessionControls,
    },
  };
}

function mergeEmbedTenantsOverlay(
  config: DigichatConfig | null,
  tenantsRaw: string | undefined,
  openRouter: boolean,
): DigichatConfig {
  const registry = parseEmbedTenants(tenantsRaw);
  if (registry.size === 0) {
    if (config) return config;
    throw new Error("digichat config: no file and no DIGICHAT_EMBED_TENANTS");
  }

  const hosts: Record<string, DigichatDeployment> = {
    ...(config?.hosts
      ? Object.fromEntries(
          Object.entries(structuredClone(config.hosts)).map(([host, dep]) => [
            host,
            unresolveCatalog(dep),
          ]),
        )
      : {}),
  };

  // Index the config hosts by NORMALISED host. `matchHostDeployment` looks a
  // host up the same way, so a config key written as an origin
  // (`https://tenant.example.com`) or with a port has to merge with the
  // registry key for the same host. Without this index one host ended up with
  // two entries and the lookup returned the registry-only duplicate, so the
  // deployment's own gate and model list were silently dropped (DIG-4589).
  const configKeyByHost = new Map<string, string>();
  for (const key of Object.keys(hosts)) {
    const normalized = normalizeConfigHost(key);
    if (normalized && !configKeyByHost.has(normalized)) {
      configKeyByHost.set(normalized, key);
    }
  }

  // Registry is host → config. New hosts hydrate fully. Existing YAML hosts
  // keep chrome, but the session lock and the model allowlist are merged so
  // one artefact decides both (DIG-4589). `requiredPlanTier` is still copied
  // when YAML omitted it so a baked example file cannot drop the live
  // DIGICHAT_EMBED_TENANTS Desk+ gate (#3662).
  for (const [host, cfg] of registry) {
    const normalized = normalizeConfigHost(host) ?? host;
    // An exact key match wins: `matchHostDeployment` returns the exact
    // normalised key before it scans the entries.
    const existingKey = hosts[host] ? host : configKeyByHost.get(normalized);
    if (!existingKey) {
      const dep = embedTenantToDeployment(cfg);
      // A first-party house row keeps its anonymous chat: its token is for
      // third-party embeds of the house chat, not an invite (DIG-3585).
      hosts[host] = FIRST_PARTY_EMBED_HOSTS.has(normalized)
        ? { ...dep, auth: "anonymous" }
        : dep;
      configKeyByHost.set(normalized, host);
      continue;
    }
    hosts[existingKey] = mergeEmbedTenantIntoDeployment(hosts[existingKey], cfg);
    // A YAML row for a non-first-party host that the registry gives a token is
    // a token tenant: it is never anonymous, whatever the YAML row defaulted
    // to (DIG-3585). A first-party house row keeps the YAML's own `auth`.
    if (
      cfg.token?.trim() &&
      !FIRST_PARTY_EMBED_HOSTS.has(normalized) &&
      hosts[existingKey].auth === "anonymous"
    ) {
      hosts[existingKey] = { ...hosts[existingKey], auth: "session" };
    }
    if (cfg.requiredPlanTier && !hosts[existingKey].gate.requiredPlanTier) {
      hosts[existingKey] = {
        ...hosts[existingKey],
        gate: { ...hosts[existingKey].gate, requiredPlanTier: cfg.requiredPlanTier },
      };
    }
  }

  return parseDigichatConfig(
    {
      version: 1,
      ...(config?.deployment ? { deployment: unresolveCatalog(config.deployment) } : {}),
      hosts,
    },
    "digichat config (tenants merge)",
    { openRouterConfigured: openRouter },
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
/**
 * The placeholder token a shipped template carries. Uppercase only, because
 * the templates write `REPLACE-FOUNDRY-ACCOUNT` and an operator-chosen agent
 * name like `my-REPLACE-agent` is a real name, not a template.
 */
const TEMPLATE_PLACEHOLDER = /REPLACE-[A-Z][A-Z0-9-]*/;

/** The first foundry field of a deployment that still holds a placeholder. */
function placeholderField(deployment: DigichatDeployment | undefined): string | null {
  const backend = deployment?.backend;
  if (!backend || backend.type !== "foundry") return null;
  for (const [name, value] of [
    ["projectEndpoint", backend.projectEndpoint],
    ["agentName", backend.agentName],
  ] as const) {
    if (typeof value === "string" && TEMPLATE_PLACEHOLDER.test(value)) return name;
  }
  return null;
}

/**
 * A shipped template carries `REPLACE-` placeholders. Deployed as-is, the
 * container boots and then fails every chat on a DNS lookup of
 * `replace-foundry-account.services.ai.azure.com` (#6023). Refuse it at load
 * time, naming the file, instead of at chat time with a name nobody can read.
 */
function assertRenderedDeployment(cfg: DigichatConfig, source: string): void {
  const entries: [string, DigichatDeployment | undefined][] = [
    ["deployment", cfg.deployment],
    ...Object.entries(cfg.hosts ?? {}).map(
      ([host, deployment]) => [`hosts.${host}`, deployment] as [string, DigichatDeployment | undefined],
    ),
  ];
  for (const [path, deployment] of entries) {
    const field = placeholderField(deployment);
    if (field) {
      throw new Error(
        `${source}: ${path}.backend.${field} still holds a REPLACE- placeholder — render the tenant config before deploying`,
      );
    }
  }
}

/**
 * Whether any deployment in this config talks to digigraph. A deployment with
 * no backend is a digigraph install (the chat route defaults to it), so an
 * empty config and a registry of foundry tenants both count as "not digigraph"
 * only when every entry says so.
 */
export function configUsesDigigraph(cfg: DigichatConfig): boolean {
  const deployments = [cfg.deployment, ...Object.values(cfg.hosts ?? {})].filter(
    (d): d is DigichatDeployment => Boolean(d),
  );
  if (deployments.length === 0) return true;
  return deployments.some((d) => (d.backend?.type ?? "digigraph") !== "foundry");
}

export function loadDigichatConfig(opts: LoadDigichatConfigOptions = {}): DigichatConfig {
  const env = opts.env ?? process.env;
  // Precedence: DIGICHAT_CONFIG_YAML > DIGICHAT_CONFIG_PATH file > defaults.
  // A blank env value is absent, so the file is read exactly as before.
  // `opts.fileContents` is the test seam that stands in for the file.
  const envYaml = env[CONFIG_YAML_ENV] ?? "";
  const hasEnvYaml = typeof envYaml === "string" && envYaml.trim().length > 0;
  const path = resolveConfigPath(env);
  const source = hasEnvYaml ? CONFIG_YAML_ENV : path;
  const allowMissing = opts.allowMissingFile !== false;

  let fromDocument: DigichatConfig | null = null;
  const contents =
    opts.fileContents !== undefined
      ? opts.fileContents
      : hasEnvYaml
        ? envYaml
        : existsSync(path)
          ? readFileSync(path, "utf8")
          : null;

  if (contents != null && contents.trim()) {
    const parsed = expandDigichatDocument(parseYamlOrJson(contents, source));
    fromDocument = parseDigichatConfig(parsed, source, {
      openRouterConfigured: openRouterConfigured(env),
    });
  } else if (contents != null && !contents.trim()) {
    throw new Error(`${source}: empty document`);
  } else if (!allowMissing && opts.fileContents === undefined && !existsSync(path)) {
    throw new Error(`${path}: file not found`);
  }

  const tenantsRaw = env.DIGICHAT_EMBED_TENANTS;
  let merged: DigichatConfig;
  if (tenantsRaw?.trim()) {
    // The registry overlay wins over the document, whichever it came from.
    merged = mergeEmbedTenantsOverlay(fromDocument, tenantsRaw, openRouterConfigured(env));
  } else if (fromDocument) {
    merged = fromDocument;
  } else {
    // No document and no tenant overlay: house (defaults.yaml).
    merged = loadDefaultsDocument("digichat config (defaults)", {
      openRouterConfigured: openRouterConfigured(env),
    });
  }

  assertRenderedDeployment(merged, source);
  return applyEnvOverlay(merged, env);
}

let cached: DigichatConfig | null = null;
let cachedAt = 0;
let loadError: Error | null = null;

/**
 * Process-wide memo, re-read every CONFIG_CACHE_TTL_MS so an edited
 * `DIGICHAT_CONFIG_YAML` (or file) is picked up by a later request without a
 * restart. Fail closed: the first load error sticks until reset.
 */
export function getDigichatConfig(): DigichatConfig {
  if (loadError) throw loadError;
  const memo = cached;
  if (memo !== null && Date.now() - cachedAt < CONFIG_CACHE_TTL_MS) return memo;
  try {
    const next = loadDigichatConfig();
    cached = next;
    cachedAt = Date.now();
    return next;
  } catch (e) {
    cached = null;
    cachedAt = 0;
    loadError = e instanceof Error ? e : new Error(String(e));
    throw loadError;
  }
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
  cachedAt = 0;
  loadError = null;
}

/** Test hook — inject a parsed config without touching disk. */
export function setDigichatConfigForTests(cfg: DigichatConfig | null): void {
  cached = cfg;
  cachedAt = cfg ? Date.now() : 0;
  loadError = null;
}

/**
 * True when this process is a single-install client container (YAML `deployment`
 * on disk, or DIGICHAT_CHROME_SKIN). Hosts-only configs stay on
 * DIGICHAT_EMBED_TENANTS. The built-in house document is the no-file fallback,
 * not an anonymous install: an unknown parent must not inherit it. Session-auth
 * deployments are not anonymous installs.
 */
export function isExplicitClientInstall(
  config: DigichatConfig = getDigichatConfig(),
  env: NodeJS.ProcessEnv | Record<string, string | undefined> = process.env,
): boolean {
  if (!config.deployment || config.deployment.auth === "session") return false;
  // A host map is a registry. Unknown parents must not fall through to
  // deployment, including when that deployment is house.
  if (config.hosts && Object.keys(config.hosts).length > 0) return false;
  if (env.DIGICHAT_CHROME_SKIN?.trim()) return true;
  // A document supplied through DIGICHAT_CONFIG_YAML is an explicit install
  // even though there is no file on disk to find.
  if ((env[CONFIG_YAML_ENV] ?? "").trim()) return true;
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
