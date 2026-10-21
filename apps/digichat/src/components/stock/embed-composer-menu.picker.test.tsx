// @vitest-environment happy-dom
"use client";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu, cursorOnCurrentRow, type MenuRow } from "./embed-composer-menu";
import { VIEW_MODES } from "@/lib/view-modes";
import { VIEW_LABELS } from "@digithings/digichat-ui";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";

/** Navigated row: the user-message chevron on the left. */
function hasChevron(row: HTMLElement): boolean {
  return (row.querySelector(".aui-menu-cursor")?.childElementCount ?? 0) > 0;
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

  it("applies a model on click and closes; selected row uses the diamond, not on", async () => {
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
    // The cursor row always carries the chevron; a checked row also keeps its
    // diamond on the right, so the two marks never share a side.
    expect(hasChevron(selected)).toBe(true);
    expect(hasDiamond(selected)).toBe(true);

    const other = screen.getByRole("menuitemradio", { name: "beta" });
    expect(hasChevron(other)).toBe(false);
    expect(hasDiamond(other)).toBe(false);

    // The chevron follows hover / arrow keys; the configured value keeps its
    // diamond, so the two marks mean different things.
    await user.hover(other);
    expect(hasChevron(other)).toBe(true);
    expect(hasChevron(selected)).toBe(false);
    expect(hasDiamond(selected)).toBe(true);
    expect(hasDiamond(other)).toBe(false);

    // Navigating back to the checked row restores the chevron beside the
    // diamond; the diamond still marks the configured value.
    await user.hover(selected);
    expect(hasChevron(selected)).toBe(true);
    expect(hasDiamond(selected)).toBe(true);

    await user.click(other);
    expect(api.setModel).toHaveBeenCalledWith("beta");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("applies a model on Enter and closes", async () => {
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
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("applies a model on ArrowRight and closes", async () => {
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
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes language pick on click and marks the current code with the diamond", async () => {
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
    expect(hasChevron(english)).toBe(true);
    expect(hasDiamond(english)).toBe(true);

    const dutch = screen.getByRole("menuitemradio", { name: /nl\s+Dutch/i });
    await user.click(dutch);
    expect(api.setLanguage).toHaveBeenCalledWith("nl");
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("closes search-engine pick on click and marks the current engine with the chevron", async () => {
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
    expect(onClose).toHaveBeenCalledTimes(1);
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
    expect(onClose).toHaveBeenCalledTimes(1);
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
    expect(hasChevron(balanced)).toBe(true);
    // `quiet` is a level that is not the current value, so it carries no
    // cursor. It was `hidden` before #6079 retired that level; the assertion
    // is the same, on a level the ladder still has.
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /\/view quiet/ }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setView).toHaveBeenCalledWith("balanced");
    expect(api.setView).not.toHaveBeenCalledWith("quiet");
    expect(onClose).toHaveBeenCalledTimes(1);
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
    expect(hasChevron(medium)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /\/effort low/ }))).toBe(false);

    await user.keyboard("{Enter}");
    expect(api.setEffort).toHaveBeenCalledWith("medium");
    expect(api.setEffort).not.toHaveBeenCalledWith("low");
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
    expect(hasChevron(dutch)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /en\s+English/i }))).toBe(false);

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
    expect(hasChevron(collapsed)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /thinking auto/i }))).toBe(false);

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
    expect(hasChevron(exa)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /search-engine auto/i }))).toBe(false);

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
    expect(hasChevron(alpha)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: "beta" }))).toBe(false);

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
    expect(hasChevron(anthropic)).toBe(true);
    expect(hasDiamond(anthropic)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /\/openai/ }))).toBe(false);
  });

  it("keeps the cursor on the clear row when no provider is connected", async () => {
    const onClose = vi.fn();
    render(
      <EmbedChatPrefsProvider value={prefs()}>
        <EmbedComposerMenu kind="provider" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );

    const clear = await screen.findByRole("menuitemradio", { name: /\/cheaperinference/ });
    expect(hasChevron(clear)).toBe(true);
    expect(hasChevron(screen.getByRole("menuitemradio", { name: /\/openai/ }))).toBe(false);
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
    expect(hasChevron(openai)).toBe(true);
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
