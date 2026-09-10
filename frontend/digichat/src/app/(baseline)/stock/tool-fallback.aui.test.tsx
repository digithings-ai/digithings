// @vitest-environment happy-dom
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { ToolFallback } from "./tool-fallback.aui";

describe("stock ToolFallback", () => {
  it("names the digisearch row by retrieval method", () => {
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
    expect(screen.getByText("digisearch keyword")).toBeTruthy();
  });

  it("humanizes vault tool ids in the row title", () => {
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
    expect(screen.getByText("digivault get note")).toBeTruthy();
  });
});
