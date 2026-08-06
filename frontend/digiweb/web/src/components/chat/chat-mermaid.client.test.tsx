// @vitest-environment happy-dom
/**
 * Client behaviour of <ChatMermaidBlock> — the half the SSR suite cannot see.
 *
 * mermaid is mocked rather than executed: what is under test is OUR contract
 * (lazy import, token-filled themeVariables, strict security, the fallback on a
 * malformed graph), not mermaid's layout engine, and a real mermaid run in a
 * synthetic DOM measures text it cannot measure. The mock also lets the
 * malformed case be deterministic instead of depending on a parser message.
 */
import type { ReactElement } from "react";
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatMarkdown } from "./ChatMarkdown";
import { ChatMermaidBlock } from "./ChatMermaidBlock";

const initialize = vi.fn();
const parse = vi.fn();
const render = vi.fn();

vi.mock("mermaid", () => ({ default: { initialize, parse, render } }));

const DIAGRAM = "graph TD;\n  A-->B;";
const FAKE_SVG = '<svg id="drawn" role="graphics-document"><g></g></svg>';

async function mount(ui: ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

beforeEach(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
  document.documentElement.removeAttribute("data-theme");
  initialize.mockReset();
  parse.mockReset().mockResolvedValue({ diagramType: "flowchart" });
  render.mockReset().mockResolvedValue({ svg: FAKE_SVG });
});

afterEach(() => {
  document.body.innerHTML = "";
});

describe("ChatMermaidBlock — drawn", () => {
  it("replaces the source fallback with the rendered SVG", async () => {
    const { host } = await mount(<ChatMermaidBlock code={DIAGRAM} />);
    const figure = host.querySelector(".chat-md-mermaid");

    expect(figure?.getAttribute("data-state")).toBe("diagram");
    expect(host.querySelector(".chat-md-mermaid-fig svg")).not.toBeNull();
    expect(host.querySelector(".chat-md-mermaid pre")).toBeNull();
  });

  it("keeps the source one click away behind an expandable toggle", async () => {
    const { host } = await mount(<ChatMermaidBlock code={DIAGRAM} />);
    const toggle = host.querySelector<HTMLButtonElement>("button[aria-expanded]");

    expect(toggle?.getAttribute("aria-expanded")).toBe("false");
    await act(async () => {
      toggle?.click();
    });
    expect(toggle?.getAttribute("aria-expanded")).toBe("true");
    expect(host.querySelector(".chat-md-mermaid pre")?.textContent).toContain("A-->B;");
  });

  it("initializes strict + token-themed, and gives mermaid a selector-safe id", async () => {
    await mount(<ChatMermaidBlock code={DIAGRAM} />);
    const config = initialize.mock.calls[0]?.[0];

    expect(config.securityLevel).toBe("strict");
    expect(config.suppressErrorRendering).toBe(true);
    expect(config.flowchart.htmlLabels).toBe(false);
    // theme "base" is the only built-in palette that honours themeVariables
    expect(config.theme).toBe("base");
    expect(config.themeVariables).toBeTypeOf("object");

    const id = render.mock.calls[0]?.[0];
    expect(id).toMatch(/^chat-mermaid-[A-Za-z0-9]+$/);
  });

  it("re-reads the tokens and redraws when the theme flips", async () => {
    await mount(<ChatMermaidBlock code={DIAGRAM} />);
    expect(render).toHaveBeenCalledTimes(1);

    await act(async () => {
      document.documentElement.setAttribute("data-theme", "light");
    });
    expect(render.mock.calls.length).toBeGreaterThan(1);
    expect(initialize.mock.calls.length).toBeGreaterThan(1);
  });
});

describe("ChatMermaidBlock — malformed", () => {
  it("falls back to the verbatim source without throwing", async () => {
    parse.mockRejectedValue(new Error("Parse error on line 1: not-a-diagram"));
    const { host } = await mount(<ChatMermaidBlock code={"not-a-diagram {{{"} />);
    const figure = host.querySelector(".chat-md-mermaid");

    expect(figure?.getAttribute("data-state")).toBe("source");
    expect(host.querySelector("svg")).toBeNull();
    expect(host.querySelector(".chat-md-mermaid pre")?.textContent).toContain("not-a-diagram {{{");
    // never reached render(), so nothing was injected into the document
    expect(render).not.toHaveBeenCalled();
  });

  it("does not take the rest of the transcript down with it", async () => {
    parse.mockRejectedValue(new Error("Parse error"));
    const { host } = await mount(
      <ChatMarkdown source={"intro text\n\n```mermaid\nbroken {{{\n```\n\nclosing text\n"} />,
    );

    expect(host.textContent).toContain("intro text");
    expect(host.textContent).toContain("closing text");
    expect(host.querySelector(".chat-md-mermaid")?.getAttribute("data-state")).toBe("source");
  });

  it("survives mermaid failing to load at all", async () => {
    parse.mockImplementation(() => {
      throw new Error("chunk load failed");
    });
    const { host } = await mount(<ChatMermaidBlock code={DIAGRAM} />);

    expect(host.querySelector(".chat-md-mermaid")?.getAttribute("data-state")).toBe("source");
    expect(host.querySelector(".chat-md-mermaid pre")?.textContent).toContain("A-->B;");
  });
});
