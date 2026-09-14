// @vitest-environment jsdom
/**
 * Behaviour of the assistant-ui elements-catalog <MermaidDiagram> base
 * (props-driven, no runtime required).
 *
 * beautiful-mermaid is mocked rather than executed: what is under test is OUR
 * contract (skeleton while streaming, outer-only diagram on success, raw-source
 * fallback on parse failure, sanitized SVG before injection), not mermaid's
 * layout engine.
 *
 * jsdom, not happy-dom: the component now sanitizes the renderer output with
 * DOMPurify, which needs a spec-compliant DOM to make its allow/deny decisions.
 * Under happy-dom, DOMPurify returned "" for a pristine SVG and passed
 * `<script>` through untouched — see mermaid-svg-sanitize.test.ts.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MermaidDiagram } from "./mermaid-diagram";

const renderMermaidSVG = vi.fn();

vi.mock("beautiful-mermaid", () => ({
  get renderMermaidSVG() {
    return renderMermaidSVG;
  },
}));

const DIAGRAM = "flowchart LR\n  U[User] --> A[digichat]";
const FAKE_SVG = '<svg role="graphics-document"><g></g></svg>';

function mount(ui: React.ReactElement) {
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => {
    root.render(ui);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

describe("MermaidDiagram", () => {
  it("shows a skeleton while streaming without parsing", () => {
    renderMermaidSVG.mockReset();
    const { host, unmount } = mount(
      <MermaidDiagram code={DIAGRAM} streaming />,
    );
    try {
      expect(renderMermaidSVG).not.toHaveBeenCalled();
      expect(host.querySelector('[data-slot="mermaid-skeleton"]')).toBeTruthy();
      expect(host.querySelector('[data-slot="mermaid-diagram"]')).toBeNull();
    } finally {
      unmount();
      host.remove();
    }
  });

  it("renders the outer diagram only, with no nested source", () => {
    renderMermaidSVG.mockReset().mockReturnValue(FAKE_SVG);
    const { host, unmount } = mount(
      <MermaidDiagram code={DIAGRAM} streaming={false} />,
    );
    try {
      const diagram = host.querySelector('[data-slot="mermaid-diagram"]');
      expect(diagram).toBeTruthy();
      expect(diagram?.innerHTML).toContain("<svg");
      // Outer only: the raw mermaid source must not appear beside the diagram.
      expect(host.textContent).not.toContain("flowchart LR");
      expect(host.querySelector('[data-slot="mermaid-fallback"]')).toBeNull();
      expect(host.querySelector('[data-slot="mermaid-skeleton"]')).toBeNull();
    } finally {
      unmount();
      host.remove();
    }
  });

  it("neutralizes script/handler content before injecting the renderer SVG", () => {
    renderMermaidSVG
      .mockReset()
      .mockReturnValue(
        [
          '<svg role="graphics-document">',
          "<script>alert('script')</script>",
          '<rect width="5" height="5" onload="alert(\'handler\')"/>',
          '<a href="javascript:alert(\'uri\')"><text>ok</text></a>',
          "<foreignObject><img src=x onerror=\"alert('fo')\"/></foreignObject>",
          "</svg>",
        ].join(""),
      );
    const { host, unmount } = mount(
      <MermaidDiagram code={DIAGRAM} streaming={false} />,
    );
    try {
      const diagram = host.querySelector('[data-slot="mermaid-diagram"]');
      expect(diagram).toBeTruthy();
      // A legitimate diagram still renders…
      expect(diagram?.innerHTML).toContain("<svg");
      expect(diagram?.querySelector("text")?.textContent).toBe("ok");
      // …but no active content reaches the DOM.
      expect(diagram?.querySelector("script")).toBeNull();
      expect(diagram?.querySelector("foreignObject")).toBeNull();
      expect(diagram?.innerHTML).not.toMatch(/on\w+=/i);
      expect(diagram?.innerHTML).not.toContain("javascript:");
    } finally {
      unmount();
      host.remove();
    }
  });

  it("neutralizes the zoom overlay's copy of the SVG too", () => {
    renderMermaidSVG
      .mockReset()
      .mockReturnValue(
        '<svg role="graphics-document"><script>alert(1)</script><rect width="5" height="5" onload="alert(2)"/></svg>',
      );
    const { host, unmount } = mount(
      <MermaidDiagram code={DIAGRAM} streaming={false} />,
    );
    try {
      const trigger = host.querySelector<HTMLButtonElement>(
        '[data-slot="mermaid-zoom-trigger"]',
      );
      expect(trigger).toBeTruthy();
      act(() => {
        trigger?.click();
      });
      const content = document.querySelector(
        '[data-slot="mermaid-zoom-content"]',
      );
      expect(content).toBeTruthy();
      expect(content?.innerHTML).toContain("<svg");
      expect(content?.querySelector("script")).toBeNull();
      expect(content?.innerHTML).not.toMatch(/on\w+=/i);
    } finally {
      unmount();
      host.remove();
    }
  });

  it("falls back to the raw source when parsing fails", () => {
    renderMermaidSVG.mockReset().mockImplementation(() => {
      throw new Error("parse error");
    });
    const { host, unmount } = mount(
      <MermaidDiagram code={DIAGRAM} streaming={false} />,
    );
    try {
      const fallback = host.querySelector('[data-slot="mermaid-fallback"]');
      expect(fallback).toBeTruthy();
      expect(fallback?.textContent).toContain("flowchart LR");
      expect(fallback?.textContent).toContain("diagram could not be rendered");
      expect(host.querySelector('[data-slot="mermaid-diagram"]')).toBeNull();
    } finally {
      unmount();
      host.remove();
    }
  });
});
