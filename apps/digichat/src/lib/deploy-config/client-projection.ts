/**
 * Client-safe projection of digichat deployment config.
 * Tokens, Foundry endpoints, MCP URLs, consume URLs never leave the server.
 */

import type {
  AuthMode,
  BootLoading,
  ChromeMode,
  DigichatDeployment,
  PageContextMode,
  PersistenceMode,
  ToolCatalogEntry,
  UserAlign,
} from "./schema";
import type { ThinkingMode, ViewMode } from "@/lib/view-modes";
import { welcomeBodyLines, welcomeTitle } from "./schema";
import { DEFAULT_LANGUAGE_CODE } from "@/lib/languages";
import { DEPLOY_DEFAULT_MODELS } from "./deploy-models";
import { resolveModelCatalog, type ModelPickerView } from "@/lib/model-picker-catalog";

const HOUSE_WELCOME = "Ask about digithings";
const HOUSE_WELCOME_BODY = "Explore the documentation, dig into the stack, or search the vault.";
const HOUSE_SUGGESTIONS = [
  "What is digigraph?",
  "How do embeds work?",
  "What components are in the stack?",
  "How do I run the stack locally?",
  "What models does digichat support?",
  "How does digiquant handle backtests?",
  "What is digivault?",
  "How do I create an embed?",
] as const;

/** Same catalog resolution defaults.yaml asks for. OpenRouter stays off until a key is set. */
const HOUSE_CATALOG = resolveModelCatalog(
  {
    default: DEPLOY_DEFAULT_MODELS.default,
    priceCapUsdPerMillion: 2,
    presets: ["auto", "reasoning", "fast", "light"],
    showFullList: true,
  },
  { openRouterConfigured: false },
);

/** Search-engine ids the BFF forwards to digigraph (digisearch vocabulary, #4724). */
export const SEARCH_ENGINE_ALLOWLIST: ReadonlySet<string> = new Set([
  "auto",
  "internal",
  "exa",
  "tavily",
  "parallel",
  "firecrawl",
  "tinyfish",
]);
import {
  DEFAULT_THREAD_SKIN,
  type ThreadSkin,
} from "@digithings/ui/chat/skins";

export type DigichatClientFeatures = {
  attachments: boolean;
  dictation: boolean;
  speech: boolean;
  view: ViewMode;
  thinking: ThinkingMode;
  density: "compact" | "default" | "airy";
  effort: "low" | "medium" | "high";
  sources: boolean;
  modelPicker: boolean;
  branchPicker: boolean;
  pageContext: PageContextMode;
};

export type DigichatClientChrome = {
  mode: ChromeMode;
  theme: "dark" | "light";
  /** Named palette. Absent means the skin palette. */
  palette?: string;
  toolbar: boolean;
  scrollbars: "always" | "auto";
  /** Boot animation. `banner` is the standard digichat cover. */
  loading?: BootLoading;
  /** `follow` chases the stream after anchoring the question; `free` is inert. */
  scroll: { mode: "follow" | "free" };
  skin: ThreadSkin;
  title?: string;
  /** Headline. Legacy YAML `welcome: "…"` still lands here. */
  welcome?: string;
  /** Subparagraphs under the headline. Empty when YAML only set a string. */
  welcomeBody?: string[];
  suggestions?: string[];
  placeholder?: string;
  accent: { color: string; foreground: string } | null;
  attribution: boolean;
  defaultLanguage: string;
  transcript: { userAlign: UserAlign };
  launcher?: {
    hotkey?: string;
    mobileFullscreen?: boolean;
    label?: string;
    closeLabel?: string;
    mode?: "dot" | "bar";
  };
};

export type DigichatClientModels = {
  default?: string;
  available: string[];
  allowPicker: boolean;
  /** Presets and provider groups. Present when the deployment uses the catalog. */
  picker?: ModelPickerView;
};

/** `group` files the tool under a sub-header in `/tools`. */
export type DigichatClientSubTool = { id: string; label?: string; group?: string };

export type DigichatClientTool = {
  id: string;
  default: boolean;
  label?: string;
  /** Individual tools under this entry (per-tool session toggles). */
  tools?: DigichatClientSubTool[];
};

/** MCP allowlist → per-tool ids as digigraph offers them (`<server>_<tool>`). */
export function mcpSubTools(
  serverId: string,
  allowedTools: readonly string[] | undefined,
): DigichatClientSubTool[] | undefined {
  if (!allowedTools?.length) return undefined;
  return allowedTools.map((t) => ({
    id: `${serverId}_${t.replace(/[^a-zA-Z0-9_-]/g, "_").slice(0, 64)}`.toLowerCase(),
    label: t,
  }));
}

export type DigichatClientConfig = {
  slug: string;
  chrome: DigichatClientChrome;
  persistence: PersistenceMode;
  auth: AuthMode;
  features: DigichatClientFeatures;
  models: DigichatClientModels;
  /** Advisory — CLI is a separate Node binary; never imported by the web app. */
  cli: { enabled: boolean };
  /** Catalog entries only — no MCP URLs */
  tools: {
    allowUserToggle: boolean;
    catalog: DigichatClientTool[];
  };
  /** MCP server ids/labels only — never URLs */
  mcp: {
    servers: Array<{
      id: string;
      label?: string;
      default?: boolean;
      tools?: DigichatClientSubTool[];
    }>;
    allowUserServers: boolean;
    allowAddForm: boolean;
  };
  gate: {
    mode: "turn_limited" | "ungated" | "trial_form";
    llmAccess?: DigichatDeployment["gate"]["llmAccess"];
    lockedContact?: string;
    showByok?: boolean;
    showLanguageSelector?: boolean;
    showContextMeter?: boolean;
    webSearch?: boolean;
    searchEngine?: string;
    /** Present only when the host locks session tool/MCP toggles. */
    lockSessionControls?: boolean;
  };
  /** Discriminator only — never project endpoints / agent names */
  backendType: DigichatDeployment["backend"]["type"];
};

export const DEFAULT_CLIENT_CONFIG: DigichatClientConfig = {
  slug: "digithings-ai",
  chrome: {
    mode: "embed",
    theme: "dark",
    skin: "digichat",
    toolbar: true,
    scroll: { mode: "follow" },
    scrollbars: "always",
    loading: "banner",
    title: "ask digichat",
    welcome: HOUSE_WELCOME,
    welcomeBody: [HOUSE_WELCOME_BODY],
    placeholder: "Ask a question",
    suggestions: [...HOUSE_SUGGESTIONS],
    accent: null,
    attribution: true,
    defaultLanguage: DEFAULT_LANGUAGE_CODE,
    transcript: { userAlign: "right" },
    launcher: {
      mode: "bar",
      label: "ask digichat",
      closeLabel: "close",
      mobileFullscreen: true,
    },
  },
  persistence: "none",
  auth: "anonymous",
  features: {
    attachments: false,
    dictation: false,
    speech: false,
    // House YAML still sets the legacy reasoning/toolCalls booleans. Those
    // fold to quiet + collapsed when view and thinking are omitted.
    view: "quiet",
    thinking: "collapsed",
    density: "default",
    effort: "medium",
    sources: true,
    modelPicker: true,
    branchPicker: true,
    pageContext: "visible",
  },
  models: {
    default: HOUSE_CATALOG.default,
    available: HOUSE_CATALOG.available,
    allowPicker: true,
    picker: HOUSE_CATALOG.picker,
  },
  cli: { enabled: false },
  tools: {
    allowUserToggle: true,
    catalog: [
      { id: "digisearch", default: true, label: "Search" },
      { id: "digivault", default: true, label: "Vault" },
    ],
  },
  mcp: {
    servers: [
      { id: "digisearch", label: "Search", default: true },
      { id: "digivault", label: "Vault", default: true },
    ],
    allowUserServers: false,
    allowAddForm: false,
  },
  gate: {
    mode: "ungated",
    llmAccess: "free_then_byok",
    showByok: true,
    showLanguageSelector: true,
    showContextMeter: true,
    webSearch: true,
  },
  backendType: "digigraph",
};

function projectCatalog(entries: ToolCatalogEntry[] | undefined): DigichatClientTool[] {
  if (!entries?.length) return [];
  return entries.map((e) => ({
    id: e.id,
    // Omitted YAML `default` means session-OFF (#3805 fail-closed for promote).
    // Only explicit `default: true` starts the tool on.
    default: e.default === true,
    ...(e.label ? { label: e.label } : {}),
    ...(e.tools?.length ? { tools: e.tools.map((t) => ({ ...t })) } : {}),
  }));
}

/** Server deployment → browser-safe projection. Copies declared fields only. */
export function toDigichatClientConfig(dep: DigichatDeployment): DigichatClientConfig {
  const catalog = projectCatalog(dep.tools?.catalog);
  const webSearch =
    dep.gate.webSearch === true || catalog.some((t) => t.id === "web_search" && t.default);
  // Tenant search-engine default: engine NAME only (never keys). Unknown values
  // are dropped here (GateSchema also rejects them at load); absent = auto (#4724).
  const rawEngine = (dep.gate.searchEngine ?? "").trim().toLowerCase();
  const searchEngine = SEARCH_ENGINE_ALLOWLIST.has(rawEngine) ? rawEngine : undefined;
  const models = dep.models;
  const allowPicker =
    models?.allowPicker === true ||
    (models?.allowPicker !== false && dep.features.modelPicker === true);

  return {
    slug: dep.slug,
    chrome: {
      mode: dep.chrome.mode,
      theme: dep.chrome.theme,
      ...(dep.chrome.palette ? { palette: dep.chrome.palette } : {}),
      toolbar: dep.chrome.toolbar !== false,
      scrollbars: dep.chrome.scrollbars ?? "always",
      loading: dep.chrome.loading ?? "banner",
      scroll: { mode: dep.chrome.scroll?.mode ?? "follow" },
      skin: dep.chrome.skin ?? DEFAULT_THREAD_SKIN,
      title: dep.chrome.title,
      welcome: welcomeTitle(dep.chrome.welcome),
      welcomeBody: welcomeBodyLines(dep.chrome.welcome),
      suggestions: dep.chrome.suggestions,
      placeholder: dep.chrome.placeholder,
      accent: dep.chrome.accent ?? null,
      attribution: dep.chrome.attribution !== false,
      defaultLanguage: dep.chrome.defaultLanguage ?? DEFAULT_LANGUAGE_CODE,
      transcript: {
        userAlign: dep.chrome.transcript?.userAlign ?? "right",
      },
      ...(dep.chrome.launcher
        ? {
            launcher: {
              hotkey: dep.chrome.launcher.hotkey,
              mobileFullscreen: dep.chrome.launcher.mobileFullscreen,
              label: dep.chrome.launcher.label,
              closeLabel: dep.chrome.launcher.closeLabel,
              mode: dep.chrome.launcher.mode,
            },
          }
        : {}),
    },
    persistence: dep.persistence,
    auth: dep.auth,
    features: { ...dep.features },
    models: {
      ...(models?.default ? { default: models.default } : {}),
      available: [...(models?.available ?? [])],
      allowPicker,
      ...(models?.picker ? { picker: models.picker } : {}),
    },
    cli: { enabled: dep.cli?.enabled === true },
    tools: {
      allowUserToggle: dep.tools?.allowUserToggle ?? true,
      catalog,
    },
    mcp: {
      servers: (dep.mcp?.servers ?? []).map((s) => {
        const tools = mcpSubTools(s.id, s.allowedTools);
        return {
          id: s.id,
          ...(s.label ? { label: s.label } : {}),
          ...(typeof s.default === "boolean" ? { default: s.default } : {}),
          ...(tools ? { tools } : {}),
        };
      }),
      allowUserServers: dep.mcp?.allowUserServers === true,
      allowAddForm: dep.mcp?.allowUserServers === true && dep.mcp?.allowAddForm === true,
    },
    gate: {
      mode: dep.gate.mode,
      llmAccess: dep.gate.llmAccess,
      lockedContact: dep.gate.lockedContact,
      showByok: dep.gate.showByok,
      showLanguageSelector: dep.gate.showLanguageSelector,
      ...(typeof dep.gate.showContextMeter === "boolean"
        ? { showContextMeter: dep.gate.showContextMeter }
        : {}),
      webSearch,
      ...(searchEngine ? { searchEngine } : {}),
      ...(dep.gate.lockSessionControls === true ? { lockSessionControls: true } : {}),
    },
    backendType: dep.backend.type,
  };
}

/** Chrome-only projection for widget.js / dashboard popup (no tools/MCP). */
export type DigichatChromeClientConfig = DigichatClientChrome & {
  slug: string;
  persistence: PersistenceMode;
  auth: AuthMode;
};

export function toChromeClientConfig(dep: DigichatDeployment): DigichatChromeClientConfig {
  const full = toDigichatClientConfig(dep);
  return {
    slug: full.slug,
    ...full.chrome,
    persistence: full.persistence,
    auth: full.auth,
  };
}
