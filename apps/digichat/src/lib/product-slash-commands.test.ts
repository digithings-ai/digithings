import { afterEach, describe, expect, it, vi } from "vitest";
import { SLASH_COMMANDS, slashHelpText } from "@digithings/digichat-ui";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";
import { emptyMcpConfig } from "@/components/stock/embed-mcp-flow";
import {
  buildProductSlashCommands,
  catalogForceTool,
  executeSlashDef,
  extraSlashDefs,
  isPrivateMode,
  isPrivateModeAvailable,
  languageSelectOptions,
  prefixSlashAdapter,
  privateModeHeaderEntries,
  seedPrivateMode,
  setPrivateMode,
  setPrivateModeAvailable,
  slashItemPrefixMatch,
  slashSubmitAction,
  tenantLanguageCodes,
} from "./product-slash-commands";

function api(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS },
    setWebSearch: vi.fn(),
    setDigisearch: vi.fn(),
    setVault: vi.fn(),
    setExtraTool: vi.fn(),
    extraToolOn: (id) => over.prefs?.extra?.[id] !== false,
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
    catalogTools: [
      { id: "digisearch", label: "Search" },
      { id: "digivault", label: "Vault" },
      { id: "web_search", label: "Web search" },
    ],
    mcpServers: [],
    sessionKey: "embed-host",
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

describe("slashSubmitAction", () => {
  it("blocks direct tool commands", () => {
    expect(slashSubmitAction("/digisearch RS256")).toEqual({ kind: "block" });
    expect(slashSubmitAction("/digivault")).toEqual({ kind: "block" });
    expect(slashSubmitAction("/websearch latest filings")).toEqual({ kind: "block" });
    expect(slashSubmitAction("/desk")).toEqual({ kind: "block" });
    expect(slashSubmitAction("/records pipeline status")).toEqual({ kind: "block" });
  });

  it("keeps a pane command in the composer until the option resolves", () => {
    expect(slashSubmitAction("/language ")).toMatchObject({ kind: "pane", command: { id: "lang" } });
    expect(slashSubmitAction("/language English")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "English",
    });
    expect(slashSubmitAction("/theme ")).toMatchObject({ kind: "pane", command: { id: "theme" } });
    expect(slashSubmitAction("/theme dark")).toMatchObject({
      kind: "run",
      command: { id: "theme" },
      arg: "dark",
    });
    expect(slashSubmitAction("/tools Search")).toMatchObject({ kind: "pane" });
  });

  it("runs /language dutch as a client command", () => {
    expect(slashSubmitAction("/language dutch")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "dutch",
    });
    expect(slashSubmitAction("/language en")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "en",
    });
    expect(slashSubmitAction("/language Italiano")).toMatchObject({
      kind: "run",
      command: { id: "lang" },
      arg: "Italiano",
    });
  });

  it("passes ordinary text through", () => {
    expect(slashSubmitAction("how does auth work")).toEqual({ kind: "pass" });
  });

  it("blocks unknown slash lines instead of sending them", () => {
    expect(slashSubmitAction("/not-a-command")).toEqual({ kind: "block" });
  });

  it("does not treat a slashHelpText dump as a command", () => {
    const help = slashHelpText({ webSearch: true, byok: true });
    expect(help).not.toContain("/digisearch");
    expect(slashSubmitAction(help)).toEqual({ kind: "block" });
  });
});

describe("catalogForceTool", () => {
  it("maps vault locate onto the BFF catalog id", () => {
    expect(catalogForceTool("digivault_search_notes")).toBe("digivault");
    expect(catalogForceTool("digisearch")).toBe("digisearch");
    expect(catalogForceTool("records")).toBe("records");
  });
});

describe("buildProductSlashCommands", () => {
  it("includes catalog tools, mcp, models, and featured languages without per-row icons", () => {
    const cmds = buildProductSlashCommands(api({ allowUserMcp: true }));
    const ids = cmds.map((c) => c.id);
    expect(ids).not.toContain("websearch");
    expect(ids).not.toContain("digisearch");
    expect(ids).not.toContain("digivault");
    expect(ids).toContain("mcp");
    expect(ids).toContain("models");
    expect(ids).toContain("dutch");
    expect(ids).toContain("language");
    expect(ids).not.toContain("search");
    expect(ids).not.toContain("toggle-digisearch");
    expect(cmds.every((c) => !("icon" in c) || c.icon == null)).toBe(true);
  });

  it("hides catalog/MCP commands when the install has no tools", () => {
    const ids = buildProductSlashCommands(
      api({
        tenantAllowsWeb: false,
        showByok: false,
        showModels: false,
        hasDigisearch: false,
        hasVault: false,
        allowUserMcp: false,
        catalogTools: [],
        mcpServers: [],
      }),
    ).map((c) => c.id);
    expect(ids).not.toContain("digisearch");
    expect(ids).not.toContain("digivault");
    expect(ids).not.toContain("websearch");
    expect(ids).not.toContain("mcp");
    expect(ids).not.toContain("tools");
    expect(ids).not.toContain("models");
    expect(ids).toContain("language");
    expect(ids).toContain("thinking");
  });

  it("does not add a slash command per catalog tool", () => {
    const ids = buildProductSlashCommands(
      api({ catalogTools: [{ id: "records", label: "Records" }] }),
    ).map((c) => c.id);
    expect(ids).not.toContain("records");
    expect(ids).toContain("tools");
  });

  it("lists one /export row whose pane offers Markdown (.md) and HTML (.html)", () => {
    const rows = buildProductSlashCommands(api());
    const exportRows = rows.filter((c) => c.id.startsWith("export"));
    expect(exportRows.map((c) => c.id)).toEqual(["export"]);
    expect(exportRows[0]?.label).toBe("/export");
    const def = SLASH_COMMANDS.find((d) => d.id === "export");
    expect(def?.choiceOptions?.map((o) => [o.value, o.label])).toEqual([
      ["md", "Markdown (.md)"],
      ["html", "HTML (.html)"],
    ]);
    // Bare /export opens the format pane instead of guessing a format.
    expect(slashSubmitAction("/export")).toMatchObject({ kind: "pane", command: { id: "export" } });
    expect(slashSubmitAction("/export pdf")).toMatchObject({ kind: "pane" });
    for (const [typed, arg] of [
      ["/export md", "md"],
      ["/export markdown", "markdown"],
      ["/export html", "html"],
    ] as const) {
      expect(slashSubmitAction(typed)).toMatchObject({
        kind: "run",
        command: { id: "export" },
        arg,
      });
    }
  });

  it("runs the bound conversation export with the chosen format", () => {
    const exportThread = vi.fn();
    const a = api({ exportThread });
    const def = { id: "export" as const, names: ["/export"], needsArg: false, hint: "" };
    executeSlashDef(def, "md", a);
    executeSlashDef(def, " HTML ", a);
    executeSlashDef(def, "markdown", a);
    executeSlashDef(def, "pdf", a);
    expect(exportThread.mock.calls).toEqual([["md"], ["html"], ["md"]]);
  });
});

describe("slashItemPrefixMatch", () => {
  it("does not treat /se as a match for /digisearch", () => {
    expect(slashItemPrefixMatch({ id: "digisearch", label: "/digisearch" }, "search")).toBe(
      false,
    );
    expect(
      slashItemPrefixMatch({ id: "digisearch", label: "/digisearch" }, "digi"),
    ).toBe(true);
  });
});

describe("prefixSlashAdapter", () => {
  it("filters the inner search with prefix match and does not add categories", () => {
    const inner = {
      categories: () => [{ id: "tools", label: "Tools" }],
      search: (_query: string) => [
        { id: "settings", label: "/settings" },
        { id: "digisearch", label: "/digisearch" },
      ],
    };
    const wrapped = prefixSlashAdapter(inner);
    expect(wrapped.search("se").map((i) => i.id)).toEqual(["settings"]);
    expect(wrapped.categories()).toEqual([]);
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

  it("opens the help panel on /help without touching tools", () => {
    const a = api();
    const def = { id: "help" as const, names: ["/help"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openHelp).toHaveBeenCalledOnce();
    expect(a.openSettings).not.toHaveBeenCalled();
    expect(a.setDigisearch).not.toHaveBeenCalled();
  });

  it("opens the language list on empty /language and sets from code, English, or autonym", () => {
    const a = api();
    const def = { id: "lang" as const, names: ["/language", "/lang"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openLanguage).toHaveBeenCalledOnce();
    executeSlashDef(def, "en", a);
    expect(a.setLanguage).toHaveBeenCalledWith("en");
    executeSlashDef(def, "Italiano", a);
    expect(a.setLanguage).toHaveBeenCalledWith("it");
    executeSlashDef(def, "espanol", a);
    expect(a.setLanguage).toHaveBeenCalledWith("es");
  });

  it("keeps /language to the tenant's languages when a list is set, unchanged when unset", () => {
    const def = { id: "lang" as const, names: ["/language", "/lang"], needsArg: false, hint: "" };
    const fenced = api({
      languageOptions: [
        { code: "en", short: "EN", label: "English" },
        { code: "fr", short: "FR", label: "Français" },
      ],
    });
    executeSlashDef(def, "fr", fenced);
    expect(fenced.setLanguage).toHaveBeenCalledWith("fr");
    executeSlashDef(def, "dutch", fenced);
    expect(fenced.setLanguage).not.toHaveBeenCalledWith("nl");
    expect(fenced.openLanguage).toHaveBeenCalledOnce();
    expect(languageSelectOptions(tenantLanguageCodes(fenced)).map((o) => o.value)).toEqual([
      "en",
      "fr",
    ]);
    const ids = buildProductSlashCommands(fenced).map((c) => c.id);
    expect(ids).toContain("language");
    expect(ids).not.toContain("dutch");

    const open = api();
    expect(tenantLanguageCodes(open)).toBeNull();
    expect(languageSelectOptions(tenantLanguageCodes(open))).toEqual(languageSelectOptions());
    executeSlashDef(def, "dutch", open);
    expect(open.setLanguage).toHaveBeenCalledWith("nl");
    expect(buildProductSlashCommands(open).map((c) => c.id)).toContain("dutch");
  });

  it("keeps a single-language tenant on its language for typed /language", () => {
    const def = { id: "lang" as const, names: ["/language", "/lang"], needsArg: false, hint: "" };
    const one = api({ allowedLanguages: ["fr"] });
    expect(tenantLanguageCodes(one)).toEqual(["fr"]);
    expect(languageSelectOptions(tenantLanguageCodes(one)).map((o) => o.value)).toEqual(["fr"]);
    executeSlashDef(def, "en", one);
    expect(one.setLanguage).not.toHaveBeenCalled();
    expect(one.openLanguage).toHaveBeenCalledOnce();
    expect(buildProductSlashCommands(one).map((c) => c.id)).not.toContain("dutch");
  });

  it("opens /provider and seeds a provider from the remainder", () => {
    const a = api();
    const def = { id: "byok" as const, names: ["/provider", "/byok", "/key"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openByok).toHaveBeenCalledWith("");
    executeSlashDef(def, "openai", a);
    expect(a.openByok).toHaveBeenCalledWith("openai");
  });

  it("opens the MCP server menu on /mcp and seeds /mcp new", () => {
    const a = api();
    const def = { id: "mcp" as const, names: ["/mcp"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openMcp).toHaveBeenCalledWith("");
    executeSlashDef(def, "new", a);
    expect(a.openMcp).toHaveBeenCalledWith("new");
  });

  it("opens the search-engine list on empty /search-engine and sets a known engine", () => {
    const a = api();
    const def = { id: "search-engine" as const, names: ["/search-engine"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openSearchEngine).toHaveBeenCalledOnce();
    executeSlashDef(def, "exa", a);
    expect(a.setSearchEngine).toHaveBeenCalledWith("exa");
    executeSlashDef(def, "not-an-engine", a);
    expect(a.setSearchEngine).toHaveBeenCalledTimes(1);
  });

  it("opens the connected-tools menu on /tools", () => {
    const a = api();
    const def = { id: "tools" as const, names: ["/tools"], needsArg: false, hint: "" };
    executeSlashDef(def, "", a);
    expect(a.openTools).toHaveBeenCalledOnce();
  });

  it("keeps /view on the three levels and folds the retired hidden one", () => {
    const a = api();
    const def = { id: "view" as const, names: ["/view"], needsArg: false, hint: "" };
    executeSlashDef(def, "verbose", a);
    expect(a.setView).toHaveBeenCalledWith("verbose");
    // A stale invocation still says `hidden`; it means the titles only.
    executeSlashDef(def, "hidden", a);
    expect(a.setView).toHaveBeenLastCalledWith("quiet");
    executeSlashDef(def, "nonsense", a);
    expect(a.openView).toHaveBeenCalledOnce();
  });

  it("sets /density from the three rhythms and opens the page otherwise", () => {
    const a = api();
    const def = { id: "density" as const, names: ["/density"], needsArg: false, hint: "" };
    executeSlashDef(def, "compact", a);
    expect(a.setDensity).toHaveBeenCalledWith("compact");
    executeSlashDef(def, "Airy", a);
    expect(a.setDensity).toHaveBeenLastCalledWith("airy");
    executeSlashDef(def, "roomy", a);
    expect(a.openDensity).toHaveBeenCalledOnce();
  });

  it("does not expose catalog or session MCP ids as slash commands", () => {
    expect(
      extraSlashDefs(
        api({
          catalogTools: [{ id: "digisearch" }],
          mcpServers: [{ id: "records", label: "Records" }],
        }),
      ),
    ).toEqual([]);
    expect(
      extraSlashDefs(
        api({
          catalogTools: [],
          mcpServers: [],
          prefs: {
            ...DEFAULT_EMBED_CHAT_PREFS,
            mcpCustom: [{ ...emptyMcpConfig(), id: "linear", label: "Linear" }],
          },
        }),
      ),
    ).toEqual([]);
  });
});

describe("/artifacts", () => {
  const ids = (over: Partial<EmbedChatPrefsApi> = {}) =>
    buildProductSlashCommands(api(over)).map((c) => c.id);

  it("lists /artifacts when the session has an artifact surface", () => {
    const listed = ids({ hasArtifacts: true });
    // Guards the "passes only because the list is empty" trap: one visible row.
    expect(listed.length).toBeGreaterThan(0);
    expect(listed).toContain("artifacts");
  });

  it("hides /artifacts when there is no artifact surface", () => {
    // Same api as the test above with one field flipped, so a listing that is
    // empty for an unrelated reason cannot pass the previous test.
    expect(ids({ hasArtifacts: false })).not.toContain("artifacts");
  });

  it("opens the artifact list on selection", () => {
    const a = api({ hasArtifacts: true });
    executeSlashDef(
      {
        id: "artifacts",
        names: ["/artifacts"],
        needsArg: false,
        hint: "",
        kind: "action",
      },
      "",
      a,
    );
    expect(a.openArtifacts).toHaveBeenCalledTimes(1);
  });
});

describe("/toolbar and /scrollbar", () => {
  const chrome = (prefs: Partial<EmbedChatPrefsApi["prefs"]> = {}) =>
    api({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, toolbar: true, scrollbars: "always", ...prefs } });

  it("lists both commands in the product palette", () => {
    const ids = buildProductSlashCommands(chrome()).map((c) => c.id);
    expect(ids.length).toBeGreaterThan(0);
    expect(ids).toContain("toolbar");
    expect(ids).toContain("scrollbar");
  });

  it("puts the current values in the value column", () => {
    const on = new Map(buildProductSlashCommands(chrome()).map((c) => [c.id, c]));
    expect(on.get("toolbar")?.value).toBe("on");
    expect(on.get("toolbar")?.description).toBe("Show or hide the composer toolbar.");
    expect(on.get("scrollbar")?.value).toBe("always");
    expect(on.get("scrollbar")?.description).toBe(
      "Show scrollbars always or while scrolling.",
    );

    const off = new Map(
      buildProductSlashCommands(chrome({ toolbar: false, scrollbars: "auto" })).map((c) => [
        c.id,
        c,
      ]),
    );
    expect(off.get("toolbar")?.value).toBe("off");
    expect(off.get("scrollbar")?.value).toBe("auto");
  });

  it("flips the visible toolbar off", () => {
    const a = chrome();
    executeSlashDef({ id: "toolbar", names: ["/toolbar"], needsArg: false, hint: "" }, "", a);
    expect(a.setToolbar).toHaveBeenCalledOnce();
    expect(a.setToolbar).toHaveBeenCalledWith(false);
  });

  it("flips always scrollbars to on-scroll", () => {
    const a = chrome();
    executeSlashDef({ id: "scrollbar", names: ["/scrollbar"], needsArg: false, hint: "" }, "", a);
    expect(a.setScrollbars).toHaveBeenCalledOnce();
    expect(a.setScrollbars).toHaveBeenCalledWith("auto");
  });

  it("runs the same flip from the palette row", () => {
    const a = chrome();
    const row = buildProductSlashCommands(a).find((c) => c.id === "toolbar");
    expect(row).toBeDefined();
    row?.execute?.();
    expect(a.setToolbar).toHaveBeenCalledWith(false);
  });
});

describe("private mode availability", () => {
  const def = { id: "private" as const, names: ["/private"], needsArg: false, hint: "" };

  afterEach(() => {
    setPrivateModeAvailable(false);
    setPrivateMode(false);
  });

  it("ignores /private when the tenant did not opt in", () => {
    executeSlashDef(def, "", api());
    expect(isPrivateModeAvailable()).toBe(false);
    expect(isPrivateMode()).toBe(false);
    expect(slashSubmitAction("/export md")).toMatchObject({ kind: "run" });
  });

  it("toggles once the tenant opts in, and export stays blocked while private", () => {
    setPrivateModeAvailable(true);
    executeSlashDef(def, "", api());
    expect(isPrivateMode()).toBe(true);
    expect(slashSubmitAction("/export")).toMatchObject({ kind: "block" });
    expect(slashSubmitAction("/export md")).toMatchObject({ kind: "block" });
  });

  it("turns on from ?private=1 only when the tenant opted in", () => {
    seedPrivateMode({ tenantOptIn: true, urlPrivate: true });
    expect(isPrivateModeAvailable()).toBe(true);
    expect(isPrivateMode()).toBe(true);
    expect(privateModeHeaderEntries(isPrivateMode())).toEqual(["X-Digi-Private", "1"]);

    seedPrivateMode({ tenantOptIn: false, urlPrivate: true });
    expect(isPrivateMode()).toBe(false);
    expect(privateModeHeaderEntries(isPrivateMode())).toBeNull();

    seedPrivateMode({ tenantOptIn: true, urlPrivate: false });
    expect(isPrivateModeAvailable()).toBe(true);
    expect(isPrivateMode()).toBe(false);
  });

  it("toggles /private off and on, and the palette value follows", () => {
    seedPrivateMode({ tenantOptIn: true, urlPrivate: true });
    executeSlashDef(def, "", api());
    expect(isPrivateMode()).toBe(false);
    expect(buildProductSlashCommands(api()).find((c) => c.id === "private")?.value).toBe("off");
    executeSlashDef(def, "", api());
    expect(isPrivateMode()).toBe(true);
    const row = buildProductSlashCommands(api()).find((c) => c.id === "private");
    expect(row?.label).toBe("/private");
    expect(row?.value).toBe("on");
    expect(row?.description).toBe("Ask the model to use stand-in names in its replies.");
  });

  it("hides /private until the tenant opts in", () => {
    seedPrivateMode({ tenantOptIn: false, urlPrivate: true });
    expect(buildProductSlashCommands(api()).some((c) => c.id === "private")).toBe(false);
  });

  it("puts the current value back on the typeahead row", () => {
    seedPrivateMode({ tenantOptIn: true, urlPrivate: true });
    buildProductSlashCommands(api());
    const wrapped = prefixSlashAdapter({
      search: () => [{ id: "private", label: "private", description: "sentence." }],
    });
    expect(wrapped.search?.("pri")).toEqual([
      {
        id: "private",
        label: "private",
        description: "sentence.",
        metadata: { value: "on" },
      },
    ]);
  });

  it("drops a live session flag when the tenant stops offering the mode", () => {
    setPrivateModeAvailable(true);
    setPrivateMode(true);
    setPrivateModeAvailable(false);
    expect(isPrivateModeAvailable()).toBe(false);
    expect(isPrivateMode()).toBe(false);
    expect(slashSubmitAction("/export md")).toMatchObject({ kind: "run" });
  });
});
