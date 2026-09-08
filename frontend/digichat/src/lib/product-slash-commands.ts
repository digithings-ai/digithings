/**
 * Product-skin slash commands for the assistant-ui trigger popover (#3733 / #3736).
 * Command *data* comes from `@digithings/digichat-ui`; execute closures live here.
 */

import type { Unstable_SlashCommand } from "@assistant-ui/react";
import {
  catalogToolSlashDef,
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
  return api.catalogTools
    .filter((t) => !builtins.has(t.id) && t.id !== "web_search")
    .map((t) => catalogToolSlashDef(t));
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
  return {
    webSearch: api.tenantAllowsWeb,
    byok: api.showByok,
    digisearch: api.hasDigisearch,
    digivault: api.hasVault,
    sessions: api.hasSessions,
    models: api.showModels,
    mcp: true,
  };
}

function toggleHint(on: boolean, onText: string, offText: string): string {
  return on ? `On — ${onText}` : `Off — ${offText}`;
}

/** Featured language rows so `/language` prefix-matches Dutch, etc. */
export function featuredLanguageCommands(
  setLanguage: (code: string) => void,
): Unstable_SlashCommand[] {
  return FEATURED_LANGUAGE_CODES.map((code) => {
    const label = languageLabel(code);
    return {
      id: label.toLowerCase(),
      label: `/${label.toLowerCase()}`,
      description: `Language: ${label}`,
      icon: "Languages",
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
      icon: iconForSlash(def.id),
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
        api.openSettings();
        return;
      }
      const code = tryResolveLanguageInput(arg);
      if (code) api.setLanguage(code);
      return;
    }
    case "settings":
      api.openSettings();
      return;
    case "mcp":
      api.openMcp();
      return;
    case "models":
      api.openModels();
      return;
    case "sessions":
      api.openSessions();
      return;
    case "help":
      return;
    case "byok":
      api.openByok();
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

function iconForSlash(id: string): string {
  switch (id) {
    case "websearch":
      return "Globe";
    case "digisearch":
      return "Search";
    case "digivault":
      return "Folder";
    case "mcp":
      return "Wrench";
    case "lang":
      return "Languages";
    case "settings":
      return "Settings";
    case "byok":
      return "Key";
    case "models":
      return "Sparkles";
    case "thinking":
      return "Lightbulb";
    case "sessions":
      return "Menu";
    case "help":
      return "HelpCircle";
    case "new":
    case "clear":
      return "Plus";
    case "compact":
      return "FileText";
    case "undo":
      return "Undo";
    case "redo":
      return "Redo";
    case "copy":
      return "Copy";
    case "export":
      return "Download";
    default:
      return "Slash";
  }
}

export function languageSelectOptions(): { value: string; label: string }[] {
  const featured = new Set<string>(FEATURED_LANGUAGE_CODES);
  const head = FEATURED_LANGUAGE_CODES.map((code) => ({
    value: code,
    label: languageLabel(code),
  }));
  const rest = LANGUAGES.filter((l) => !featured.has(l.code)).map((l) => ({
    value: l.code,
    label: l.label,
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
  search?: (query: string) => Array<{ id: string; label?: string }>;
  categories?: () => Array<{ id: string; label: string }>;
  categoryItems?: (categoryId: string) => unknown[];
};

/** Wrap the native slash adapter with Actions / Tools / Session / Setup. */
export function categorizedSlashAdapter<T extends SlashAdapterLike>(inner: T): T {
  const all = () => inner.search?.("") ?? [];
  return {
    ...inner,
    categories: () => [...SLASH_CATEGORIES],
    categoryItems: (categoryId: string) =>
      all().filter((item) => slashCategoryOf(item.id) === categoryId),
    search: (query: string) => {
      const raw = inner.search?.(query) ?? [];
      return raw.filter((item) => slashItemPrefixMatch(item, query));
    },
  };
}

export { SLASH_CATEGORIES };
