// @vitest-environment happy-dom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { ThemePicker } from "./ThemePicker";
import { ThemeProvider, useTheme } from "./ThemeProvider";

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
    localStorage.clear();
    document.documentElement.removeAttribute("data-theme");
    document.documentElement.removeAttribute("data-palette");
    media = installMedia(false);
  });

  afterEach(() => {
    cleanup();
    localStorage.clear();
  });

  it("toggle writes an explicit dt-theme", () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "toggle" }));
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");
    expect(localStorage.getItem("dt-theme")).toBe("light");
  });

  it("auto clears dt-theme and follows the OS, keeping the palette", () => {
    localStorage.setItem("dt-palette", "dracula");
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

describe("ThemePicker", () => {
  beforeEach(() => {
    localStorage.clear();
    installMedia(false);
  });

  afterEach(cleanup);

  it("opens on the current mode and palette", () => {
    localStorage.setItem("dt-theme", "dark");
    localStorage.setItem("dt-palette", "github");
    render(
      <ThemeProvider>
        <ThemePicker />
      </ThemeProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Colour theme" }));
    expect(screen.getByRole("button", { name: "Dark" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByText("github")).toBeTruthy();
  });
});
