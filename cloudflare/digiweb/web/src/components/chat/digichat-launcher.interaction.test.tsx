/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DigichatLauncher } from "./DigichatLauncher";

describe("DigichatLauncher interactions", () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    vi.useFakeTimers();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  function renderLauncher(onOpenChange = vi.fn()) {
    act(() => {
      root.render(
        createElement(
          DigichatLauncher,
          { portal: false, onOpenChange },
          createElement("div", { "data-chat-body": "1" }),
        ),
      );
    });
    return onOpenChange;
  }

  it("types the wordmark without replacing the square trigger", () => {
    renderLauncher();
    const trigger = container.querySelector(
      ".digichat-launcher__trigger",
    ) as HTMLButtonElement;

    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseover", { bubbles: true }));
      vi.advanceTimersByTime(400);
    });

    expect(trigger.hasAttribute("data-typing")).toBe(true);
    expect(
      trigger.querySelector(".digichat-launcher__word")?.textContent,
    ).toBe("digichat");

    act(() => {
      trigger.dispatchEvent(new MouseEvent("mouseout", { bubbles: true }));
    });
    expect(trigger.hasAttribute("data-typing")).toBe(false);
    expect(
      trigger.querySelector(".digichat-launcher__word")?.textContent,
    ).toBe("d");
  });

  it("opens in place and Escape reverses the panel back to the trigger", () => {
    const onOpenChange = renderLauncher();
    const trigger = container.querySelector(
      ".digichat-launcher__trigger",
    ) as HTMLButtonElement;

    act(() => trigger.click());
    expect(container.querySelector(".digichat-launcher__panel")).not.toBeNull();
    expect(onOpenChange).toHaveBeenCalledWith(true);
    const chatBody = container.querySelector("[data-chat-body]");

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(
      container.querySelector(".digichat-launcher__panel.is-closing"),
    ).not.toBeNull();

    act(() => vi.advanceTimersByTime(340));
    expect(
      container.querySelector(".digichat-launcher__panel.is-hidden"),
    ).not.toBeNull();
    expect(container.querySelector(".digichat-launcher__trigger")).not.toBeNull();
    expect(onOpenChange).toHaveBeenLastCalledWith(false);

    const reopenedTrigger = container.querySelector(
      ".digichat-launcher__trigger",
    ) as HTMLButtonElement;
    act(() => reopenedTrigger.click());
    expect(container.querySelector("[data-chat-body]")).toBe(chatBody);
    expect(
      container.querySelector(".digichat-launcher__panel.is-hidden"),
    ).toBeNull();
  });

  it("dismisses when the transparent outside-click backdrop is clicked", () => {
    const onOpenChange = renderLauncher();
    const trigger = container.querySelector(
      ".digichat-launcher__trigger",
    ) as HTMLButtonElement;

    act(() => trigger.click());
    const backdrop = container.querySelector(
      ".digichat-launcher__backdrop",
    ) as HTMLButtonElement;
    act(() => backdrop.click());
    act(() => vi.advanceTimersByTime(340));

    expect(
      container.querySelector(".digichat-launcher__panel.is-hidden"),
    ).not.toBeNull();
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });

  it("closes immediately when reduced motion is requested", () => {
    vi.spyOn(window, "matchMedia").mockImplementation(
      (query) =>
        ({
          matches: query === "(prefers-reduced-motion: reduce)",
        }) as MediaQueryList,
    );
    const onOpenChange = renderLauncher();
    const trigger = container.querySelector(
      ".digichat-launcher__trigger",
    ) as HTMLButtonElement;

    act(() => trigger.click());
    const close = container.querySelector(
      ".digichat-launcher__close",
    ) as HTMLButtonElement;
    act(() => close.click());

    expect(
      container.querySelector(".digichat-launcher__panel.is-hidden"),
    ).not.toBeNull();
    expect(container.querySelector(".digichat-launcher__trigger")).not.toBeNull();
    expect(onOpenChange).toHaveBeenLastCalledWith(false);
  });
});
