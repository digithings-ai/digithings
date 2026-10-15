// @vitest-environment happy-dom
/**
 * Scroll-mode reveal threshold and the top-edge hover rescue.
 * Class flips happen in an effect, so SSR markup cannot show them.
 */
import type { ReactElement } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { NavShell } from "./NavShell";
import type { NavItem } from "./chrome";

const ITEMS: NavItem[] = [{ label: "Docs", href: "/docs" }];

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

function scrollTo(y: number) {
  Object.defineProperty(window, "scrollY", { configurable: true, value: y });
  act(() => {
    window.dispatchEvent(new Event("scroll"));
  });
}

afterEach(() => {
  document.body.replaceChildren();
  Object.defineProperty(window, "scrollY", { configurable: true, value: 0 });
});

describe("NavShell scroll reveal", () => {
  it("stays hidden until upward scroll passes scrollRevealDelta", async () => {
    const { host, unmount } = await mount(
      <NavShell
        brand="digiquant"
        links={ITEMS}
        showThemeToggle={false}
        scrollRevealDelta={120}
      />,
    );
    const nav = host.querySelector("header.nav-shell");
    scrollTo(400);
    expect(nav?.classList.contains("is-hidden")).toBe(true);
    scrollTo(360);
    expect(nav?.classList.contains("is-hidden")).toBe(true);
    scrollTo(200);
    expect(nav?.classList.contains("is-hidden")).toBe(false);
    await unmount();
  });

  it("reveals when the pointer is in hoverRevealZone", async () => {
    const { host, unmount } = await mount(
      <NavShell
        brand="digiquant"
        links={ITEMS}
        showThemeToggle={false}
        scrollRevealDelta={120}
        hoverRevealZone={24}
      />,
    );
    const nav = host.querySelector("header.nav-shell");
    scrollTo(400);
    expect(nav?.classList.contains("is-hidden")).toBe(true);
    act(() => {
      window.dispatchEvent(new MouseEvent("mousemove", { clientY: 8 }));
    });
    expect(nav?.classList.contains("is-hidden")).toBe(false);
    await unmount();
  });
});
