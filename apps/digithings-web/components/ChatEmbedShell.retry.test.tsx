// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createElement } from "react";
import {
  ChatEmbedShell,
  EMBED_LOAD_ERROR_RETRY,
  EMBED_LOAD_ERROR_TITLE,
  EMBED_SHELL_CLASS,
  OCC_CHAT_EMBED_HOST,
} from "@/components/ChatEmbedShell";

/**
 * Retry behaviour, rendered (jsdom). Mocked only: fetch is stubbed (the
 * services probe never resolves), no frame really loads, no network, no model.
 */
function fakeDocument(html: string): Document {
  const doc = document.implementation.createHTMLDocument("embed");
  doc.body.innerHTML = html;
  Object.defineProperty(doc, "URL", { value: "http://localhost:3000/embed" });
  return doc;
}

function frame(): HTMLIFrameElement {
  const el = document.getElementById("dc-digichat-frame");
  if (!(el instanceof HTMLIFrameElement)) throw new Error("no embed frame");
  return el;
}

function loadFrameWith(doc: Document) {
  const el = frame();
  Object.defineProperty(el, "contentDocument", { configurable: true, value: doc });
  fireEvent.load(el);
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

describe("ChatEmbedShell retry", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => {})));
    window.history.replaceState(null, "", "/chat/occ?token=invite-fixture");
  });
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  });

  it("an error page in the frame shows the card; Retry remounts the frame with the key kept", async () => {
    render(
      createElement(ChatEmbedShell, {
        embedOrigin: window.location.origin,
        embedHost: OCC_CHAT_EMBED_HOST,
        acceptsInviteToken: true,
        warmupLoader: "banner",
      }),
    );
    await flush();
    const first = frame();
    expect(first.getAttribute("src")).toContain("token=invite-fixture");
    // The key left the address bar once read.
    expect(window.location.search).not.toContain("token=");

    loadFrameWith(fakeDocument("<h1>Internal Server Error</h1>"));
    await flush();
    expect(screen.getByText(EMBED_LOAD_ERROR_TITLE)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: EMBED_LOAD_ERROR_RETRY }));
    await flush();
    expect(screen.queryByText(EMBED_LOAD_ERROR_TITLE)).toBeNull();
    const second = frame();
    expect(second).not.toBe(first);
    expect(second.getAttribute("src")).toContain("token=invite-fixture");

    // The fresh frame is the chat this time: no card.
    loadFrameWith(fakeDocument(`<div class="${EMBED_SHELL_CLASS}"></div>`));
    await flush();
    expect(screen.queryByText(EMBED_LOAD_ERROR_TITLE)).toBeNull();
  });

  it("after Retry the ready timeout is armed again", async () => {
    vi.useFakeTimers();
    render(
      createElement(ChatEmbedShell, {
        embedOrigin: window.location.origin,
        embedHost: OCC_CHAT_EMBED_HOST,
        acceptsInviteToken: true,
        warmupLoader: "banner",
      }),
    );
    await flush();
    // Never loads, never says ready: the card after the ready timeout.
    await act(async () => {
      vi.advanceTimersByTime(31_000);
    });
    expect(screen.getByText(EMBED_LOAD_ERROR_TITLE)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: EMBED_LOAD_ERROR_RETRY }));
    await flush();
    expect(screen.queryByText(EMBED_LOAD_ERROR_TITLE)).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(31_000);
    });
    expect(screen.getByText(EMBED_LOAD_ERROR_TITLE)).toBeTruthy();
  });

  it("a loaded frame that cannot be read as the chat gets the card, not a raw reveal", async () => {
    vi.useFakeTimers();
    render(
      createElement(ChatEmbedShell, {
        embedOrigin: window.location.origin,
        embedHost: OCC_CHAT_EMBED_HOST,
        acceptsInviteToken: true,
        warmupLoader: "banner",
      }),
    );
    await flush();
    // Cross-origin: contentDocument is null, so onLoad cannot tell.
    loadFrameWith(null as unknown as Document);
    await act(async () => {
      vi.advanceTimersByTime(31_000);
    });
    expect(screen.getByText(EMBED_LOAD_ERROR_TITLE)).toBeTruthy();
  });
});
