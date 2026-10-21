// @vitest-environment happy-dom
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { ToolGroupContent, ToolGroupRoot, ToolGroupTrigger } from "./tool-group.aui";

/**
 * The stock tool-group row outside the DigiChat skin: no `digichat-thread`,
 * no `data-thread-skin="digichat"`. Its caret used to turn with Tailwind
 * utilities in the TSX; it now turns from chat-aui.css's skin-agnostic base
 * rule, so this mounts the real stylesheet and reads the computed transform.
 */
const here = dirname(fileURLToPath(import.meta.url));
const css = readFileSync(join(here, "../../../styles/chat-aui.css"), "utf8");

afterEach(() => {
  document.head.replaceChildren();
  document.body.replaceChildren();
});

function grid(host: HTMLElement) {
  const trigger = host.querySelector<HTMLElement>('[data-slot="tool-group-trigger"]')!;
  const caret = trigger.querySelector<HTMLElement>(':scope > [data-slot="disclosure-chevron"]');
  expect(caret, "caret is a direct child of the trigger").toBeTruthy();
  const svg = caret!.querySelector<SVGElement>('[data-slot="dot-matrix-grid"]')!;
  return { trigger, svg };
}

describe("stock tool-group caret", () => {
  it("turns with its own row in a non-digichat skin", async () => {
    const style = document.createElement("style");
    style.textContent = css;
    document.head.append(style);
    const host = document.createElement("div");
    host.className = "aui-root aui-thread-root";
    host.setAttribute("data-thread-skin", "base");
    document.body.append(host);
    const root = createRoot(host);
    await act(async () => {
      root.render(
        <ToolGroupRoot>
          <ToolGroupTrigger count={2} />
          <ToolGroupContent>tools</ToolGroupContent>
        </ToolGroupRoot>,
      );
    });

    const closed = grid(host);
    expect(closed.trigger.getAttribute("aria-expanded")).toBe("false");
    expect(getComputedStyle(closed.svg).transform).not.toContain("rotate(90deg)");

    await act(async () => {
      closed.trigger.click();
    });
    const open = grid(host);
    expect(open.trigger.getAttribute("aria-expanded")).toBe("true");
    expect(getComputedStyle(open.svg).transform).toContain("rotate(90deg)");

    await act(async () => root.unmount());
  });
});
