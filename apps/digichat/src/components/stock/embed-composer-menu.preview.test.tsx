// @vitest-environment happy-dom
"use client";

import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EmbedComposerMenu } from "./embed-composer-menu";
import {
  DEFAULT_EMBED_CHAT_PREFS,
  EmbedChatPrefsProvider,
  committedChatPrefs,
  slashRowPreview,
  useEmbedChatPrefs,
  type EmbedChatPrefs,
  type EmbedChatPrefsApi,
} from "@digithings/ui/chat/stock";

/**
 * Live preview in the `/` menu: hovering or arrowing onto a purely visual
 * row (view, density, theme) paints the page with it; leaving or closing
 * reverts; choosing commits and the menu stays open on the same page.
 */

function api(over: Partial<EmbedChatPrefsApi> = {}): EmbedChatPrefsApi {
  return {
    prefs: { ...DEFAULT_EMBED_CHAT_PREFS, model: "alpha", view: "balanced", density: "default" },
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

/** What the page renders from: the thread reads prefs through context. */
function Page() {
  const { prefs } = useEmbedChatPrefs();
  return <output data-testid="page">{`${prefs.view}|${prefs.density}|${prefs.model}|${prefs.language}`}</output>;
}

const page = () => screen.getByTestId("page").textContent;

/** A host that commits like the real ones: setters update its prefs. */
function Host({
  kind,
  open = true,
  onClose = () => {},
  base = {},
}: {
  kind: "view" | "density" | "models" | "language" | "settings";
  open?: boolean;
  onClose?: () => void;
  base?: Partial<EmbedChatPrefsApi>;
}) {
  const [prefs, setPrefs] = useState<EmbedChatPrefs>(api().prefs);
  const set = (patch: Partial<EmbedChatPrefs>) => setPrefs((p) => ({ ...p, ...patch }));
  const value = api({
    prefs,
    setView: (view) => set({ view }),
    setDensity: (density) => set({ density }),
    setModel: (model) => set({ model }),
    setLanguage: (language) => set({ language }),
    ...base,
  });
  return (
    <EmbedChatPrefsProvider value={value}>
      <Page />
      {open ? <EmbedComposerMenu kind={kind} models={["alpha", "beta"]} onClose={onClose} /> : null}
    </EmbedChatPrefsProvider>
  );
}

function mountHost() {
  const wrap = document.createElement("div");
  wrap.setAttribute("data-thread-skin", "digichat");
  wrap.setAttribute("data-preview-test-host", "true");
  wrap.innerHTML = `<div class="aui-composer-root"></div>`;
  document.body.appendChild(wrap);
}

describe("EmbedComposerMenu live preview", () => {
  beforeEach(mountHost);
  afterEach(() => {
    document.querySelector("[data-preview-test-host]")?.remove();
    vi.unstubAllGlobals();
  });

  it("previews a hovered view and reverts when the cursor leaves it", async () => {
    const user = userEvent.setup();
    render(<Host kind="view" />);
    const quiet = await screen.findByRole("menuitemradio", { name: /\/view quiet/ });
    expect(page()).toMatch(/^balanced\|/);

    await user.hover(quiet);
    expect(page()).toMatch(/^quiet\|/);
    // The committed value keeps its mark while another row is previewed.
    expect(screen.getByRole("menuitemradio", { name: /\/view balanced/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(quiet).toHaveAttribute("aria-checked", "false");

    await user.hover(screen.getByRole("menuitemradio", { name: /\/view balanced/ }));
    expect(page()).toMatch(/^balanced\|/);
  });

  it("previews the row reached with the arrow keys", async () => {
    const user = userEvent.setup();
    render(<Host kind="density" />);
    await screen.findByRole("menuitemradio", { name: /\/density airy/ });
    expect(page()).toMatch(/\|default\|/);
    await user.keyboard("{ArrowDown}");
    expect(page()).toMatch(/\|airy\|/);
    await user.keyboard("{ArrowUp}{ArrowUp}");
    expect(page()).toMatch(/\|compact\|/);
  });

  it("reverts the preview when the menu closes without a pick", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<Host kind="view" />);
    await user.hover(await screen.findByRole("menuitemradio", { name: /\/view verbose/ }));
    expect(page()).toMatch(/^verbose\|/);
    rerender(<Host kind="view" open={false} />);
    expect(page()).toMatch(/^balanced\|/);
  });

  it("reverts the preview when the menu leaves the sub-page", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Host kind="settings" onClose={onClose} />);
    await user.click(await screen.findByRole("menuitem", { name: /\/view/ }));
    await user.hover(await screen.findByRole("menuitemradio", { name: /\/view quiet/ }));
    expect(page()).toMatch(/^quiet\|/);
    await user.keyboard("{Escape}");
    expect(await screen.findByRole("menuitem", { name: /\/view/ })).toBeTruthy();
    expect(page()).toMatch(/^balanced\|/);
    expect(onClose).not.toHaveBeenCalled();
  });

  it("commits on select, stays open on the same page and marks the new value", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    const { rerender } = render(<Host kind="view" onClose={onClose} />);
    await user.click(await screen.findByRole("menuitemradio", { name: /\/view quiet/ }));
    expect(page()).toMatch(/^quiet\|/);
    expect(onClose).not.toHaveBeenCalled();
    const quiet = screen.getByRole("menuitemradio", { name: /\/view quiet/ });
    expect(quiet).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("menuitemradio", { name: /\/view balanced/ })).toHaveAttribute(
      "aria-checked",
      "false",
    );
    // Closing after a pick keeps the committed value.
    rerender(<Host kind="view" open={false} onClose={onClose} />);
    expect(page()).toMatch(/^quiet\|/);
  });

  it("commits on Enter and keeps the menu open", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(<Host kind="density" onClose={onClose} />);
    await screen.findByRole("menuitemradio", { name: /\/density airy/ });
    await user.keyboard("{ArrowDown}{Enter}");
    expect(page()).toMatch(/\|airy\|/);
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("menuitemradio", { name: /\/density airy/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("does not preview non-visual settings (model, language)", async () => {
    const user = userEvent.setup();
    const previewPrefs = vi.fn();
    const { unmount } = render(<Host kind="models" />);
    await user.hover(await screen.findByRole("menuitemradio", { name: "beta" }));
    expect(page()).toMatch(/\|alpha\|/);
    unmount();

    render(<Host kind="language" base={{ previewPrefs }} />);
    const rows = await screen.findAllByRole("menuitemradio");
    await user.hover(rows[2]!);
    expect(page()).toMatch(/\|en$/);
    expect(previewPrefs.mock.calls.filter(([patch]) => patch !== null)).toEqual([]);
  });

  it("previews an embed theme without storing it, reverts on close and commits on select", async () => {
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
    const previewTheme = vi.fn();
    const onClose = vi.fn();
    const value = api({
      themeState: { preference: "light", palette: "default", resolved: "light" },
      setTheme,
      previewTheme,
    });
    const { unmount } = render(
      <EmbedChatPrefsProvider value={value}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(await screen.findByRole("menuitem", { name: /\/theme/ }));
    await user.hover(await screen.findByRole("menuitemradio", { name: /\/theme aura dark/i }));
    expect(previewTheme).toHaveBeenLastCalledWith({ preference: "dark", palette: "aura" });
    expect(setTheme).not.toHaveBeenCalled();
    expect(store.size).toBe(0);
    // The committed theme keeps its mark during the preview.
    expect(screen.getByRole("menuitemradio", { name: /\/theme default light/i })).toHaveAttribute(
      "aria-checked",
      "true",
    );

    await user.click(screen.getByRole("menuitemradio", { name: /\/theme aura dark/i }));
    expect(previewTheme).toHaveBeenLastCalledWith(null);
    expect(setTheme).toHaveBeenCalledWith("dark", "aura");
    expect(onClose).not.toHaveBeenCalled();

    await user.hover(screen.getByRole("menuitemradio", { name: /\/theme aura light/i }));
    expect(previewTheme).toHaveBeenLastCalledWith({ preference: "light", palette: "aura" });
    unmount();
    expect(previewTheme).toHaveBeenLastCalledWith(null);
    expect(store.size).toBe(0);
  });

  it("previews an app theme on the document without persisting, and reverts on close", async () => {
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
    store.set("dt-theme", "dark");
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.removeAttribute("data-palette");
    const onClose = vi.fn();
    const { unmount } = render(
      <EmbedChatPrefsProvider value={api()}>
        <EmbedComposerMenu kind="settings" onClose={onClose} />
      </EmbedChatPrefsProvider>,
    );
    await user.click(await screen.findByRole("menuitem", { name: /\/theme/ }));
    await user.hover(await screen.findByRole("menuitemradio", { name: /\/theme aura light/i }));
    expect(document.documentElement.getAttribute("data-palette")).toBe("aura");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(store.get("dt-theme")).toBe("dark");
    expect(store.has("dt-palette")).toBe(false);

    act(() => unmount());
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.getAttribute("data-palette")).toBeNull();
    expect(store.get("dt-theme")).toBe("dark");
    expect(store.has("dt-palette")).toBe(false);
    expect(onClose).not.toHaveBeenCalled();
  });
});

describe("prefs preview overlay", () => {
  it("overlays the preview on prefs while committedPrefs keeps the chosen value", () => {
    let seen: EmbedChatPrefsApi | null = null;
    function Probe() {
      seen = useEmbedChatPrefs();
      return null;
    }
    render(
      <EmbedChatPrefsProvider value={api()}>
        <Probe />
      </EmbedChatPrefsProvider>,
    );
    act(() => seen!.previewPrefs!({ view: "quiet", scrollbars: "always" }));
    expect(seen!.prefs.view).toBe("quiet");
    expect(seen!.prefs.scrollbars).toBe("always");
    expect(committedChatPrefs(seen!).view).toBe("balanced");
    act(() => seen!.previewPrefs!(null));
    expect(seen!.prefs.view).toBe("balanced");
  });

  it("previews /scrollbar as the flipped value and nothing for other main rows", () => {
    const prefs = { ...DEFAULT_EMBED_CHAT_PREFS, scrollbars: "auto" as const };
    expect(slashRowPreview("scrollbar", prefs)).toEqual({ scrollbars: "always" });
    expect(slashRowPreview("scrollbar", { ...prefs, scrollbars: "always" })).toEqual({
      scrollbars: "auto",
    });
    expect(slashRowPreview("models", prefs)).toBeNull();
    expect(slashRowPreview("toolbar", prefs)).toBeNull();
  });
});
