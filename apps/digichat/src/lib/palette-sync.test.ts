import { describe, expect, it } from "vitest";
import {
  applyPaletteFrame,
  matchingSlashCommands,
  optionDraft,
  paletteFrame,
  paletteSurfaces,
  paneDraftForId,
  parseSlashInput,
  SLASH_COMMANDS,
} from "@digithings/digichat-ui";
import { extraSlashDefs, slashSubmitAction } from "./product-slash-commands";
import { DEFAULT_EMBED_CHAT_PREFS, type EmbedChatPrefsApi } from "@digithings/ui/chat/stock";

function api(): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: () => {},
    setDigisearch: () => {},
    setVault: () => {},
    setExtraTool: () => {},
    extraToolOn: () => true,
    setMcpConfig: () => {},
    removeMcpConfig: () => {},
    setLanguage: () => {},
    setView: () => {},
    setThinking: () => {},
    setModel: () => {},
    setEffort: () => {},
    setSearchEngine: () => {},
    setToolbar: () => {},
    setScrollbars: () => {},
    setDensity: () => {},
    reset: () => {},
    tenantAllowsWeb: true,
    showByok: true,
    showModels: true,
    hasDigisearch: true,
    hasVault: true,
    hasSessions: false,
    hasArtifacts: false,
    allowUserMcp: true,
    allowAddMcp: true,
    catalogTools: [
      { id: "digisearch", label: "Search" },
      { id: "datatap", label: "DataTap" },
    ],
    mcpServers: [{ id: "zammad", label: "Zammad tickets" }],
    sessionKey: "t",
    openSettings: () => {},
    openHelp: () => {},
    openTools: () => {},
    openMcp: () => {},
    openByok: () => {},
    openModels: () => {},
    openEffort: () => {},
    openSearchEngine: () => {},
    openView: () => {},
    openDensity: () => {},
    openThinking: () => {},
    openLanguage: () => {},
    openSessions: () => {},
    openArtifacts: () => {},
    newThread: () => {},
    compactThread: () => {},
    undo: () => {},
    redo: () => {},
  };
}

describe("one palette", () => {
  it("does not open a second palette on top of a pane", () => {
    expect(paletteSurfaces("/language ")).toEqual({ slash: false, menu: "language" });
    expect(paletteSurfaces("/language /")).toEqual({ slash: false, menu: "language" });
    expect(paletteSurfaces("/theme default dark")).toEqual({ slash: false, menu: "theme" });
    expect(paletteSurfaces("/")).toEqual({ slash: true, menu: null });
    for (const text of ["/", "/language", "/language ", "/language /", "/theme "]) {
      const surfaces = paletteSurfaces(text);
      expect(Number(surfaces.slash) + Number(surfaces.menu != null)).toBeLessThanOrEqual(1);
    }
  });

  it("syncs /language and /theme with the composer", () => {
    expect(paneDraftForId("language")).toBe("/language ");
    expect(paneDraftForId("theme")).toBe("/theme ");
    expect(optionDraft("/language", "English")).toBe("/language English");
    expect(paletteFrame("/language")).toMatchObject({ kind: "commands" });
    expect(paletteFrame("/language English")).toMatchObject({
      kind: "pane",
      menu: "language",
      filter: "English",
    });
    expect(paletteFrame("/theme ")).toMatchObject({ kind: "pane", menu: "theme", filter: "" });
    expect(applyPaletteFrame("pane", paletteFrame("/theme"))).toEqual({
      kind: "commands",
      menu: "close",
      filter: "",
    });
    expect(slashSubmitAction("/language ")).toMatchObject({ kind: "pane" });
    expect(slashSubmitAction("/language English")).toMatchObject({ kind: "run" });
    expect(slashSubmitAction("/theme dark")).toMatchObject({ kind: "run" });
  });

  it("drops direct tool commands from the palette", () => {
    const ids = matchingSlashCommands("/", { webSearch: true }).map((command) => command.id);
    expect(ids).not.toContain("digisearch");
    expect(ids).not.toContain("digivault");
    expect(ids).not.toContain("websearch");
    expect(ids).toContain("tools");
    expect(SLASH_COMMANDS.map((command) => command.id)).not.toContain("digisearch");
    expect(parseSlashInput("/digisearch").kind).toBe("unknown");
    expect(parseSlashInput("/zammad").kind).toBe("unknown");
    expect(extraSlashDefs(api())).toEqual([]);
    expect(slashSubmitAction("/datatap")).toEqual({ kind: "block" });
  });
});
