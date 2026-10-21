// @vitest-environment happy-dom
import { SLASH_COMMANDS } from "@digithings/digichat-ui";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_EMBED_CHAT_PREFS, type EmbedChatPrefsApi } from "@digithings/ui/chat/stock";
import { buildProductSlashCommands, executeSlashDef } from "./product-slash-commands";

function api(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: vi.fn(),
    setDigisearch: vi.fn(),
    setVault: vi.fn(),
    setExtraTool: vi.fn(),
    extraToolOn: () => true,
    setMcpConfig: vi.fn(),
    removeMcpConfig: vi.fn(),
    setLanguage: vi.fn(),
    setView: vi.fn(),
    setThinking: vi.fn(),
    setModel: vi.fn(),
    setEffort: vi.fn(),
    setSearchEngine: vi.fn(),
    setToolbar: vi.fn(),
    setScrollbars: vi.fn(),
    setDensity: vi.fn(),
    reset: vi.fn(),
    tenantAllowsWeb: true,
    showByok: true,
    showModels: true,
    hasDigisearch: true,
    hasVault: true,
    hasSessions: false,
    hasArtifacts: false,
    allowUserMcp: false,
    allowAddMcp: false,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "host",
    openSettings: vi.fn(),
    openHelp: vi.fn(),
    openTools: vi.fn(),
    openMcp: vi.fn(),
    openByok: vi.fn(),
    openModels: vi.fn(),
    openEffort: vi.fn(),
    openSearchEngine: vi.fn(),
    openView: vi.fn(),
    openDensity: vi.fn(),
    openThinking: vi.fn(),
    openLanguage: vi.fn(),
    openSessions: vi.fn(),
    openArtifacts: vi.fn(),
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    ...over,
  };
}

const theme = SLASH_COMMANDS.find((command) => command.id === "theme");

describe("/theme", () => {
  beforeEach(() => {
    // happy-dom's storage is not usable under every Node (a recent Node ships
    // its own `localStorage` global that shadows it), so stub a Map-backed one,
    // the same way web-search-pref.test.ts does.
    const store = new Map<string, string>();
    vi.stubGlobal("localStorage", {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, String(v)),
      removeItem: (k: string) => void store.delete(k),
      clear: () => store.clear(),
      key: (i: number) => [...store.keys()][i] ?? null,
      get length() {
        return store.size;
      },
    });
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-palette");
    window.matchMedia = () =>
      ({
        matches: false,
        media: "(prefers-color-scheme: light)",
        addEventListener: () => {},
        removeEventListener: () => {},
      }) as unknown as MediaQueryList;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sets mode and palette, and auto keeps the palette key", () => {
    expect(theme).toBeTruthy();
    const prefs = api();
    executeSlashDef(theme!, "dark", prefs);
    expect(localStorage.getItem("dt-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    executeSlashDef(theme!, "dracula", prefs);
    expect(localStorage.getItem("dt-palette")).toBe("dracula");
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
    expect(localStorage.getItem("dt-theme")).toBe("dark");
    executeSlashDef(theme!, "auto", prefs);
    expect(localStorage.getItem("dt-theme")).toBeNull();
    expect(localStorage.getItem("dt-palette")).toBe("dracula");
    executeSlashDef(theme!, "default", prefs);
    expect(localStorage.getItem("dt-palette")).toBeNull();
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
  });

  it("applies a picker row typed as /theme <palette> <mode>", () => {
    const prefs = api({});
    executeSlashDef(theme!, "aura light", prefs);
    expect(document.documentElement.getAttribute("data-palette")).toBe("aura");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    executeSlashDef(theme!, "default dark", prefs);
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });

  it("keeps a deployment palette when only the mode is typed", () => {
    // Painted by the deployment (no stored dt-palette), as the picker shows it.
    document.documentElement.setAttribute("data-palette", "dracula");
    executeSlashDef(theme!, "light", api());
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    // The mode is stored; the deployment's palette is not frozen into storage.
    expect(localStorage.getItem("dt-theme")).toBe("light");
    expect(localStorage.getItem("dt-palette")).toBeNull();
  });

  it("keeps a stored palette choice when only the mode is typed", () => {
    localStorage.setItem("dt-palette", "aura");
    document.documentElement.setAttribute("data-palette", "aura");
    executeSlashDef(theme!, "dark", api());
    expect(localStorage.getItem("dt-palette")).toBe("aura");
    expect(document.documentElement.getAttribute("data-palette")).toBe("aura");
  });

  it("opens the picker for an empty or unknown argument", () => {
    const openTheme = vi.fn();
    executeSlashDef(theme!, "", api({ openTheme }));
    executeSlashDef(theme!, "nope", api({ openTheme }));
    expect(openTheme).toHaveBeenCalledTimes(2);
  });

  it("hides the command and ignores it when the embed pins the theme", () => {
    const openTheme = vi.fn();
    const locked = api({ themeLocked: true, openTheme });
    expect(buildProductSlashCommands(locked).map((row) => row.id)).not.toContain("theme");
    localStorage.setItem("dt-theme", "light");
    executeSlashDef(theme!, "dark", locked);
    expect(localStorage.getItem("dt-theme")).toBe("light");
    expect(openTheme).not.toHaveBeenCalled();
  });
});
