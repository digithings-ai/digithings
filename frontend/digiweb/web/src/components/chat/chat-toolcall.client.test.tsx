// @vitest-environment happy-dom
/**
 * Client behaviour of <ChatToolCall> — the half SSR cannot see.
 *
 * digichat-ui keys tool rows by identity across tool_call → tool_result, so
 * the same ChatToolCall instance receives `defaultOpen: true` on settle
 * without remounting. useState alone would keep the closed initial state and
 * leave citations out of the DOM (body mounts only while open).
 */
import type { ReactElement } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { ChatToolCall } from "./ChatToolCall";

async function mount(ui: ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  return {
    host,
    rerender: (next: ReactElement) => act(() => root.render(next)),
    unmount: () => act(() => root.unmount()),
  };
}

afterEach(() => {
  document.body.replaceChildren();
});

describe("ChatToolCall — defaultOpen across a stable-key settle", () => {
  it("adopts defaultOpen when a bodyless running row settles with citations", async () => {
    const { host, rerender, unmount } = await mount(
      <ChatToolCall name="digivault.search" args="auth" status="running" />,
    );

    // In flight: plain head, no disclosure, no body.
    expect(host.querySelector("[aria-expanded]")).toBeNull();
    expect(host.textContent).not.toContain("Auth overview");

    await rerender(
      <ChatToolCall name="digivault.search" args="auth" status="ok" defaultOpen>
        <ul>
          <li>Auth overview</li>
        </ul>
      </ChatToolCall>,
    );

    const toggle = host.querySelector("[aria-expanded]");
    expect(toggle).not.toBeNull();
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    expect(host.textContent).toContain("Auth overview");

    await unmount();
  });

  it("does not re-open after the reader has collapsed the block", async () => {
    const { host, rerender, unmount } = await mount(
      <ChatToolCall name="digivault.search" args="auth" status="ok" defaultOpen>
        <ul>
          <li>Auth overview</li>
        </ul>
      </ChatToolCall>,
    );

    const button = host.querySelector("button");
    expect(button?.getAttribute("aria-expanded")).toBe("true");

    await act(async () => {
      button?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(host.querySelector("button")?.getAttribute("aria-expanded")).toBe("false");
    expect(host.textContent).not.toContain("Auth overview");

    // A later prop refresh that still says defaultOpen must not fight the reader.
    await rerender(
      <ChatToolCall name="digivault.search" args="auth" status="ok" defaultOpen>
        <ul>
          <li>Auth overview</li>
        </ul>
      </ChatToolCall>,
    );
    expect(host.querySelector("button")?.getAttribute("aria-expanded")).toBe("false");
    expect(host.textContent).not.toContain("Auth overview");

    await unmount();
  });
});
