// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { createElement } from "react";
import {
  ChatEmbedShell,
  WARMUP_DELAY_MS,
} from "@/components/ChatEmbedShell";

/**
 * The cold-start cover, rendered. One animation for every surface: the
 * digichat hero banner's LOADING pass, which is what digichat paints itself.
 * The old BootLabOverlay tool-call rows must be unreachable — no prop, no
 * variant, no caller can bring them back.
 *
 * Mocked only: fetch is stubbed (the services probe never resolves) and no
 * frame really loads. Everything else is the real shell.
 */
describe("ChatEmbedShell cold-start cover", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    window.history.replaceState(null, "", "/chat");
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("paints the digichat hero banner and cannot paint the tool-call rows", async () => {
    render(createElement(ChatEmbedShell, { embedOrigin: window.location.origin }));

    // A warm load never flashes the cover (WARMUP_DELAY_MS).
    expect(screen.queryByRole("img", { name: "digichat" })).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(WARMUP_DELAY_MS + 1);
    });

    const banner = screen.getByRole("img", { name: "digichat" });
    expect(banner.tagName).toBe("CANVAS");
    expect(banner.getAttribute("class") ?? "").not.toContain("dboot-lab");

    // The screen-reader line stays with the cover.
    expect(screen.getByText("Loading chat…")).toBeTruthy();

    // The old tool-call animation is gone: no boot-lab root, no tool rows, no
    // variant switch to select one.
    expect(document.querySelector(".dboot-lab")).toBeNull();
    expect(document.querySelector(".dboot-lab-tools")).toBeNull();
    expect(document.querySelector(".aui-tool-fallback-trigger")).toBeNull();
    expect(document.querySelector("[data-variant]")).toBeNull();
  });

  it("shows the same cover on the landing pop-up as on the full-page chat", async () => {
    // LiveAsk passes no loader preference at all; the cover is still the banner.
    const { unmount } = render(
      createElement(ChatEmbedShell, { embedOrigin: window.location.origin }),
    );
    await act(async () => {
      vi.advanceTimersByTime(WARMUP_DELAY_MS + 1);
    });
    expect(screen.getByRole("img", { name: "digichat" })).toBeTruthy();
    unmount();
  });
});
