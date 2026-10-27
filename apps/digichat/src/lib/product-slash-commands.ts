/**
 * Product-skin slash commands for the assistant-ui trigger popover (#3733 / #3736).
 * Command *data* comes from `@digithings/digichat-ui`; execute closures live here.
 */

import type { Unstable_SlashCommand } from "@assistant-ui/react";
import {
  commandOpensPane,
  isEffortCode,
  isSearchEngine,
  isThinkingCode,
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
import { isTraceDensity } from "@digithings/ui/chat/trace-spacing";
import type { EmbedChatPrefsApi } from "@digithings/ui/chat/stock";
import {
  applyDocumentTheme,
  isPaletteId,
  isThemePreference,
  matchThemeStep,
  normalizePalette,
  type ThemePreference,
  type ThemeState,
} from "@digithings/ui/theme";
import {
  isLegacyViewMode,
  isViewMode,
  normalizeViewMode,
} from "@/lib/view-modes";
import { applyThemeModeKeepingPalette, readEffectiveThemeState } from "@/lib/palette-prefs";

export type SlashSubmitAction =
  | { kind: "pass" }
  | { kind: "block"; reason?: string }
  | { kind: "force"; forceTool: string; text: string }
  | { kind: "force-web"; text: string }
  | { kind: "pane"; command: SlashDef; arg: string }
  | { kind: "run"; command: SlashDef; arg: string };

/** Map slash force-tool ids onto BFF catalog values. */
export function catalogForceTool(forceTool: string | undefined): string | undefined {
  if (!forceTool) return undefined;
  if (forceTool === "digivault_search_notes") return "digivault";
  if (forceTool === "web_search") return undefined;
  return forceTool;
}

/** Catalog and MCP tools are toggled in `/tools`, not as their own commands. */
export function extraSlashDefs(api: EmbedChatPrefsApi): SlashDef[] {
  void api;
  return [];
}

/**
 * Session private mode (`?private=1`, then `/private` to toggle).
 *
 * Module scope, not React state: the slash wiring is a static function object
 * (`digichat-skin-options`) and `slashSubmitAction` takes no session argument,
 * so a state value would never reach the command. The transport is frozen on
 * first render (#1339) for the same reason — its header accessor reads here.
 * ON-only by construction: a session starts private from the URL or is switched
 * to it; there is no `private=0`.
 */
let privateMode = false;
const privateModeListeners = new Set<() => void>();

export function isPrivateMode(): boolean {
  return privateMode;
}

export function setPrivateMode(on: boolean): void {
  if (privateMode === on) return;
  privateMode = on;
  for (const listener of privateModeListeners) listener();
}

export function togglePrivateMode(): void {
  setPrivateMode(!privateMode);
}

/** `useSyncExternalStore` subscription for the embed's session state. */
export function subscribePrivateMode(listener: () => void): () => void {
  privateModeListeners.add(listener);
  return () => {
    privateModeListeners.delete(listener);
  };
}

/**
 * Whether the resolved tenant offers private mode at all (`features.privateMode`).
 *
 * Separate from the session flag on purpose: the flag answers "is this session
 * private", this answers "may it ever be". Starts false, so a session painted
 * before the tenant config lands cannot enter the mode, and a tenant that never
 * opted in cannot enter it at all — not from `?private=1`, not from `/private`.
 * Turning availability off also drops a live session flag, or a tenant that
 * stops offering the mode would leave one on for the rest of the session.
 */
let privateModeAvailable = false;

export function isPrivateModeAvailable(): boolean {
  return privateModeAvailable;
}

export function setPrivateModeAvailable(on: boolean): void {
  if (privateModeAvailable === on) return;
  privateModeAvailable = on;
  if (!on) setPrivateMode(false);
}

function themeArgApplies(raw: string): boolean {
  const text = raw.trim().toLowerCase();
  if (!text) return false;
  if (isThemePreference(text)) return true;
  if (text === "default" || isPaletteId(text)) return true;
  const [pal, mode, ...rest] = text.split(/\s+/);
  return (
    rest.length === 0 &&
    (pal === "default" || isPaletteId(pal)) &&
    (mode === "dark" || mode === "light")
  );
}

/**
 * A pane with no resolved option stays open. Typing filters it. Enter must
 * not clear the composer, or the next `/` stacks a second palette.
 * `/mcp new` and `/provider openai` still run: the remainder seeds the editor.
 */
function paneStaysOpen(command: SlashDef, arg: string): boolean {
  if (!commandOpensPane(command)) return false;
  const raw = arg.trim();
  switch (command.id) {
    case "lang":
      return !raw || tryResolveLanguageInput(raw) == null;
    case "effort":
      return !raw || !isEffortCode(raw);
    case "view": {
      if (!raw) return true;
      const mode = raw.toLowerCase();
      return !isViewMode(mode) && !isLegacyViewMode(mode);
    }
    case "density":
      return !raw || !isTraceDensity(raw.toLowerCase());
    case "thinking":
      return !raw || !isThinkingCode(raw);
    case "search-engine":
      return !raw || !isSearchEngine(raw);
    case "theme":
      return !themeArgApplies(raw);
    case "mcp":
    case "byok":
      return !raw;
    default:
      return true;
  }
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
  if (command.kind === "tool") return { kind: "block" };
  // Export serialises the stored messages, which still hold the real text the
  // user typed — handing over exactly what private mode is meant to hide.
  if (isPrivateMode() && command.id === "export") {
    return {
      kind: "block",
      reason: "Export is off in a private session — the stored thread still holds the real text.",
    };
  }
  if (paneStaysOpen(command, arg)) return { kind: "pane", command, arg };
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
    artifacts: api.hasArtifacts,
    theme: api.themeLocked !== true,
  };
}

/** The theme `/theme` reads: the host's own (tenant embed) or the document's. */
export function currentThemeState(api: EmbedChatPrefsApi): ThemeState {
  // The painted palette when the host does not own the theme (a deployment
  // palette is painted, not stored).
  return api.themeState ?? readEffectiveThemeState();
}

/** Apply a `/theme` pick through the host when it owns the theme, else document-wide. */
export function applyThemePick(api: EmbedChatPrefsApi, preference: ThemePreference, palette: string): void {
  if (api.setTheme) api.setTheme(preference, normalizePalette(palette));
  else applyDocumentTheme(preference, palette);
}

function toggleHint(on: boolean, onText: string, offText: string): string {
  return on ? `On · ${onText}` : `Off · ${offText}`;
}

/** Friendly /models hint. Preset tokens stay words; a concrete pick stays its id. */
function modelChoiceLabel(model: string | undefined): string {
  const value = model?.trim() ?? "";
  if (!value) return "";
  if (value === "auto" || value === "preset:auto") return "Auto";
  if (value.startsWith("preset:")) {
    const id = value.slice("preset:".length);
    return id ? id.charAt(0).toUpperCase() + id.slice(1) : "";
  }
  return value;
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

export function buildProductSlashCommands(api: EmbedChatPrefsApi): Unstable_SlashCommand[] {
  const vis = visibilityFromPrefs(api);
  const { prefs } = api;
  const extra = extraSlashDefs(api);
  const rows: Unstable_SlashCommand[] = [];

  for (const def of [...SLASH_COMMANDS, ...extra]) {
    if (def.id === "search-engine" && !vis.webSearch) continue;
    if (def.id === "byok" && vis.byok === false) continue;
    if (def.id === "sessions" && vis.sessions !== true) continue;
    if (def.id === "artifacts" && vis.artifacts !== true) continue;
    if ((def.id === "models" || def.id === "effort") && vis.models === false) continue;
    if (def.id === "mcp" && vis.mcp === false) continue;
    if (def.id === "tools" && vis.tools === false) continue;
    if (def.id === "theme" && vis.theme === false) continue;

    let description = def.hint;
    if (def.id === "view") {
      description = `View: ${prefs.view}`;
    } else if (def.id === "density") {
      description = `Density: ${prefs.density}`;
    } else if (def.id === "theme") {
      const state = currentThemeState(api);
      description = matchThemeStep(state.preference, state.palette, state.resolved).label;
    } else if (def.id === "thinking") {
      description = `Thinking: ${prefs.thinking}`;
    } else if (def.id === "lang") {
      description = `Reply language (${languageLabel(prefs.language)})`;
    } else if (def.id === "models") {
      description = modelChoiceLabel(prefs.model) || def.hint;
    } else if (def.id === "toolbar") {
      description = toggleHint(prefs.toolbar, "visible", "hidden");
    } else if (def.id === "scrollbar") {
      description = prefs.scrollbars === "always" ? "always visible" : "on scroll";
    } else if (def.id === "effort") {
      description = prefs.effort || "medium";
    } else if (def.id === "search-engine") {
      description = prefs.searchEngine || "auto";
    } else if (def.id === "export") {
      description = "Markdown file of this thread";
    }

    const id = def.id === "lang" ? "language" : def.id;
    const insertName = def.id === "export" ? "/export md" : def.names[0];
    rows.push({
      id,
      label: insertName,
      description,
      execute: () => {
        executeSlashDef(def, "", api);
      },
    });
    if (def.id === "export") {
      rows.push({
        id: "export-html",
        label: "/export html",
        description: "Rendered HTML of this chat",
        execute: () => {},
      });
    }
  }

  rows.push(...featuredLanguageCommands(api.setLanguage));
  return rows;
}

/** Direct tool drafts are gone. Pane commands write their sequence themselves. */
export function shouldInsertToolDraft(id: string, extra: readonly SlashDef[]): boolean {
  void id;
  void extra;
  return false;
}

export function executeSlashDef(def: SlashDef, arg: string, api: EmbedChatPrefsApi): void {
  switch (def.id) {
    case "view": {
      const mode = arg.trim().toLowerCase();
      // `hidden` / `compact` / `detailed` are the retired ids; they fold
      // forward. The live ids come from the app's own contract
      // (`@/lib/view-modes.ts`), the one that owns them.
      if (isViewMode(mode)) api.setView(mode);
      else if (isLegacyViewMode(mode)) api.setView(normalizeViewMode(mode));
      else api.openView();
      return;
    }
    case "density": {
      const raw = arg.trim().toLowerCase();
      if (isTraceDensity(raw)) api.setDensity(raw);
      else api.openDensity();
      return;
    }
    case "theme": {
      if (api.themeLocked) return;
      const raw = arg.trim().toLowerCase();
      if (!raw) {
        api.openTheme?.();
        return;
      }
      // The painted palette, so `/theme light` keeps a deployment palette the
      // picker and the row description already show (not storage alone).
      const state = currentThemeState(api);
      if (isThemePreference(raw)) {
        // A host-owned theme (embed) takes the pick; the app changes the mode
        // and keeps the painted palette without freezing it into dt-palette.
        if (api.setTheme) applyThemePick(api, raw, state.palette);
        else applyThemeModeKeepingPalette(raw);
        return;
      }
      if (raw === "default" || isPaletteId(raw)) {
        applyThemePick(api, state.preference, raw);
        return;
      }
      // The picker rows read "/theme <palette> <mode>"; typing one applies it.
      const [pal, mode, ...rest] = raw.split(/\s+/);
      if (
        rest.length === 0 &&
        (pal === "default" || isPaletteId(pal)) &&
        (mode === "dark" || mode === "light")
      ) {
        applyThemePick(api, mode, pal);
        return;
      }
      api.openTheme?.();
      return;
    }
    case "thinking": {
      const mode = arg.trim().toLowerCase();
      if (isThinkingCode(mode)) api.setThinking(mode);
      else api.openThinking();
      return;
    }
    case "private":
      // A session flag, not a turn: flips the mode and sends nothing. A tenant
      // that did not opt in has no mode to flip, so the command does nothing
      // even if a stale definition or a typed value reaches this far.
      if (!privateModeAvailable) return;
      togglePrivateMode();
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
    case "toolbar":
      api.setToolbar(!api.prefs.toolbar);
      return;
    case "scrollbar":
      api.setScrollbars(api.prefs.scrollbars === "always" ? "auto" : "always");
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
    case "search-engine": {
      if (!arg) {
        api.openSearchEngine();
        return;
      }
      const value = arg.trim().toLowerCase();
      if (isSearchEngine(value)) api.setSearchEngine(value);
      return;
    }
    case "sessions":
      api.openSessions();
      return;
    case "artifacts":
      api.openArtifacts();
      return;
    case "help":
      api.openHelp();
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
      return;
  }
}

export function executeSlashFromComposer(
  id: "lang" | "effort" | "search-engine" | "byok" | "mcp" | "tools",
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

export { SLASH_CATEGORIES };
