// @vitest-environment happy-dom
/**
 * Runtime kit <MermaidDiagram> (.aui): forwards the active message part's
 * running state as `streaming` to the props-driven base element.
 *
 * useAuiState is mocked: what is under test is OUR wiring (selector +
 * prop forwarding), not the assistant-ui store.
 */
import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";

import { MermaidDiagram } from "./mermaid-diagram.aui";

const useAuiState = vi.fn();

vi.mock("@assistant-ui/react", () => ({
  get useAuiState() {
    return useAuiState;
  },
}));

const baseProps: Array<Record<string, unknown>> = [];

vi.mock("./mermaid-diagram", () => ({
  MermaidDiagram: (props: Record<string, unknown>) => {
    baseProps.push(props);
    return null;
  },
  MermaidZoom: () => null,
}));

const Stub = () => null;

function mount(ui: React.ReactElement) {
  baseProps.length = 0;
  const host = document.createElement("div");
  document.body.append(host);
  const root = createRoot(host);
  act(() => {
    root.render(ui);
  });
  return { host, unmount: () => act(() => root.unmount()) };
}

describe("MermaidDiagram runtime kit", () => {
  it("forwards streaming=true while the part is running", () => {
    useAuiState.mockReset().mockReturnValue(true);
    const { host, unmount } = mount(
      <MermaidDiagram
        code="graph TD"
        language="mermaid"
        components={{ Pre: Stub, Code: Stub }}
      />,
    );
    try {
      expect(useAuiState).toHaveBeenCalled();
      expect(baseProps).toHaveLength(1);
      expect(baseProps[0]).toMatchObject({ code: "graph TD", streaming: true });
    } finally {
      unmount();
      host.remove();
    }
  });

  it("forwards streaming=false once the part settles", () => {
    useAuiState.mockReset().mockReturnValue(false);
    const { host, unmount } = mount(
      <MermaidDiagram
        code="graph TD"
        language="mermaid"
        components={{ Pre: Stub, Code: Stub }}
      />,
    );
    try {
      expect(baseProps).toHaveLength(1);
      expect(baseProps[0]).toMatchObject({
        code: "graph TD",
        streaming: false,
      });
    } finally {
      unmount();
      host.remove();
    }
  });
});
