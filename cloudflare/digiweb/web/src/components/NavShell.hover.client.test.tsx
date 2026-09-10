// @vitest-environment happy-dom
/**
 * Client behaviour of <NavShell autoHide="hover"> — the hover-reveal dwell
 * delay and its viewport-exit cancellation. Neither is visible to SSR: the
 * reveal effect only attaches after mount, so NavShell.render.test.tsx (SSR
 * smoke tests) can't reach it.
 */
import type { ReactElement } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

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

/** Inside HOT_ZONE (<=24px from the top) — starts the dwell timer. */
const moveIntoHotZone = () => window.dispatchEvent(new MouseEvent("mousemove", { clientY: 10 }));

/** documentElement, not window: mouseleave doesn't bubble, and it's the html
 *  element's geometry — filling the viewport — the pointer actually exits. */
const leaveViewport = () => document.documentElement.dispatchEvent(new MouseEvent("mouseleave"));

afterEach(() => {
  document.body.replaceChildren();
});

describe("NavShell — hover autoHide reveal dwell", () => {
  it("reveals once the cursor dwells past REVEAL_DELAY", async () => {
    const { host, unmount } = await mount(
      <NavShell brand="digithings" links={ITEMS} showThemeToggle={false} autoHide="hover" />,
    );
    const nav = host.querySelector("header.nav-shell");
    expect(nav?.classList.contains("is-hidden")).toBe(true);

    vi.useFakeTimers();
    moveIntoHotZone();
    vi.advanceTimersByTime(150); // past the 120ms dwell delay
    vi.useRealTimers();

    expect(nav?.classList.contains("is-hidden")).toBe(false);
    await unmount();
  });

  it("cancels the pending reveal when the cursor leaves the viewport before the delay elapses", async () => {
    const { host, unmount } = await mount(
      <NavShell brand="digithings" links={ITEMS} showThemeToggle={false} autoHide="hover" />,
    );
    const nav = host.querySelector("header.nav-shell");

    vi.useFakeTimers();
    moveIntoHotZone(); // starts the dwell timer
    leaveViewport(); // pointer exits before it fires — e.g. a flick toward browser chrome
    vi.advanceTimersByTime(150); // well past the 120ms delay
    vi.useRealTimers();

    // Still hidden: the timer was cancelled, not merely racing a slower reveal.
    expect(nav?.classList.contains("is-hidden")).toBe(true);
    await unmount();
  });
});
