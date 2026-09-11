/**
 * Client-safe projection of digichat deployment config.
 * Tokens, Foundry endpoints, MCP URLs, consume URLs never leave the server.
 */

import type {
  AuthMode,
  ChromeMode,
  DigichatDeployment,
  DisclosureMode,
  PersistenceMode,
  ToolCatalogEntry,
  UserAlign,
} from "./schema";
import { welcomeBodyLines, welcomeTitle } from "./schema";
import {
  BASELINE_EMBED_PLACEHOLDER,
  BASELINE_EMBED_SKIN,
  BASELINE_EMBED_SUGGESTIONS,
  BASELINE_EMBED_WELCOME,
  BASELINE_EMBED_WELCOME_BODY,
} from "@/lib/baseline-embed";
import { DEFAULT_LANGUAGE_CODE } from "@/lib/languages";
import { DEFAULT_THREAD_SKIN, type ThreadSkin } from "@/lib/thread-skins";

export type DigichatClientFeatures = {
  attachments: boolean;
  dictation: boolean;
  speech: boolean;
  reasoning: DisclosureMode;
  toolCalls: DisclosureMode;
  sources: boolean;
  modelPicker: boolean;
  branchPicker: boolean;
};

export type DigichatClientChrome = {
  mode: ChromeMode;
  theme: "dark" | "light";
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
};

export type DigichatClientTool = {
  id: string;
  default: boolean;
  label?: string;
};

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
    servers: Array<{ id: string; label?: string; default?: boolean }>;
    allowUserServers: boolean;
    allowAddForm: boolean;
  };
  gate: {
    mode: "turn_limited" | "ungated" | "trial_form";
    activityDetail: "off" | "labels" | "full";
    llmAccess?: DigichatDeployment["gate"]["llmAccess"];
    lockedContact?: string;
    showByok?: boolean;
    showLanguageSelector?: boolean;
    webSearch?: boolean;
  };
  /** Discriminator only — never project endpoints / agent names */
  backendType: "digigraph" | "foundry";
};

export const DEFAULT_CLIENT_CONFIG: DigichatClientConfig = {
  slug: "embed",
  chrome: {
    mode: "embed",
    theme: "dark",
    skin: BASELINE_EMBED_SKIN,
    welcome: BASELINE_EMBED_WELCOME,
    welcomeBody: [...BASELINE_EMBED_WELCOME_BODY],
    placeholder: BASELINE_EMBED_PLACEHOLDER,
    suggestions: [...BASELINE_EMBED_SUGGESTIONS],
    accent: null,
    attribution: false,
    defaultLanguage: DEFAULT_LANGUAGE_CODE,
    transcript: { userAlign: "right" },
  },
  persistence: "none",
  auth: "anonymous",
  features: {
    attachments: true,
    dictation: false,
    speech: false,
    reasoning: "collapsed",
    toolCalls: "collapsed",
    sources: true,
    modelPicker: false,
    branchPicker: true,
  },
  models: {
    default: "deepseek/deepseek-v4-flash",
    available: [
      "deepseek/deepseek-v4-flash",
      "deepseek/deepseek-v4-flash-0731",
      "openai/gpt-oss-120b",
      "z-ai/glm-5.3-flash",
    ],
    allowPicker: true,
  },
  cli: { enabled: false },
  tools: { allowUserToggle: true, catalog: [] },
  mcp: { servers: [], allowUserServers: true, allowAddForm: true },
  gate: {
    mode: "turn_limited",
    activityDetail: "labels",
    showByok: true,
    showLanguageSelector: false,
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
  }));
}

/** Server deployment → browser-safe projection. Copies declared fields only. */
export function toDigichatClientConfig(dep: DigichatDeployment): DigichatClientConfig {
  const catalog = projectCatalog(dep.tools?.catalog);
  const webSearch =
    dep.gate.webSearch === true || catalog.some((t) => t.id === "web_search" && t.default);
  const models = dep.models;
  const allowPicker =
    models?.allowPicker === true ||
    (models?.allowPicker !== false && dep.features.modelPicker === true);

  return {
    slug: dep.slug,
    chrome: {
      mode: dep.chrome.mode,
      theme: dep.chrome.theme,
      skin: dep.chrome.skin ?? DEFAULT_THREAD_SKIN,
      title: dep.chrome.title,
      welcome: welcomeTitle(dep.chrome.welcome),
      welcomeBody: welcomeBodyLines(dep.chrome.welcome),
      suggestions: dep.chrome.suggestions,
      placeholder: dep.chrome.placeholder,
      accent: dep.chrome.accent ?? null,
      attribution: dep.chrome.attribution === true,
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
    },
    cli: { enabled: dep.cli?.enabled === true },
    tools: {
      allowUserToggle: dep.tools?.allowUserToggle ?? true,
      catalog,
    },
    mcp: {
      servers: (dep.mcp?.servers ?? []).map((s) => ({
        id: s.id,
        ...(s.label ? { label: s.label } : {}),
        ...(typeof s.default === "boolean" ? { default: s.default } : {}),
      })),
      allowUserServers: dep.mcp?.allowUserServers === true,
      allowAddForm: dep.mcp?.allowUserServers === true && dep.mcp?.allowAddForm === true,
    },
    gate: {
      mode: dep.gate.mode,
      activityDetail: dep.gate.activityDetail,
      llmAccess: dep.gate.llmAccess,
      lockedContact: dep.gate.lockedContact,
      showByok: dep.gate.showByok,
      showLanguageSelector: dep.gate.showLanguageSelector,
      webSearch,
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
