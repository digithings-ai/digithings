// @vitest-environment happy-dom
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { applyDocumentTheme } from "../theme/apply-theme";
import { ThemeProvider, ThemeToggle, useTheme } from "./ThemeProvider";

type MediaStub = {
  matches: boolean;
  dispatch: (light: boolean) => void;
};

function installMedia(light: boolean): MediaStub {
  const listeners = new Set<(event: { matches: boolean }) => void>();
  const mq = {
    matches: light,
    media: "(prefers-color-scheme: light)",
    addEventListener: (_type: string, fn: (event: { matches: boolean }) => void) => {
      listeners.add(fn);
    },
    removeEventListener: (_type: string, fn: (event: { matches: boolean }) => void) => {
      listeners.delete(fn);
    },
    dispatch(next: boolean) {
      mq.matches = next;
      for (const fn of listeners) fn({ matches: next });
    },
  };
  window.matchMedia = () => mq as unknown as MediaQueryList;
  return mq;
}

function Probe() {
  const { theme, preference, palette, setTheme, setPalette, toggle } = useTheme();
  return (
    <div>
      <span data-testid="theme">{theme}</span>
      <span data-testid="pref">{preference}</span>
      <span data-testid="pal">{palette}</span>
      <button type="button" onClick={() => setTheme("auto")}>
        auto
      </button>
      <button type="button" onClick={() => setTheme("dark")}>
        dark
      </button>
      <button type="button" onClick={() => setPalette("dracula")}>
        dracula
      </button>
      <button type="button" onClick={() => setPalette("default")}>
        default
      </button>
      <button type="button" onClick={() => setPalette("nope")}>
        nope
      </button>
      <button type="button" onClick={toggle}>
        toggle
      </button>
    </div>
  );
}

describe("ThemeProvider", () => {
  let media: MediaStub;

  beforeEach(() => {
    // happy-dom's storage is not usable under every Node (a recent Node ships
    // its own `localStorage` global that shadows it), so stub a Map-backed one,
    // the same way the digichat pref tests do.
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
    document.documentElement.removeAttribute("data-theme-pin");
    media = installMedia(false);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("toggle walks default dark, default light, then the first palette", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("dt-theme")).toBe("light");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem("dt-theme")).toBe("dark");
    expect(localStorage.getItem("dt-palette")).toBe("aura");
    expect(document.documentElement.getAttribute("data-palette")).toBe("aura");
  });

  it("the shared toggle names the stop it is on in its title, and a click moves it", () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>,
    );
    // /chatbot's top bar renders this toggle. Its title is the cycle stop it is
    // on, so the cycle in the top bar is pinned, not just described.
    const toggle = screen.getByRole("button", { name: "Toggle colour theme" });
    expect(toggle.getAttribute("title")).toBe("default · dark");
    fireEvent.click(toggle);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(toggle.getAttribute("title")).toBe("default · light");
  });

  it("auto clears dt-theme and follows the OS, keeping the palette", () => {
    localStorage.setItem("dt-palette", "dracula");
    // What themeInitScript paints before hydration.
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.setAttribute("data-palette", "dracula");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("pal").textContent).toBe("dracula");
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
    fireEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(localStorage.getItem("dt-theme")).toBe("dark");
    fireEvent.click(screen.getByRole("button", { name: "auto" }));
    expect(localStorage.getItem("dt-theme")).toBeNull();
    expect(localStorage.getItem("dt-palette")).toBe("dracula");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    media.dispatch(true);
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("dt-palette")).toBe("dracula");
  });

  it("reads the painted document on mount and writes nothing", () => {
    // digiquant.io paints dark itself and runs no themeInitScript, while the
    // dashboard mirrors its own choice into dt-theme on the same origin.
    localStorage.setItem("dt-theme", "light");
    document.documentElement.setAttribute("data-theme", "dark");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(localStorage.getItem("dt-theme")).toBe("light");
    expect(localStorage.getItem("dt-palette")).toBeNull();
    // The painted mode is the page's preference, so title and icon agree.
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(screen.getByTestId("pref").textContent).toBe("dark");
  });

  it("leaves a pinned embed document alone", () => {
    localStorage.setItem("dt-theme", "light");
    localStorage.setItem("dt-palette", "dracula");
    document.documentElement.setAttribute("data-theme-pin", "1");
    document.documentElement.setAttribute("data-theme", "dark");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    // useTheme() reports what the pin painted, not a hard-coded default.
    expect(screen.getByTestId("theme").textContent).toBe("dark");
    expect(screen.getByTestId("pref").textContent).toBe("dark");
    expect(screen.getByTestId("pal").textContent).toBe("default");
    expect(localStorage.getItem("dt-theme")).toBe("light");
    expect(localStorage.getItem("dt-palette")).toBe("dracula");
    document.documentElement.removeAttribute("data-theme-pin");
  });

  it("reports a pinned light embed as light", () => {
    document.documentElement.setAttribute("data-theme-pin", "1");
    document.documentElement.setAttribute("data-theme", "light");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(screen.getByTestId("theme").textContent).toBe("light");
    document.documentElement.removeAttribute("data-theme-pin");
  });

  it("follows a theme painted outside the provider (the /theme command)", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      applyDocumentTheme("light", "aura");
    });
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByTestId("pref").textContent).toBe("light");
    expect(screen.getByTestId("pal").textContent).toBe("aura");
    // An explicit choice is not undone by the OS changing.
    act(() => media.dispatch(false));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
  });

  it("a storage event from another tab repaints mode and palette", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    localStorage.setItem("dt-theme", "light");
    localStorage.setItem("dt-palette", "nord");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "dt-theme" }));
    });
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-palette")).toBe("nord");
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(screen.getByTestId("pal").textContent).toBe("nord");
  });

  it("a pinned document ignores a storage event", () => {
    document.documentElement.setAttribute("data-theme-pin", "1");
    document.documentElement.setAttribute("data-theme", "dark");
    localStorage.setItem("dt-theme", "light");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: "dt-theme" }));
    });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
  });

  it("an OS change repaints auto without writing storage", () => {
    document.documentElement.setAttribute("data-theme", "dark");
    document.documentElement.setAttribute("data-palette", "nord");
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    act(() => media.dispatch(true));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(document.documentElement.getAttribute("data-palette")).toBe("nord");
    expect(screen.getByTestId("theme").textContent).toBe("light");
    expect(localStorage.getItem("dt-theme")).toBeNull();
    expect(localStorage.getItem("dt-palette")).toBeNull();
  });

  it("setPalette persists dt-palette and drops an unknown name", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "dracula" }));
    expect(document.documentElement.getAttribute("data-palette")).toBe("dracula");
    expect(localStorage.getItem("dt-palette")).toBe("dracula");
    fireEvent.click(screen.getByRole("button", { name: "default" }));
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
    expect(localStorage.getItem("dt-palette")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "nope" }));
    expect(screen.getByTestId("pal").textContent).toBe("default");
    expect(document.documentElement.hasAttribute("data-palette")).toBe(false);
  });
});
