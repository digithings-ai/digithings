/**
 * Product-skin slash commands for the assistant-ui trigger popover (#3733).
 * Command *data* comes from `@digithings/digichat-ui`; execute closures live here.
 */

import type { Unstable_SlashCommand } from "@assistant-ui/react";
import {
  parseSlashInput,
  type SlashDef,
  type SlashVisibility,
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
  | { kind: "run"; command: SlashDef; arg: string };

/** Map slash force-tool ids onto BFF catalog values. */
export function catalogForceTool(forceTool: string | undefined): string | undefined {
  if (!forceTool) return undefined;
  if (forceTool === "digivault_search_notes") return "digivault";
  return forceTool;
}

export function slashSubmitAction(raw: string): SlashSubmitAction {
  if (raw.includes("\n") && raw.trim().startsWith("/")) {
    return { kind: "block" };
  }
  const parsed = parseSlashInput(raw);
  if (parsed.kind === "none") return { kind: "pass" };
  if (parsed.kind === "unknown") return { kind: "block" };
  if (parsed.kind === "incomplete") return { kind: "block" };
  if (parsed.command.kind === "force") {
    const forceTool = catalogForceTool(parsed.command.forceTool);
    if (!forceTool || !parsed.arg) return { kind: "block" };
    return { kind: "force", forceTool, text: parsed.arg };
  }
  return { kind: "run", command: parsed.command, arg: parsed.arg };
}

export function visibilityFromPrefs(api: EmbedChatPrefsApi): SlashVisibility {
  return {
    webSearch: api.tenantAllowsWeb,
    byok: api.showByok,
    digisearch: api.hasDigisearch,
    digivault: api.hasVault,
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

export function buildProductSlashCommands(api: EmbedChatPrefsApi): Unstable_SlashCommand[] {
  const vis = visibilityFromPrefs(api);
  const { prefs } = api;
  const rows: Unstable_SlashCommand[] = [];

  for (const def of SLASH_COMMANDS) {
    if (def.id === "websearch" && !vis.webSearch) continue;
    if (def.id === "byok" && vis.byok === false) continue;
    if (def.id === "toggle-digisearch" && vis.digisearch === false) continue;
    if (def.id === "toggle-digivault" && vis.digivault === false) continue;

    let description = def.hint;
    if (def.id === "websearch") {
      description = toggleHint(prefs.webSearch, "External cites", "corpus only");
    } else if (def.id === "toggle-digisearch") {
      description = toggleHint(prefs.digisearch, "knowledge base", "disabled this session");
    } else if (def.id === "toggle-digivault") {
      description = toggleHint(prefs.vault, "vault notes", "disabled this session");
    } else if (def.id === "lang") {
      description = `Reply language (${languageLabel(prefs.language)})`;
    }

    const id = def.id === "lang" ? "language" : def.id;
    rows.push({
      id,
      label: def.names[0],
      description,
      icon: iconForSlash(def.id),
      execute: () => executeSlashDef(def, "", api),
    });
  }

  rows.push(...featuredLanguageCommands(api.setLanguage));
  return rows;
}

export function executeSlashDef(def: SlashDef, arg: string, api: EmbedChatPrefsApi): void {
  switch (def.id) {
    case "websearch":
      if (api.tenantAllowsWeb) api.setWebSearch(!api.prefs.webSearch);
      return;
    case "toggle-digisearch":
      api.setDigisearch(!api.prefs.digisearch);
      return;
    case "toggle-digivault":
      api.setVault(!api.prefs.vault);
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
    case "help":
      return;
    case "byok":
      api.openByok();
      return;
    case "new":
      api.reset();
      api.newThread();
      return;
    default:
      return;
  }
}

function iconForSlash(id: SlashDef["id"]): string {
  switch (id) {
    case "websearch":
      return "Globe";
    case "search":
    case "toggle-digisearch":
      return "Search";
    case "vault":
    case "toggle-digivault":
      return "Folder";
    case "lang":
      return "Languages";
    case "settings":
      return "Settings";
    case "byok":
      return "Key";
    case "help":
      return "HelpCircle";
    case "new":
      return "Plus";
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

/** Prefix-match popover rows so `/search` does not highlight `/digisearch`. */
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
