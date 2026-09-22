/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DigichatLauncher, matchesHotkey } from "./DigichatLauncher";

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

  describe("hotkey", () => {
    function renderWithHotkey(hotkey: string, onOpenChange = vi.fn()) {
      act(() => {
        root.render(
          createElement(
            DigichatLauncher,
            { portal: false, hotkey, onOpenChange },
            createElement("div", { "data-chat-body": "1" }),
          ),
        );
      });
      return onOpenChange;
    }

    function press(init: KeyboardEventInit) {
      act(() => {
        window.dispatchEvent(new KeyboardEvent("keydown", init));
      });
    }

    it("matches the configured modifiers only", () => {
      expect(matchesHotkey(new KeyboardEvent("keydown", { key: "k", metaKey: true }), "mod+k")).toBe(
        true,
      );
      expect(matchesHotkey(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }), "mod+k")).toBe(
        true,
      );
      // `mod` is ctrl-or-meta; neither present must not match.
      expect(matchesHotkey(new KeyboardEvent("keydown", { key: "k" }), "mod+k")).toBe(false);
      // A named modifier pins exactly that one.
      expect(
        matchesHotkey(new KeyboardEvent("keydown", { key: "k", metaKey: true }), "ctrl+k"),
      ).toBe(false);
      // Shift is checked strictly, so `mod+k` must not fire on `mod+shift+k`.
      expect(
        matchesHotkey(new KeyboardEvent("keydown", { key: "k", metaKey: true, shiftKey: true }), "mod+k"),
      ).toBe(false);
      // A different key never matches.
      expect(matchesHotkey(new KeyboardEvent("keydown", { key: "j", metaKey: true }), "mod+k")).toBe(
        false,
      );
    });

    it("opens the panel from the configured hotkey", () => {
      const onOpenChange = renderWithHotkey("mod+k");
      expect(container.querySelector(".digichat-launcher__panel")).toBeNull();

      press({ key: "k", metaKey: true });

      expect(onOpenChange).toHaveBeenLastCalledWith(true);
      expect(
        container.querySelector(".digichat-launcher__panel:not(.is-hidden)"),
      ).not.toBeNull();
    });

    it("ignores the key without its modifier", () => {
      const onOpenChange = renderWithHotkey("mod+k");

      press({ key: "k" });

      expect(onOpenChange).not.toHaveBeenCalled();
      expect(container.querySelector(".digichat-launcher__panel")).toBeNull();
    });

    it("does not re-open from the hotkey once the panel is up", () => {
      const onOpenChange = renderWithHotkey("mod+k");
      press({ key: "k", metaKey: true });

      press({ key: "k", metaKey: true });

      expect(onOpenChange).toHaveBeenCalledTimes(1);
    });

    it("binds nothing when no hotkey is configured", () => {
      const onOpenChange = vi.fn();
      act(() => {
        root.render(
          createElement(
            DigichatLauncher,
            { portal: false, onOpenChange },
            createElement("div", { "data-chat-body": "1" }),
          ),
        );
      });

      press({ key: "k", metaKey: true });

      expect(onOpenChange).not.toHaveBeenCalled();
    });
  });
});
