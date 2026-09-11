// @vitest-environment happy-dom
/**
 * Behaviour of the assistant-ui elements-catalog <MermaidDiagram> base
 * (props-driven, no runtime required).
 *
 * beautiful-mermaid is mocked rather than executed: what is under test is OUR
 * contract (skeleton while streaming, outer-only diagram on success, raw-source
 * fallback on parse failure), not mermaid's layout engine.
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
