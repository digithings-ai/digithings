/**
 * Product-skin slash commands for the assistant-ui trigger popover (#3733 / #3736).
 * Command *data* comes from `@digithings/digichat-ui`; execute closures live here.
 */

import type { Unstable_SlashCommand } from "@assistant-ui/react";
import {
  catalogToolSlashDef,
  isEffortCode,
  parseSlashInput,
  type SlashDef,
  type SlashVisibility,
  SLASH_CATEGORIES,
  SLASH_COMMANDS,
} from "@digithings/digichat-ui";
import {
  FEATURED_LANGUAGE_CODES,
  LANGUAGES,
  languageLabel,
  tryResolveLanguageInput,
} from "@/lib/languages";
import type { EmbedChatPrefsApi } from "@/components/stock/embed-chat-prefs";
import { connectedMcpConfigs } from "@/components/stock/embed-mcp-flow";

export type SlashSubmitAction =
  | { kind: "pass" }
  | { kind: "block" }
  | { kind: "force"; forceTool: string; text: string }
  | { kind: "force-web"; text: string }
  | { kind: "run"; command: SlashDef; arg: string };

/** Map slash force-tool ids onto BFF catalog values. */
export function catalogForceTool(forceTool: string | undefined): string | undefined {
  if (!forceTool) return undefined;
  if (forceTool === "digivault_search_notes") return "digivault";
  if (forceTool === "web_search") return undefined;
  return forceTool;
}

export function extraSlashDefs(api: EmbedChatPrefsApi): SlashDef[] {
  const builtins = new Set(SLASH_COMMANDS.map((c) => c.id));
  const seen = new Set<string>();
  const out: SlashDef[] = [];
  const mcp = connectedMcpConfigs(api.mcpServers, api.prefs.mcpCustom);
  for (const t of [...api.catalogTools, ...mcp]) {
    const id = t.id.trim();
    if (!id || seen.has(id) || builtins.has(id) || id === "web_search") continue;
    seen.add(id);
    out.push(catalogToolSlashDef(t));
  }
  return out;
}

export function slashSubmitAction(raw: string, extra?: readonly SlashDef[]): SlashSubmitAction {
  if (raw.includes("\n") && raw.trim().startsWith("/")) {
    return { kind: "block" };
  }
  const parsed = parseSlashInput(raw, extra);
  if (parsed.kind === "none") return { kind: "pass" };
  if (parsed.kind === "unknown") return { kind: "block" };
  if (parsed.kind === "incomplete") return { kind: "block" };
  const { command, arg } = parsed;
  if (command.kind === "tool" && arg) {
    if (command.id === "websearch" || command.forceTool === "web_search") {
      return { kind: "force-web", text: arg };
    }
    const forceTool = catalogForceTool(command.forceTool);
    if (!forceTool) return { kind: "block" };
    return { kind: "force", forceTool, text: arg };
  }
  return { kind: "run", command, arg };
}

export function visibilityFromPrefs(api: EmbedChatPrefsApi): SlashVisibility {
  const hasMcp = api.allowUserMcp || api.mcpServers.length > 0;
  const hasTools =
    api.hasDigisearch ||
    api.hasVault ||
    api.tenantAllowsWeb ||
    api.catalogTools.length > 0 ||
    hasMcp;
  return {
    webSearch: api.tenantAllowsWeb,
    byok: api.showByok,
    digisearch: api.hasDigisearch,
    digivault: api.hasVault,
    sessions: api.hasSessions,
    models: api.showModels,
    mcp: hasMcp,
    tools: hasTools,
  };
}

function toggleHint(on: boolean, onText: string, offText: string): string {
  return on ? `On · ${onText}` : `Off · ${offText}`;
}

/** Featured language rows so `/dutch` etc. still resolve. */
export function featuredLanguageCommands(
  setLanguage: (code: string) => void,
): Unstable_SlashCommand[] {
  return FEATURED_LANGUAGE_CODES.map((code) => {
    const label = languageLabel(code);
    return {
      id: label.toLowerCase(),
      label: `/${label.toLowerCase()}`,
      description: `Reply in ${label}`,
      execute: () => setLanguage(code),
    };
  });
}

export function slashCategoryOf(id: string): string {
  if (FEATURED_LANGUAGE_CODES.some((c) => languageLabel(c).toLowerCase() === id)) {
    return "setup";
  }
  const def = SLASH_COMMANDS.find((c) => c.id === id || c.id === (id === "language" ? "lang" : id));
  return def?.category ?? "tools";
}

export function buildProductSlashCommands(api: EmbedChatPrefsApi): Unstable_SlashCommand[] {
  const vis = visibilityFromPrefs(api);
  const { prefs } = api;
  const extra = extraSlashDefs(api);
  const rows: Unstable_SlashCommand[] = [];

  for (const def of [...SLASH_COMMANDS, ...extra]) {
    if (def.id === "websearch" && !vis.webSearch) continue;
    if (def.id === "byok" && vis.byok === false) continue;
    if (def.id === "digisearch" && vis.digisearch === false) continue;
    if (def.id === "digivault" && vis.digivault === false) continue;
    if (def.id === "sessions" && vis.sessions !== true) continue;
    if ((def.id === "models" || def.id === "effort") && vis.models === false) continue;
    if (def.id === "mcp" && vis.mcp === false) continue;
    if (def.id === "tools" && vis.tools === false) continue;

    let description = def.hint;
    if (def.id === "websearch") {
      description = toggleHint(prefs.webSearch, "External cites", "corpus only");
    } else if (def.id === "digisearch") {
      description = toggleHint(prefs.digisearch, "knowledge base", "disabled this session");
    } else if (def.id === "digivault") {
      description = toggleHint(prefs.vault, "vault notes", "disabled this session");
    } else if (def.id === "thinking") {
      description = toggleHint(prefs.thinking, "reasoning visible", "reasoning hidden");
    } else if (def.id === "lang") {
      description = `Reply language (${languageLabel(prefs.language)})`;
    } else if (def.id === "models") {
      description = prefs.model || def.hint;
    } else if (def.id === "effort") {
      description = prefs.effort || "medium";
    } else if (def.kind === "tool" && def.id) {
      const on = api.extraToolOn(def.id);
      description = toggleHint(on, def.hint, "disabled this session");
    }

    const id = def.id === "lang" ? "language" : def.id;
    const insertName = def.names[0];
    rows.push({
      id,
      label: insertName,
      description,
      execute: () => {
        if (def.kind === "tool") return;
        executeSlashDef(def, "", api);
      },
    });
  }

  rows.push(...featuredLanguageCommands(api.setLanguage));
  return rows;
}

/** Menu pick for a catalog tool inserts `/id ` so the user can add a query. */
export function shouldInsertToolDraft(id: string, extra: readonly SlashDef[]): boolean {
  if (id === "digisearch" || id === "digivault" || id === "websearch") return true;
  return extra.some((d) => d.id === id && d.kind === "tool");
}

export function executeSlashDef(def: SlashDef, arg: string, api: EmbedChatPrefsApi): void {
  switch (def.id) {
    case "websearch":
      if (api.tenantAllowsWeb) api.setWebSearch(!api.prefs.webSearch);
      return;
    case "digisearch":
      api.setDigisearch(!api.prefs.digisearch);
      return;
    case "digivault":
      api.setVault(!api.prefs.vault);
      return;
    case "thinking":
      api.setThinking(!api.prefs.thinking);
      return;
    case "lang": {
      if (!arg) {
        api.openLanguage();
        return;
      }
      const code = tryResolveLanguageInput(arg);
      if (code) api.setLanguage(code);
      else api.openLanguage();
      return;
    }
    case "settings":
      api.openSettings();
      return;
    case "tools":
      api.openTools();
      return;
    case "mcp":
      api.openMcp(arg);
      return;
    case "models":
      api.openModels();
      return;
    case "effort": {
      if (!arg) {
        api.openEffort();
        return;
      }
      const value = arg.trim().toLowerCase();
      if (isEffortCode(value)) api.setEffort(value);
      return;
    }
    case "sessions":
      api.openSessions();
      return;
    case "help":
      // Placeholder — the slash list is the help. Do not dump into the composer.
      return;
    case "byok":
      api.openByok(arg);
      return;
    case "new":
    case "clear":
      api.reset();
      api.newThread();
      return;
    case "compact":
      void api.compactThread();
      return;
    case "undo":
      api.undo();
      return;
    case "redo":
      api.redo();
      return;
    default:
      if (def.kind === "tool") {
        api.setExtraTool(def.id, !api.extraToolOn(def.id));
      }
      return;
  }
}

export function executeSlashFromComposer(
  id: "lang" | "effort" | "byok" | "mcp" | "tools",
  composerText: string,
  api: EmbedChatPrefsApi,
  extra?: readonly SlashDef[],
): void {
  const parsed = parseSlashInput(composerText, extra);
  const arg = parsed.kind === "command" && parsed.command.id === id ? parsed.arg : "";
  const def =
    parsed.kind === "command" && parsed.command.id === id
      ? parsed.command
      : SLASH_COMMANDS.find((c) => c.id === id);
  if (def) executeSlashDef(def, arg, api);
}

export function languageSelectOptions(): {
  value: string;
  label: string;
  native: string;
}[] {
  const featured = new Set<string>(FEATURED_LANGUAGE_CODES);
  const head = FEATURED_LANGUAGE_CODES.map((code) => {
    const row = LANGUAGES.find((l) => l.code === code);
    return {
      value: code,
      label: row?.label ?? code,
      native: row?.native ?? languageLabel(code),
    };
  });
  const rest = LANGUAGES.filter((l) => !featured.has(l.code)).map((l) => ({
    value: l.code,
    label: l.label,
    native: l.native,
  }));
  return [...head, ...rest];
}

/** Prefix-match popover rows so `/se` does not highlight `/digisearch`. */
export function slashItemPrefixMatch(
  item: { id: string; label?: string },
  query: string,
): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  if (item.id.toLowerCase().startsWith(q)) return true;
  const label = (item.label ?? "").replace(/^\//, "").toLowerCase();
  return label.startsWith(q);
}

type SlashAdapterLike = {
  search?: (query: string) => readonly { id: string; label?: string }[];
  categories?: () => readonly { id: string; label: string }[];
  categoryItems?: (categoryId: string) => readonly unknown[];
};

/** Prefix-match only — no category folders, so `/` is a navigable item list. */
export function prefixSlashAdapter<T extends SlashAdapterLike>(inner: T): T {
  return {
    ...inner,
    categories: () => [],
    categoryItems: () => [],
    search: (query: string) => {
      const raw = inner.search?.(query) ?? [];
      return raw.filter((item) => slashItemPrefixMatch(item, query));
    },
  } as T;
}

/** @deprecated Use prefixSlashAdapter — categories were dropped from the product palette. */
export const categorizedSlashAdapter = prefixSlashAdapter;

export { SLASH_CATEGORIES };
