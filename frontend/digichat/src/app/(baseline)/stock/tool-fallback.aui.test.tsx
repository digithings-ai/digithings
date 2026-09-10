// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolFallback } from "./tool-fallback.aui";

describe("stock ToolFallback", () => {
  it("renders the digisearch row with the raw backend id", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t1"
        toolName="digisearch"
        args={{ query: "jwt", mode: "keyword" }}
        argsText='{"query":"jwt","mode":"keyword"}'
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digisearch")).toBeTruthy();
    expect(screen.queryByText("digisearch keyword")).toBeNull();
  });

  it("renders vault tool ids verbatim in the row title", () => {
    render(
      <ToolFallback
        type="tool-call"
        toolCallId="t2"
        toolName="digivault_get_note"
        args={{ vault_paths: ["a.md"] }}
        argsText='{"vault_paths":["a.md"]}'
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
    expect(screen.getByText("digivault_get_note")).toBeTruthy();
    expect(screen.queryByText("digivault get note")).toBeNull();
  });
});
