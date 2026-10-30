// @vitest-environment happy-dom
"use client";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  EmbedComposerMenu,
  cursorOnCurrentRow,
  buildModelPathTree,
  type MenuRow,
} from "./embed-composer-menu";
import { VIEW_MODES } from "@/lib/view-modes";
import { VIEW_LABELS } from "@digithings/digichat-ui";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";
import { resolveModelCatalog } from "@/lib/model-picker-catalog";

/** Navigated row: marked by data-cursor (the lighter wash); no chevron glyph on any row. */
function isCursorRow(row: HTMLElement): boolean {
  expect(row.querySelector(".aui-menu-cursor")).toBeNull();
  return row.getAttribute("data-cursor") === "true";
}

/** Configured value: the 3x3 cube diamond on the right. */
function hasDiamond(row: HTMLElement): boolean {
  return row.querySelector("[data-slot='dropdown-menu-radio-item-indicator']") !== null;
}

function prefs(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "alpha" },
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
    allowUserMcp: true,
    allowAddMcp: true,
    catalogTools: [],
    mcpServers: [],
    sessionKey: "t",
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
    newThread: vi.fn(),
    compactThread: vi.fn(),
    undo: vi.fn(),
    redo: vi.fn(),
    ...over,
  };
}

function mountHost() {
  const wrap = document.createElement("div");
  wrap.setAttribute("data-thread-skin", "digichat");
  wrap.setAttribute("data-picker-test-host", "true");
  wrap.innerHTML = `<div class="aui-composer-root"></div>`;
  document.body.appendChild(wrap);
}

describe("EmbedComposerMenu exclusive pickers", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.querySelector("[data-picker-test-host]")?.remove();
  });

  it("applies a model on click and stays open; selected row uses the diamond, not on", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    const selected = await screen.findByRole("menuitemradio", { name: "alpha" });
    expect(selected).toHaveAttribute("aria-checked", "true");
    expect(selected.textContent).not.toMatch(/\bon\b/i);
    // The cursor row always carries the cursor wash; a checked row also keeps its
    // diamond on the right, so the two marks never share a side.
    expect(isCursorRow(selected)).toBe(true);
    expect(hasDiamond(selected)).toBe(true);

    const other = screen.getByRole("menuitemradio", { name: "beta" });
    expect(isCursorRow(other)).toBe(false);
    expect(hasDiamond(other)).toBe(false);

    // The cursor wash follows hover / arrow keys; the configured value keeps its
    // diamond, so the two marks mean different things.
    await user.hover(other);
    expect(isCursorRow(other)).toBe(true);
    expect(isCursorRow(selected)).toBe(false);
    expect(hasDiamond(selected)).toBe(true);
    expect(hasDiamond(other)).toBe(false);

    // Navigating back to the checked row restores the cursor wash beside the
    // diamond; the diamond still marks the configured value.
    await user.hover(selected);
    expect(isCursorRow(selected)).toBe(true);
    expect(hasDiamond(selected)).toBe(true);

    await user.click(other);
    expect(api.setModel).toHaveBeenCalledWith("beta");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("applies a model on Enter and stays open", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    await screen.findByRole("menuitemradio", { name: "alpha" });
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");
    expect(api.setModel).toHaveBeenCalledWith("beta");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("applies a model on ArrowRight and stays open", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    await screen.findByRole("menuitemradio", { name: "alpha" });
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{ArrowRight}");
    expect(api.setModel).toHaveBeenCalledWith("beta");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("keeps the menu open after a language pick and marks the current code with the diamond", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, language: "en", model: "alpha" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="language" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const english = await screen.findByRole("menuitemradio", { name: /en\s+English/i });
    expect(english).toHaveAttribute("aria-checked", "true");
    expect(english.textContent).not.toMatch(/\bon\b/i);
    expect(isCursorRow(english)).toBe(true);
    expect(hasDiamond(english)).toBe(true);

    const dutch = screen.getByRole("menuitemradio", { name: /nl\s+Dutch/i });
    await user.click(dutch);
    expect(api.setLanguage).toHaveBeenCalledWith("nl");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("keeps the menu open after a search-engine pick and marks the current engine as the cursor row", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, searchEngine: "auto" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="search-engine" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const auto = await screen.findByRole("menuitemradio", { name: /search-engine auto/i });
    expect(auto).toHaveAttribute("aria-checked", "true");

    const exa = screen.getByRole("menuitemradio", { name: /search-engine exa/i });
    await user.click(exa);
    expect(api.setSearchEngine).toHaveBeenCalledWith("exa");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("renders the shared wording for every view level, so no level is left blank", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="view" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    // The page offers exactly the app's levels and nothing else: a retired id
    // on this page is a level the product renamed away (#6034 renamed
    // compact/detailed to quiet/verbose, #6079 retired hidden).
    const offered = (await screen.findAllByRole("menuitemradio")).map(
      (row) => /\/view\s+([a-z]+)/.exec(row.textContent ?? "")?.[1],
    );
    expect(offered).toEqual([...VIEW_MODES]);

    // Every level carries the shared wording in its own column on the right
    // of the row. A level with no wording renders a blank column, which is
    // what the quiet and verbose rows did while the menu kept its own
    // retired label map (DIG-4665). The wording comes from the shared map,
    // so this test walks the app's own ids: a rename cannot leave a row
    // unlabelled. The description must land in the description column and
    // not in the label, so the assertion reads the row's child cells
    // instead of its whole text.
    for (const level of VIEW_MODES) {
      const wording = VIEW_LABELS[level];
      expect(wording.trim()).not.toBe("");

      const row = await screen.findByRole("menuitemradio", {
        name: new RegExp(`^/view ${level}`, "i"),
      });
      const cells = Array.from(row.children) as HTMLElement[];
      const label = cells.find((cell) => cell.textContent?.trim() === `/view ${level}`);
      expect(label).toBeDefined();
      // The description cell is the other cell that truncates. The label cell
      // is excluded, so a label that grows a `truncate` of its own cannot
      // make this test read the label as the description.
      const description = cells.find(
        (cell) => cell !== label && cell.querySelector(".truncate"),
      );
      expect(description).toBeDefined();
      expect(description).not.toBe(label);
      expect(description?.textContent).toContain(wording);
    }
    unmount();
  });

  it("hides the search-engine row on the main menu when the tenant disallows web", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ tenantAllowsWeb: false })}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    expect(screen.queryByText("/search-engine")).toBeNull();
    unmount();
  });

  it("lists /theme in settings and paints the chosen palette", async () => {
    const user = userEvent.setup();
    // happy-dom's storage is not usable under every Node (a recent Node ships
    // its own `localStorage` global that shadows it), so stub a Map-backed one.
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
    localStorage.setItem("dt-theme", "dark");
    localStorage.removeItem("dt-palette");
    document.documentElement.removeAttribute("data-palette");
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("menuitem", { name: /\/theme/ }));

    const current = await screen.findByRole("menuitemradio", { name: /\/theme default dark/i });
    expect(current).toHaveAttribute("aria-checked", "true");
    const aura = screen.getByRole("menuitemradio", { name: /\/theme aura dark/i });
    await user.click(aura);

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-palette")).toBe("aura");
    expect(localStorage.getItem("dt-theme")).toBe("dark");
    expect(localStorage.getItem("dt-palette")).toBe("aura");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
    unmount();
    vi.unstubAllGlobals();
  });

  it("routes a /theme pick through a tenant embed's own theme, not localStorage", async () => {
    const user = userEvent.setup();
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
    const setTheme = vi.fn();
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider
        value={prefs({
          themeState: { preference: "light", palette: "default", resolved: "light" },
          setTheme,
        })}
      >
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("menuitem", { name: /\/theme/ }));
    // Opens on the tenant's own theme (light here), not on dt-theme.
    const current = await screen.findByRole("menuitemradio", { name: /\/theme default light/i });
    expect(current).toHaveAttribute("aria-checked", "true");
    await user.click(screen.getByRole("menuitemradio", { name: /\/theme aura dark/i }));

    expect(setTheme).toHaveBeenCalledWith("dark", "aura");
    expect(store.size).toBe(0);
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
    unmount();
    vi.unstubAllGlobals();
  });

  it("drops the pick when an embed's checked theme row is chosen again", async () => {
    const user = userEvent.setup();
    const setTheme = vi.fn();
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider
        value={prefs({
          themeState: { preference: "light", palette: "default", resolved: "light" },
          setTheme,
        })}
      >
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("menuitem", { name: /\/theme/ }));
    await user.click(await screen.findByRole("menuitemradio", { name: /\/theme default light/i }));

    // "auto" is how an embed clears the pick (embedThemePick("auto") is null).
    expect(setTheme).toHaveBeenCalledTimes(1);
    expect(setTheme).toHaveBeenCalledWith("auto", "default");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
    unmount();
  });

  it("pins the mode when the app's checked theme row is chosen with no stored theme", async () => {
    const user = userEvent.setup();
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
    document.documentElement.removeAttribute("data-palette");
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("menuitem", { name: /\/theme/ }));
    // No dt-theme: the app follows the OS, and the checked row is that mode.
    const checked = (await screen.findAllByRole("menuitemradio")).find(
      (row) => row.getAttribute("aria-checked") === "true",
    );
    expect(checked).toBeTruthy();
    const mode = /light/i.test(checked!.textContent ?? "") ? "light" : "dark";
    await user.click(checked!);

    expect(store.get("dt-theme")).toBe(mode);
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
    unmount();
    vi.unstubAllGlobals();
  });

  it("shows the search-engine row on the main menu when the tenant allows web", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ tenantAllowsWeb: true })}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    expect(await screen.findByText("/search-engine")).not.toBeNull();
    unmount();
  });

  it("offers auto in /models when the deployment default is auto", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          defaultModel="auto"
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );
    expect(await screen.findByRole("menuitemradio", { name: /auto/ })).not.toBeNull();
    unmount();
  });

  it("puts modes above a flat list of model names and selects a preset token", async () => {
    const onClose = vi.fn();
    const setModel = vi.fn();
    const picker = {
      showFullList: true,
      presets: [
        { id: "auto", label: "Default", model: "alpha/flash" },
        { id: "reasoning", label: "Reasoning", model: "beta/think" },
      ],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/flash", label: "Alpha Flash" }] },
        { provider: "beta", models: [{ id: "beta/think", label: "Beta Think" }] },
      ],
    };
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" }, setModel })}>
        <EmbedComposerMenu kind="models" picker={picker} models={["alpha/flash"]} onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    const radios = await screen.findAllByRole("menuitemradio");
    expect(radios.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Default"),
      expect.stringContaining("Reasoning"),
      "flash",
      "think",
    ]);
    expect(screen.queryByText(/our default/)).toBeNull();
    expect(screen.queryByText(/Best reasoning/)).toBeNull();
    // No provider headers, no expand state: just model names.
    expect(screen.queryAllByRole("menuitem", { name: /^\// })).toEqual([]);
    expect(document.querySelector("[aria-expanded]")).toBeNull();
    expect(screen.queryByText(/alpha|beta/)).toBeNull();
    // The row reads `think`; the pick is still the full id.
    await userEvent.click(screen.getByRole("menuitemradio", { name: /think/ }));
    expect(setModel).toHaveBeenLastCalledWith("beta/think");
    await userEvent.click(screen.getByRole("menuitemradio", { name: /Reasoning/ }));
    expect(setModel).toHaveBeenCalledWith("preset:reasoning");
    unmount();
  });


  it("builds the /models tree from id path segments, folders first, sorted at every level", () => {
    const tree = buildModelPathTree([
      "zeta/b-model",
      "alpha/sub/deep-2",
      "bare-model",
      "alpha/flat",
      "alpha/sub/deep-1",
      "another-bare",
      "zeta/a-model",
      "alpha/flat",
    ]);
    const show = (nodes: ReturnType<typeof buildModelPathTree>): unknown[] =>
      nodes.map((node) =>
        node.kind === "folder" ? { [`/${node.name}`]: show(node.children) } : node.name,
      );
    expect(show(tree)).toEqual([
      { "/alpha": [{ "/sub": ["deep-1", "deep-2"] }, "flat"] },
      { "/zeta": ["a-model", "b-model"] },
      // No slash: listed as-is at the top level, after the folders, no folder invented.
      "another-bare",
      "bare-model",
    ]);
    const deep = (tree[0] as { children: { children: { id: string }[] }[] }).children[0]!
      .children[0]!;
    expect(deep.id).toBe("alpha/sub/deep-1");
  });

  it("flattens deeper ids to their model name and picks the full id", async () => {
    const setModel = vi.fn();
    const picker = {
      showFullList: true,
      presets: [{ id: "auto", label: "Default", model: "alpha/sub/deep" }],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/sub/deep", label: "Deep" }, { id: "alpha/top", label: "Top" }] },
        { provider: "bare", models: [{ id: "bare-model", label: "Bare" }] },
      ],
    };
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" }, setModel })}>
        <EmbedComposerMenu kind="models" picker={picker} models={["alpha/sub/deep"]} onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await screen.findByRole("menuitemradio", { name: "alpha/sub/deep" });
    const rows = [...document.querySelectorAll('[id^="dc-menu-"]')];
    expect(rows.map((row) => row.textContent)).toEqual(["Default", "deep", "top", "bare-model"]);
    await userEvent.click(screen.getByRole("menuitemradio", { name: /deep/ }));
    expect(setModel).toHaveBeenLastCalledWith("alpha/sub/deep");
    unmount();
  });

  it("keeps the full id on rows whose model names collide across providers", async () => {
    const setModel = vi.fn();
    const picker = {
      showFullList: true,
      presets: [{ id: "auto", label: "Default", model: "alpha/same" }],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/same", label: "Same" }, { id: "alpha/solo", label: "Solo" }] },
        { provider: "beta", models: [{ id: "beta/same", label: "Same" }] },
      ],
    };
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" }, setModel })}>
        <EmbedComposerMenu kind="models" picker={picker} models={["alpha/same"]} onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await screen.findByRole("menuitemradio", { name: "beta/same" });
    const rows = [...document.querySelectorAll('[id^="dc-menu-"]')];
    expect(rows.map((row) => row.textContent)).toEqual(["Default", "alpha/same", "solo", "beta/same"]);
    await userEvent.click(screen.getByRole("menuitemradio", { name: "beta/same" }));
    expect(setModel).toHaveBeenLastCalledWith("beta/same");
    unmount();
  });


  it("exposes the full raw id as a model row's accessible name", async () => {
    const picker = {
      showFullList: true,
      presets: [{ id: "auto", label: "Default", model: "alpha/flash" }],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/flash", label: "Alpha Flash" }] },
      ],
    };
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" } })}>
        <EmbedComposerMenu kind="models" picker={picker} models={["alpha/flash"]} onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    const row = screen.getByRole("menuitemradio", { name: "alpha/flash" });
    expect(row.getAttribute("aria-label")).toBe("alpha/flash");
    unmount();
  });

  it("filters the flat list by model name", async () => {
    const picker = {
      showFullList: true,
      presets: [{ id: "auto", label: "Default", model: "alpha/flash" }],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/flash", label: "Alpha Flash" }] },
        { provider: "beta", models: [{ id: "beta/think", label: "Beta Think" }] },
      ],
    };
    const { unmount } = render(
      <EmbedChatPrefsProvider
        value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" }, paletteQuery: "thi" })}
      >
        <EmbedComposerMenu kind="models" picker={picker} models={["alpha/flash"]} onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    const radios = await screen.findAllByRole("menuitemradio");
    expect(radios.map((row) => row.textContent?.trim())).toEqual(["think"]);
    unmount();
  });

  it("filters the model list by any part of the name or id, start-of-name first", async () => {
    const picker = {
      showFullList: true,
      presets: [{ id: "auto", label: "Default", model: "alpha/flash" }],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/big-flash", label: "Big Flash" }] },
        { provider: "beta", models: [{ id: "beta/flash-mini", label: "Flash Mini" }, { id: "beta/think-luna", label: "Luna" }] },
      ],
    };
    const shown = async (paletteQuery: string) => {
      const { unmount } = render(
        <EmbedChatPrefsProvider
          value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" }, paletteQuery })}
        >
          <EmbedComposerMenu kind="models" picker={picker} models={["alpha/big-flash"]} onClose={vi.fn()} />
        </EmbedChatPrefsProvider>,
      );
      const radios = await screen.findAllByRole("menuitemradio");
      const out = radios.map((row) => row.textContent?.trim());
      unmount();
      return out;
    };
    expect(await shown("FLASH")).toEqual(["flash-mini", "big-flash"]);
    expect(await shown("luna")).toEqual(["think-luna"]);
    expect(await shown("ALPHA")).toEqual(["big-flash"]);
  });

  it("still filters by the provider part of the full id", async () => {
    const picker = {
      showFullList: true,
      presets: [{ id: "auto", label: "Default", model: "alpha/flash" }],
      groups: [
        { provider: "alpha", models: [{ id: "alpha/flash", label: "Alpha Flash" }] },
        { provider: "beta", models: [{ id: "beta/think", label: "Beta Think" }] },
      ],
    };
    const { unmount } = render(
      <EmbedChatPrefsProvider
        value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" }, paletteQuery: "beta" })}
      >
        <EmbedComposerMenu kind="models" picker={picker} models={["alpha/flash"]} onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    const radios = await screen.findAllByRole("menuitemradio");
    expect(radios.map((row) => row.textContent?.trim())).toEqual(["think"]);
    unmount();
  });

  it("renders the modes first, then a flat list of model names with no provider", async () => {
    const onClose = vi.fn();
    const resolved = resolveModelCatalog(
      { presets: ["auto", "reasoning", "fast", "light"], showFullList: true },
      { openRouterConfigured: false },
    );
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "" } })}>
        <EmbedComposerMenu
          kind="models"
          picker={resolved.picker}
          models={resolved.available}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );
    const radios = await screen.findAllByRole("menuitemradio");
    const texts = radios.map((row) => row.textContent ?? "");
    expect(texts.slice(0, 4)).toEqual([
      expect.stringContaining("Default"),
      expect.stringContaining("Reasoning"),
      expect.stringContaining("Fast"),
      expect.stringContaining("Light"),
    ]);
    const names = texts.slice(4);
    expect(names.length).toBeGreaterThan(2);
    expect(names).toContain("deepseek-v4.1-flash");
    expect(names).toContain("gemini-3.8-flash");
    // No provider prefix, header or tree glyph on any row.
    for (const name of names) expect(name).not.toMatch(/\/|├─|└─/);
    expect(screen.queryAllByRole("menuitem", { name: /^\// })).toEqual([]);
    expect(document.querySelectorAll('[data-slot="tools-tree-branch"]').length).toBe(0);
    // No descriptions, subtitles or catalog labels.
    expect(screen.queryByText("Manual selection")).toBeNull();
    expect(screen.queryByText("Premium")).toBeNull();
    expect(screen.queryByText(/Best reasoning in this list/)).toBeNull();
    expect(screen.queryByText("GLM 5.3")).toBeNull();
    expect(screen.queryByText("Gemini 3.8 Flash")).toBeNull();
    unmount();
  });


  it("does not offer auto when a model is pinned", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="models"
          models={["alpha", "beta"]}
          defaultModel="alpha"
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );
    await screen.findByRole("menuitemradio", { name: "alpha" });
    expect(screen.queryByRole("menuitemradio", { name: /auto/ })).toBeNull();
    unmount();
  });

  it("lists cheaperinference as a provider choice", async () => {
    const onClose = vi.fn();
    const onClearProvider = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="provider"
          onClose={onClose}
          onClearProvider={onClearProvider}
        />
      </EmbedChatPrefsProvider>,
    );
    expect(
      await screen.findByRole("menuitemradio", { name: /cheaperinference/ }),
    ).not.toBeNull();
    unmount();
  });

  it("renders the /help panel with examples, commands and the contact address", async () => {
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="help" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    const panel = await screen.findByText(/Ask about OCC policies/);
    expect(panel).not.toBeNull();
    expect(screen.getByText(/How do I raise a support ticket\?/)).not.toBeNull();
    expect(screen.getByText(/\/models/)).not.toBeNull();
    const contact = screen.getByRole("link", { name: "contact@digithings.ai" });
    expect(contact.getAttribute("href")).toBe("mailto:contact@digithings.ai");
    unmount();
  });
});

describe("EmbedComposerMenu navigation tree", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.querySelector("[data-picker-test-host]")?.remove();
  });

  it("goes back from a directly opened page to the root instead of closing", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="mcp" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    // Opened at a leaf, so the root list is not on screen yet.
    expect(screen.queryByRole("menuitem", { name: /\/models/ })).toBeNull();

    await user.keyboard("{Escape}");

    expect(onClose).not.toHaveBeenCalled();
    expect(await screen.findByRole("menuitem", { name: /\/models/ })).toBeTruthy();
  });

  it("closes only from the root", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

describe("EmbedComposerMenu current value", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.querySelector("[data-picker-test-host]")?.remove();
  });

  it("opens a sub-page from the root on its current value and commits that value", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    // The root opens the page; the page owns the cursor from there on.
    await user.click(await screen.findByRole("menuitem", { name: /\/view/ }));

    const balanced = await screen.findByRole("menuitemradio", { name: /\/view balanced/ });
    expect(isCursorRow(balanced)).toBe(true);
    // `quiet` is a level that is not the current value, so it carries no
    // cursor. It was `hidden` before #6079 retired that level; the assertion
    // is the same, on a level the ladder still has.
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /\/view quiet/ }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setView).toHaveBeenCalledWith("balanced");
    expect(api.setView).not.toHaveBeenCalledWith("quiet");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("opens a sub-page on the value that is set, not on the first row", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await user.click(await screen.findByRole("menuitem", { name: /\/effort/ }));

    // The effort is "medium", the second row: the cursor is not the top one.
    const medium = await screen.findByRole("menuitemradio", { name: /\/effort medium/ });
    expect(isCursorRow(medium)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /\/effort low/ }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setEffort).toHaveBeenCalledWith("medium");
    expect(api.setEffort).not.toHaveBeenCalledWith("low");
  });

  it("offers only the tenant's chip languages on /language when the tenant sets a list", async () => {
    const user = userEvent.setup();
    const api = prefs({
      prefs: { ...DEFAULT_EMBED_CHAT_PREFS, language: "en", model: "alpha" },
      languageOptions: [
        { code: "en", short: "EN", label: "English" },
        { code: "fr", short: "FR", label: "Français" },
      ],
    });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="language" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const rows = await screen.findAllByRole("menuitemradio");
    expect(rows.map((row) => row.textContent?.trim().slice(0, 2))).toEqual(["en", "fr"]);
    expect(screen.queryByRole("menuitemradio", { name: /nl\s+Dutch/i })).toBeNull();
    await user.click(screen.getByRole("menuitemradio", { name: /fr\s+French/i }));
    expect(api.setLanguage).toHaveBeenCalledWith("fr");
    expect(onClose).not.toHaveBeenCalled();
  });

  it("shows only the pinned language on /language for a single-language tenant", async () => {
    const api = prefs({
      prefs: { ...DEFAULT_EMBED_CHAT_PREFS, language: "fr", model: "alpha" },
      allowedLanguages: ["fr"],
    });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="language" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    const rows = await screen.findAllByRole("menuitemradio");
    expect(rows).toHaveLength(1);
    expect(rows[0]).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("menuitemradio", { name: /en\s+English/i })).toBeNull();
  });

  it("opens /language on the language that is set", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, language: "nl", model: "alpha" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="language" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const dutch = await screen.findByRole("menuitemradio", { name: /nl\s+Dutch/i });
    expect(isCursorRow(dutch)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /en\s+English/i }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setLanguage).toHaveBeenCalledWith("nl");
    expect(api.setLanguage).not.toHaveBeenCalledWith("en");
  });

  it("opens /thinking on the thinking mode that is set", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, thinking: "collapsed" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="thinking" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const collapsed = await screen.findByRole("menuitemradio", { name: /thinking collapsed/i });
    expect(isCursorRow(collapsed)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /thinking auto/i }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setThinking).toHaveBeenCalledWith("collapsed");
    expect(api.setThinking).not.toHaveBeenCalledWith("auto");
  });

  it("opens /search-engine on the engine that is set", async () => {
    const user = userEvent.setup();
    const api = prefs({ prefs: { ...DEFAULT_EMBED_CHAT_PREFS, searchEngine: "exa" } });
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="search-engine" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const exa = await screen.findByRole("menuitemradio", { name: /search-engine exa/i });
    expect(isCursorRow(exa)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /search-engine auto/i }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setSearchEngine).toHaveBeenCalledWith("exa");
    expect(api.setSearchEngine).not.toHaveBeenCalledWith("auto");
  });

  it("opens /models on the model that is set, not on the first row", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="models" models={["beta", "alpha"]} onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const alpha = await screen.findByRole("menuitemradio", { name: "alpha" });
    expect(isCursorRow(alpha)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: "beta" }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setModel).toHaveBeenCalledWith("alpha");
    expect(api.setModel).not.toHaveBeenCalledWith("beta");
  });

  it("has no rows on /help, so Enter commits nothing", async () => {
    const user = userEvent.setup();
    const api = prefs();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="help" models={["alpha", "beta"]} onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    // The help panel is not a list: it must not borrow the model rows.
    expect(await screen.findByText(/Ask about OCC policies/)).not.toBeNull();
    expect(screen.queryByRole("menuitemradio")).toBeNull();

    await user.keyboard("{Enter}");
    expect(api.setModel).not.toHaveBeenCalled();
    expect(onClose).not.toHaveBeenCalled();
  });

  it("puts the cursor on the active provider row, not on the row before it", async () => {
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu
          kind="provider"
          providerActive={{ provider: "anthropic", model: "claude-sonnet" }}
          onClose={onClose}
        />
      </EmbedChatPrefsProvider>,
    );

    const anthropic = await screen.findByRole("menuitemradio", { name: /\/anthropic/ });
    expect(isCursorRow(anthropic)).toBe(true);
    expect(hasDiamond(anthropic)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /\/openai/ }))).toBe(false);
  });

  it("keeps the cursor on the clear row when no provider is connected", async () => {
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="provider" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const clear = await screen.findByRole("menuitemradio", { name: /\/cheaperinference/ });
    expect(isCursorRow(clear)).toBe(true);
    expect(isCursorRow(screen.getByRole("menuitemradio", { name: /\/openai/ }))).toBe(false);
  });

  it("comes back from the key form on the provider row the user opened", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="provider" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    await screen.findByRole("menuitemradio", { name: /\/cheaperinference/ });
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");

    // The key form is up: the provider list is gone.
    expect(screen.queryByRole("menuitemradio", { name: /\/openai/ })).toBeNull();

    await user.keyboard("{Escape}");

    const openai = await screen.findByRole("menuitemradio", { name: /\/openai/ });
    expect(isCursorRow(openai)).toBe(true);
  });

  it("keeps the menu open after a model pick when the composer writer is not bound", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const api = prefs({ setComposerDraft: vi.fn() });
    render(
      <EmbedChatPrefsProvider value={api}>
        <EmbedComposerMenu kind="models" models={["alpha", "beta"]} onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(await screen.findByRole("menuitemradio", { name: "beta" }));
    expect(api.setModel).toHaveBeenCalledWith("beta");
    // A setting pick keeps the menu open on the same page.
    expect(onClose).not.toHaveBeenCalled();
  });

  it("leaves the provider page on Escape when the composer writer is not bound", async () => {
    const user = userEvent.setup();
    const setComposerDraft = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs({ setComposerDraft })}>
        <EmbedComposerMenu kind="provider" onClose={vi.fn()} />
      </EmbedChatPrefsProvider>,
    );
    await screen.findByRole("menuitemradio", { name: /\/cheaperinference/ });
    await user.keyboard("{Escape}");
    expect(setComposerDraft).not.toHaveBeenCalled();
    expect(await screen.findByRole("menuitem", { name: /\/language/ })).toBeTruthy();
  });
});

describe("cursorOnCurrentRow", () => {
  function row(over: Partial<MenuRow>): MenuRow {
    return {
      id: "row",
      label: "row",
      value: "",
      activate: () => {},
      ...over,
    };
  }

  it("lands on the checked radio row", () => {
    const rows = [
      row({ id: "a" }),
      row({ id: "b", checked: true, exclusive: true }),
      row({ id: "c" }),
    ];
    expect(cursorOnCurrentRow(rows)).toBe(1);
  });

  it("starts at the top for a list without a single current value", () => {
    // A toggle is checked but not a choice: there is no row to land on.
    expect(cursorOnCurrentRow([row({ id: "a", checked: true })])).toBe(0);
    expect(cursorOnCurrentRow([])).toBe(0);
  });
});
