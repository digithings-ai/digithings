import { describe, expect, it, vi } from "vitest";
import { parseSlashInput } from "@digithings/digichat-ui";
import { DEFAULT_EMBED_CHAT_PREFS, type EmbedChatPrefsApi } from "@/components/stock/embed-chat-prefs";
import {
  buildProductSlashCommands,
  catalogForceTool,
  executeSlashDef,
  slashSubmitAction,
} from "./product-slash-commands";

function api(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: vi.fn(),
    setDigisearch: vi.fn(),
    setVault: vi.fn(),
    setLanguage: vi.fn(),
    reset: vi.fn(),
    tenantAllowsWeb: true,
    showByok: true,
    hasDigisearch: true,
    hasVault: true,
    sessionKey: "embed-host",
    openSettings: vi.fn(),
    openByok: vi.fn(),
    newThread: vi.fn(),
    ...over,
  };
}

describe("slashSubmitAction", () => {
  it("forces /search and /vault with the remainder as the user message", () => {
    expect(slashSubmitAction("/search RS256")).toEqual({
      kind: "force",
      forceTool: "digisearch",
      text: "RS256",
    });
    expect(slashSubmitAction("/vault notes")).toEqual({
      kind: "force",
      forceTool: "digivault",
      text: "notes",
    });
  });

  it("blocks empty /search instead of sending", () => {
    expect(slashSubmitAction("/search")).toEqual({ kind: "block" });
  });

  it("runs /language dutch as a client command", () => {
    expect(slashSubmitAction("/language dutch")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "dutch",
    });
  });

  it("passes ordinary text through", () => {
    expect(slashSubmitAction("how does auth work")).toEqual({ kind: "pass" });
  });

  it("blocks unknown slash lines instead of sending them", () => {
    expect(slashSubmitAction("/not-a-command")).toEqual({ kind: "block" });
  });
});

describe("catalogForceTool", () => {
  it("maps vault locate onto the BFF catalog id", () => {
    expect(catalogForceTool("digivault_search_notes")).toBe("digivault");
    expect(catalogForceTool("digisearch")).toBe("digisearch");
  });
});

describe("buildProductSlashCommands", () => {
  it("includes toggles, force commands, and featured languages", () => {
    const cmds = buildProductSlashCommands(api());
    const ids = cmds.map((c) => c.id);
    expect(ids).toContain("websearch");
    expect(ids).toContain("digisearch");
    expect(ids).toContain("search");
    expect(ids).toContain("dutch");
    expect(ids).toContain("language");
  });

  it("hides websearch when the tenant disallows it", () => {
    const ids = buildProductSlashCommands(api({ tenantAllowsWeb: false })).map((c) => c.id);
    expect(ids).not.toContain("websearch");
  });

  it("still parses /digisearch as a toggle", () => {
    expect(parseSlashInput("/digisearch")).toMatchObject({
      kind: "command",
      command: { id: "toggle-digisearch" },
    });
  });
});

describe("executeSlashDef", () => {
  it("resets prefs and starts a new thread on /new", () => {
    const a = api();
    const def = { id: "new" as const, names: ["/new"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.reset).toHaveBeenCalledOnce();
    expect(a.newThread).toHaveBeenCalledOnce();
  });
});
