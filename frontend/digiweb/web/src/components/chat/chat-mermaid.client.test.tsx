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

/** Drive React turns until *predicate* holds, or fail loudly naming what never happened. */
async function waitUntil(predicate: () => boolean, what: string, turns = 100) {
  for (let i = 0; i < turns; i += 1) {
    if (predicate()) return;
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0));
    });
  }
  throw new Error(`never became true after ${turns} turns: ${what}`);
}

const stateOf = (host: HTMLElement) =>
  host.querySelector(".chat-md-mermaid")?.getAttribute("data-state") ?? null;

/** Wait for the figure to exist AND leave `pending` — both halves matter. */
const settled = (host: HTMLElement) =>
  waitUntil(
    () => {
      const s = stateOf(host);
      return s !== null && s !== "pending";
    },
    'a .chat-md-mermaid figure past data-state="pending"',
  );

async function mount(ui: ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(ui);
  });
  await settled(host);
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

// KNOWN LOAD SENSITIVITY — read before removing the `retry`.
//
// These seven exercise an effect chain that is several async hops deep:
// a MutationObserver on <html data-theme> bumps state, the effect re-runs,
// `await import("mermaid")` resolves, then parse() and render() settle. The waits
// below are predicate-based (not timeouts), which fixed the common races — an earlier
// version waited for `pending` to clear, which is already true after the first paint,
// so the redraw assertion ran against stale mock counts.
//
// What is NOT fixed: under heavy CPU starvation the observer→effect→import chain can
// fail to complete at all. Measured on a laptop with three concurrent Next builds:
// 0/4 clean before the predicate waits, 2/5 after, with the theme-flip case still
// failing after ~50s of yielding — so it is not turn-starvation that more patience
// resolves. Unloaded, the full suite is 83/83 across five consecutive runs, twice.
//
// A dedicated CI runner is the unloaded case, so `retry: 2` should never engage there.
// It is here so that wiring this suite into a REQUIRED lane (#1948) cannot make an
// unrelated PR intermittently red — the failure mode this repo has repeatedly paid for.
// The retry is deliberately narrow (this file only) and loud (this comment), not a
// suite-wide default. Removing it is correct once the chain is made deterministic —
// most likely by driving the observer explicitly rather than relying on happy-dom
// delivering it under load.
describe("ChatMermaidBlock — drawn", { retry: 2 }, () => {
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

  it("hands mermaid a quoted label, but shows the model's raw text as source", async () => {
    const raw = "flowchart TD\n C[List locations (Exchange, OneDrive, Blob)]";
    const { host } = await mount(<ChatMermaidBlock code={raw} />);

    expect(parse).toHaveBeenCalledWith('flowchart TD\n C["List locations (Exchange, OneDrive, Blob)"]');
    expect(render).toHaveBeenCalledWith(
      expect.any(String),
      'flowchart TD\n C["List locations (Exchange, OneDrive, Blob)"]',
    );

    const toggle = host.querySelector<HTMLButtonElement>("button[aria-expanded]");
    await act(async () => {
      toggle?.click();
    });
    // The reader still sees exactly what the model wrote, unquoted.
    expect(host.querySelector(".chat-md-mermaid pre")?.textContent).toContain(
      "C[List locations (Exchange, OneDrive, Blob)]",
    );
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
    // Wait for the SECOND render, not for `pending` to clear: the figure is already
    // "diagram" from the first paint, so a pending-based wait returns instantly and
    // the assertion races the redraw. This was the 5s-timeout mode.
    await waitUntil(() => render.mock.calls.length > 1, "a second mermaid render");
    expect(initialize.mock.calls.length).toBeGreaterThan(1);
  });
});

describe("ChatMermaidBlock — malformed", { retry: 2 }, () => {
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
