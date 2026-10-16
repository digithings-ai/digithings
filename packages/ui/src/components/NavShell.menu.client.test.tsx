// @vitest-environment happy-dom
/**
 * Client a11y behaviour of the narrow-viewport portal sheet. The render suite
 * only sees the SSR tree, and the sheet lives behind a portal + mount gate, so
 * these are the assertions that keep the menu honest: the hamburger's
 * expanded/controls contract, Escape and scrim dismissal, and — the part that
 * would otherwise be taken on faith — focus returning to the hamburger rather
 * than being stranded on a hidden sheet.
 */
import type { ReactElement } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { NavShell } from "./NavShell";
import type { NavItem } from "./chrome";

const ITEMS: NavItem[] = [
  { label: "Docs", href: "/docs" },
  { label: "Changelog", href: "/changelog" },
];

async function mount(ui: ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  return {
    host,
    unmount: () => act(() => root.unmount()),
  };
}

const sheet = () => document.body.querySelector<HTMLElement>(".nav-shell-sheet");
const backdrop = () => document.body.querySelector<HTMLButtonElement>(".nav-shell-backdrop");
const toggle = (host: HTMLElement) =>
  host.querySelector<HTMLButtonElement>("button.nav-shell-toggle");

const press = async (el: Element) => {
  await act(async () => {
    el.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
};

const pressEscape = async () => {
  await act(async () => {
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
  });
};

const render = (currentPath?: string) =>
  mount(
    <NavShell
      brand="digithings"
      links={ITEMS}
      currentPath={currentPath}
      skipTo="#main"
      showThemeToggle={false}
    />,
  );

afterEach(() => {
  document.body.replaceChildren();
});

describe("NavShell — skip link", () => {
  it("renders a skip-to-content link when skipTo is set", async () => {
    const { host, unmount } = await render();
    const skip = host.querySelector<HTMLAnchorElement>('a[href="#main"]');
    expect(skip?.textContent).toContain("Skip to content");
    await unmount();
  });

  it("omits the skip link when skipTo is not set", async () => {
    const { host, unmount } = await mount(
      <NavShell brand="digithings" links={ITEMS} showThemeToggle={false} />,
    );
    expect(host.querySelector('a[href="#main"]')).toBeNull();
    await unmount();
  });
});

describe("NavShell — portal sheet", () => {
  it("wires the hamburger to the sheet and opens it", async () => {
    const { host, unmount } = await render();
    const button = toggle(host);
    expect(button).not.toBeNull();
    expect(button?.getAttribute("aria-expanded")).toBe("false");
    const sheetId = button?.getAttribute("aria-controls");
    expect(sheetId).toBeTruthy();
    expect(sheet()?.getAttribute("aria-hidden")).toBe("true");

    await press(button!);

    expect(button?.getAttribute("aria-expanded")).toBe("true");
    expect(sheet()?.classList.contains("is-open")).toBe(true);
    expect(sheet()?.id).toBe(sheetId);
    expect(sheet()?.getAttribute("aria-hidden")).toBe("false");
    await unmount();
  });

  it("closes on Escape and returns focus to the hamburger", async () => {
    const { host, unmount } = await render();
    const button = toggle(host)!;

    await press(button);
    expect(sheet()?.classList.contains("is-open")).toBe(true);

    await pressEscape();

    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(sheet()?.classList.contains("is-open")).toBe(false);
    expect(document.activeElement).toBe(button);
    await unmount();
  });

  it("closes on a scrim click and returns focus to the hamburger", async () => {
    const { host, unmount } = await render();
    const button = toggle(host)!;

    await press(button);
    expect(backdrop()?.classList.contains("is-open")).toBe(true);

    await press(backdrop()!);

    expect(button.getAttribute("aria-expanded")).toBe("false");
    expect(sheet()?.classList.contains("is-open")).toBe(false);
    expect(document.activeElement).toBe(button);
    await unmount();
  });
});
