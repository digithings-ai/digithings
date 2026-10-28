// @vitest-environment happy-dom
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
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
  it("labels tool outcomes", () => {
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
    expect(privateWorkStepLabel({ kind: "tool", statusType: "running" }).label).toBe("Running tool");
  });

  it("labels reasoning", () => {
    expect(privateWorkStepLabel({ kind: "reasoning", statusType: "running" }).label).toBe("Thinking");
    expect(privateWorkStepLabel({ kind: "reasoning", statusType: "complete" }).label).toBe("Thought");
  });
});

describe("PrivateWorkStep", () => {
  it("shows the step and its outcome but nothing that opens", () => {
    const el = render(<PrivateWorkStep kind="tool" toolName="search_tickets" statusType="complete" />);
    const step = el.querySelector('[data-slot="aui_private-work-step"]');
    expect(step).not.toBeNull();
    expect(step?.textContent).toContain("Used tool");
    expect(step?.getAttribute("data-state")).toBe("success");
    expect(el.querySelector("button")).toBeNull();
    expect(el.querySelector("[aria-expanded]")).toBeNull();
    expect(el.querySelector("details")).toBeNull();
  });

  it("shows a failed step as failed", () => {
    const el = render(<PrivateWorkStep kind="tool" toolName="search" statusType="complete" isError />);
    expect(el.textContent).toContain("Failed tool");
    expect(el.querySelector('[data-state="error"]')).not.toBeNull();
  });
});

describe("thread.aui private mode wiring", () => {
  const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "thread.aui.tsx"), "utf8");
  it("renders tool calls and reasoning as PrivateWorkStep, not null or a disclosure", () => {
    expect(src).toMatch(/case "reasoning": \{\s*if \(privateMode\) return <PrivateWorkStep kind="reasoning"/);
    expect(src).toMatch(/case "tool-call":\s*if \(privateMode\) \{[\s\S]{0,200}<PrivateWorkStep\s+kind="tool"/);
    expect(src).not.toMatch(/if \(privateMode\) return null;/);
  });
});

describe("thread.aui private chain", () => {
  const src = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "thread.aui.tsx"), "utf8");
  it("renders the chain flat, with no folding WorkChain header, in a private session", () => {
    expect(src).toMatch(
      /if \(privateMode\) \{\s*return \(\s*<div data-slot="aui_chain-of-thought" data-private="">\s*\{children\}/,
    );
  });
});
