// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import { PrivateWorkStep, privateWorkStepLabel } from "./private-work-step";

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

let root: Root | null = null;
let host: HTMLElement | null = null;

function render(node: React.ReactNode): HTMLElement {
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
  act(() => root!.render(node));
  return host;
}

afterEach(() => {
  act(() => root?.unmount());
  host?.remove();
  root = null;
  host = null;
});

describe("privateWorkStepLabel", () => {
  it("uses the normal tool row wording", () => {
    expect(privateWorkStepLabel({ kind: "tool", statusType: "complete" })).toEqual({
      label: "Used tool",
      state: "success",
    });
    expect(privateWorkStepLabel({ kind: "tool", statusType: "complete", isError: true }).label).toBe(
      "Failed tool",
    );
    expect(
      privateWorkStepLabel({ kind: "tool", statusType: "incomplete", reason: "error" }).label,
    ).toBe("Failed tool");
    expect(
      privateWorkStepLabel({ kind: "tool", statusType: "incomplete", reason: "cancelled" }),
    ).toEqual({ label: "Cancelled tool", state: "idle" });
    expect(privateWorkStepLabel({ kind: "tool", statusType: "running" })).toEqual({
      label: "Running tool",
      state: "tool",
    });
    expect(privateWorkStepLabel({ kind: "tool", statusType: "requires-action" }).label).toBe(
      "Waiting on tool",
    );
  });

  it("labels reasoning Reasoning, with the normal row's glyphs", () => {
    expect(privateWorkStepLabel({ kind: "reasoning", statusType: "running" })).toEqual({
      label: "Reasoning",
      state: "thinking",
    });
    expect(privateWorkStepLabel({ kind: "reasoning", statusType: "complete" })).toEqual({
      label: "Reasoning",
      state: "thought",
    });
  });
});

describe("PrivateWorkStep", () => {
  it("draws the normal tool row, but nothing that opens", () => {
    const el = render(<PrivateWorkStep kind="tool" toolName="search_tickets" statusType="complete" />);
    const row = el.querySelector('[data-slot="tool-fallback-trigger"]');
    expect(row).not.toBeNull();
    expect(row?.hasAttribute("data-private")).toBe(true);
    expect(row?.textContent).toContain("Used tool: search_tickets");
    expect(row?.querySelector('[data-slot="dot-matrix"]')?.getAttribute("data-state")).toBe("success");
    expect(row?.className).toContain("pointer-events-none");
    expect(row?.className).not.toMatch(/hover:|active:/);
    expect(el.querySelector("button")).toBeNull();
    expect(el.querySelector("[aria-expanded]")).toBeNull();
    expect(el.querySelector(".aui-disclosure-chevron")).toBeNull();
    expect(el.querySelector("details")).toBeNull();
  });

  it("draws the normal reasoning row, running and done", () => {
    const running = render(<PrivateWorkStep kind="reasoning" statusType="running" />);
    const row = running.querySelector('[data-slot="reasoning-trigger"]');
    expect(row?.textContent).toBe("Reasoning");
    expect(row?.querySelector('[data-slot="dot-matrix"]')?.getAttribute("data-state")).toBe("thinking");
    expect(row?.querySelector('[data-slot="reasoning-trigger-label"]')?.className).toContain("shimmer");
    expect(running.querySelector("button")).toBeNull();
    expect(running.querySelector(".aui-disclosure-chevron")).toBeNull();
  });

  it("shows a failed step as failed", () => {
    const el = render(<PrivateWorkStep kind="tool" toolName="search" statusType="complete" isError />);
    expect(el.textContent).toContain("Failed tool");
    expect(el.querySelector('[data-state="error"]')).not.toBeNull();
  });
});
