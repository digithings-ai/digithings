// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";

import { TooltipIconButton } from "./tooltip-icon-button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "./ui/tooltip";
import { Button } from "./ui/button";

/** Rendered base-skin overlays carry theme tokens only (mocked, no runtime). */
let root: Root | null = null;
let host: HTMLDivElement | null = null;

function mount(node: React.ReactNode) {
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  act(() => root!.render(node));
}

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
  document.body.innerHTML = "";
});

const DIGICHAT = /\b(rounded-none|bg-ink|text-ink|bg-surface-2|border-hair)\b/;

describe("base skin overlays", () => {
  it("an open tooltip portals a rounded foreground chip", () => {
    mount(
      <TooltipProvider>
        <Tooltip open>
          <TooltipTrigger render={<button type="button">t</button>} />
          <TooltipContent>Copy</TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    const popup = document.body.querySelector<HTMLElement>("[data-slot=tooltip-content]");
    expect(popup).not.toBeNull();
    expect(popup!.className).toContain("rounded-md");
    expect(popup!.className).toContain("bg-foreground");
    expect(popup!.className).toContain("text-background");
    expect(popup!.className).not.toMatch(DIGICHAT);
  });

  it("the timing pane override keeps the popover tokens and a rounded corner", () => {
    mount(
      <TooltipProvider>
        <Tooltip open>
          <TooltipTrigger render={<button type="button">t</button>} />
          <TooltipContent className="bg-popover text-popover-foreground border px-3 py-2">
            First token 120ms
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>,
    );
    const popup = document.body.querySelector<HTMLElement>("[data-slot=tooltip-content]")!;
    expect(popup.className).toContain("bg-popover");
    expect(popup.className).not.toContain("bg-foreground");
    expect(popup.className).toContain("rounded-md");
  });

  it("icon buttons hover on muted, not the digichat surface", () => {
    mount(<TooltipIconButton tooltip="Copy">c</TooltipIconButton>);
    const button = host!.querySelector("button")!;
    expect(button.className).toContain("hover:bg-muted");
    expect(button.className).not.toMatch(DIGICHAT);
    mount(<Button variant="outline">o</Button>);
    expect(host!.querySelector("button")!.className).toContain("border-border");
  });
});
